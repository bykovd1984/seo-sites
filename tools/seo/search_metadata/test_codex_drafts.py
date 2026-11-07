import hashlib,json,unittest
from unittest.mock import patch
from pathlib import Path

from codex_drafts import search_history,expand_response,prepare,run_one
from archive_catalog import init_catalog
from generate import atomic_json
from model_stage import set_draft_policy
import test_semrush_workflow


class CodexDraftTests(unittest.TestCase):
    def setUp(self):
        fixture=test_semrush_workflow.SemrushTests();fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.db,self.root=fixture.db,fixture.root
        set_draft_policy(self.db,True);init_catalog(self.db)
        self.period='fixture-period'
        self.db.execute('INSERT INTO research_archive_periods VALUES (?,?,?,?,?,?,?,?,?)',
            (self.period,'fixture-snapshot','a'*64,'2026-01-01','2026-11-07','https://manualsdump.com/','fixture-proof','2026-11-07','indexed'))
        self.db.execute('INSERT INTO research_archive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (self.period,286733,69,fixture.url,'2026-11-04',2,1,'pending','ready_for_generation',1,'{}','2026-11-07'))
        self.db.commit()

    def task(self):return prepare(self.db,self.period,self.root/'drafts',10)['queued'][0]

    def saved_output(self,task,status='completed',tools=False):
        folder=Path(task['directory']);source=json.loads((folder/'bundle.json').read_text(encoding='utf-8'))
        raw=dict(pageTitle='HP M1005 scanning',h1Heading='HP M1005 scanning',
            pageDescription='Scanning a document with HP M1005 at 300 dpi.',requiresReview=False,
            contentEvidence=['Scanning a document with HP M1005.'],selectedKeywords=['hp m1005 scanning'],
            rationale='The query and source match.',decisionGroups=[])
        atomic_json(folder/'model-output.json',raw)
        atomic_json(folder/'invocation.json',dict(model='gpt-6.1-sol',effort='medium',auth='ChatGPT',requestId=source['requestId'],
            status=status,responseSha256=hashlib.sha256((folder/'model-output.json').read_bytes()).hexdigest()))
        events=[dict(type='item.completed',item={'type':'command_execution' if tools else 'agent_message'}),
            dict(type='turn.completed',usage={'input_tokens':100,'output_tokens':25})]
        (folder/'generation-events.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n',encoding='utf-8')
        return source

    def test_history_preserves_all_queries_and_provider_alias_dates_without_sums(self):
        def window(engine,url,date,queries):
            return dict(engine=engine,start=date,end=date,selectedForGeneration=True,payload={'verified':{'url':url}},
                queries=[dict(query=q,clicks=1,impressions=10,position=12) for q in queries])
        source=dict(searchWindows=[window('google','normal','2026-04-01',['old term','persistent']),
            window('google','normal','2026-11-04',['persistent']),window('bing','normal','2026-11-04',['old term']),
            window('google','amp','2026-11-04',['old term'])])
        history=search_history(source)
        self.assertEqual(len(history),3)
        google=next(g for g in history if (g['engine'],g['url'])==('google','normal'))
        byquery={q['query']:q for q in google['queries']}
        self.assertTrue(byquery['old term']['notReportedInLatestWindow'])
        self.assertEqual(byquery['old term']['lastReported']['end'],'2026-04-01')
        self.assertFalse(byquery['persistent']['notReportedInLatestWindow'])
        self.assertEqual(byquery['persistent']['lastReported']['clicks'],1)
        self.assertEqual(sum(len(g['queries']) for g in history),4)

    def test_prepare_requires_fully_imported_eligible_pending_period_row(self):
        for column,value in [('history_imported',0),('eligible',0),('state','excluded')]:
            with self.subTest(column=column):
                self.db.execute('UPDATE research_archive_pages SET '+column+'=?',(value,))
                self.assertEqual(prepare(self.db,self.period,self.root/'drafts',10)['queued'],[])
                self.db.execute("UPDATE research_archive_pages SET history_imported=1,eligible=1,state='pending'")
        self.assertEqual(len(prepare(self.db,self.period,self.root/'drafts',10)['queued']),1)

    def test_completed_model_output_resumes_without_another_call(self):
        task=self.task();self.saved_output(task)
        with patch('codex_drafts.subprocess.run',side_effect=AssertionError('Model must not be called twice')):
            result=run_one(self.db,task,'unused-codex')
        self.assertEqual(result['status'],'validated_draft')
        version=json.loads(self.db.execute('SELECT payload FROM research_metadata_versions WHERE id=?',(result['version'],)).fetchone()[0])
        self.assertTrue(version['draftOnly'])
        self.assertEqual(version['researchCoverage']['semrush']['status'],'not_imported')
        self.assertEqual(prepare(self.db,self.period,self.root/'drafts',10)['queued'],[])

    def test_uncertain_call_is_held_without_retrying(self):
        task=self.task();self.saved_output(task,status='running')
        with patch('codex_drafts.subprocess.run',side_effect=AssertionError('Uncertain model call must not repeat')):
            result=run_one(self.db,task,'unused-codex')
        self.assertEqual(result['status'],'held')
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_metadata_versions').fetchone()[0],0)

    def test_tool_use_or_changed_provenance_cannot_import_a_draft(self):
        task=self.task();self.saved_output(task,tools=True)
        with self.assertRaisesRegex(ValueError,'Unexpected model tool use'):run_one(self.db,task,'unused-codex')
        folder=Path(task['directory']);receipt=json.loads((folder/'invocation.json').read_text(encoding='utf-8'))
        receipt['effort']='xhigh';atomic_json(folder/'invocation.json',receipt)
        with self.assertRaisesRegex(ValueError,'Receipt model'):run_one(self.db,task,'unused-codex')
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_metadata_versions').fetchone()[0],0)

    def test_candidate_groups_cover_exact_frozen_ids_once(self):
        task=self.task();source=self.saved_output(task)
        source['semrushCandidates']=[{'candidateId':'first'},{'candidateId':'second'}]
        raw=json.loads((Path(task['directory'])/'model-output.json').read_text(encoding='utf-8'))
        raw['decisionGroups']=[dict(numbers=[1,2],decision='reject',reason='Unrelated',contentEvidence=[])]
        result=expand_response(source,raw)
        self.assertEqual([d['candidateId'] for d in result['keywordDecisions']],['first','second'])
        raw['decisionGroups'][0]['numbers']=[1,1]
        with self.assertRaisesRegex(ValueError,'exact frozen candidates once'):expand_response(source,raw)

if __name__=='__main__':unittest.main()
