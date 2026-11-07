import base64
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_codex_drafts
import test_research
from codex_groups import init_groups,select_sources,prepare_group,load_group,claim_group,run_group,repair_sources,case_evidence,repair_queue
from codex_drafts import prepare,run_one
from generate import atomic_json
from model_stage import page_bundle,queue
from outcomes import page_outcome
from research import import_contexts,import_page


class GroupDraftTests(unittest.TestCase):
    def setUp(self):
        fixture=test_codex_drafts.CodexDraftTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.db,self.root,self.period=fixture.db,fixture.root,fixture.period
        report=test_research.ResearchTests();report.root=self.root
        report.url='https://manualsdump.com/en/manuals/brother-ql800/1234/5'
        import_page(self.db,report.manifest(sourcePdfId=1234,page=5,semrush=[]),'test')
        source=dict(type='seo_context',sourcePdfId=1234,page=5,brand='Brother',models=['QL800'],readOnly=True,
            rawHtmlBase64=base64.b64encode(b'<p>Printing labels with Brother QL800.</p>').decode())
        path=self.root/'brother.jsonl';atomic_json(path,source);import_contexts(self.db,path)
        self.db.execute('INSERT INTO research_archive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (self.period,1234,5,report.url,'2026-11-03',1,1,'pending','ready_for_generation',1,'{}','2026-11-07'))
        init_groups(self.db);self.db.commit()
        self.calls=[]

    def group(self):
        sources,held=select_sources(self.db,self.period,8,200000)
        self.assertEqual(held,{})
        self.assertEqual([s['page'] for s in sources],[69,5])
        return prepare_group(self.db,self.period,self.root/'groups',sources)

    def executor(self,mutate=None,tools=False):
        def execute(folder,command,environment):
            self.calls.append(str(folder))
            self.assertIn('gpt-6.1-sol',command)
            self.assertIn('model_reasoning_effort="medium"',command)
            self.assertNotIn('OPENAI_API_KEY',environment)
            import gzip
            sources=json.loads(gzip.decompress((folder/'inputs.json.gz').read_bytes()))
            rows=[]
            for s in sources:
                title='HP M1005 scanning' if s['page']==69 else 'Brother QL800 label printing'
                quote='Scanning a document with HP M1005.' if s['page']==69 else 'Printing labels with Brother QL800.'
                rows.append(dict(requestId=s['requestId'],sourcePdfId=s['sourcePdfId'],page=s['page'],pageTitle=title,
                    h1Heading=title,pageDescription=quote,requiresReview=False,contentEvidence=[quote],
                    selectedKeywords=[],rationale='Exact page content supports this topic.',decisionGroups=[]))
            raw={'results':rows}
            if mutate:mutate(raw)
            atomic_json(folder/'model-output.json',raw)
            events=[dict(type='item.completed',item={'type':'command_execution' if tools else 'agent_message'}),
                dict(type='turn.completed',usage={'input_tokens':100,'cached_input_tokens':50,'output_tokens':20})]
            (folder/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n',encoding='utf-8')
            return 0
        return execute

    def test_two_pages_validate_independently_and_resume_without_call_or_double_usage(self):
        ident=self.group();result=run_group(self.db,ident,'codex',self.executor())
        self.assertEqual([p['status'] for p in result['pages']],['validated_draft','validated_draft'])
        again=run_group(self.db,ident,'codex',lambda *a:self.fail('Completed call must not repeat'))
        self.assertTrue(all(p['reused'] for p in again['pages']))
        self.assertEqual(len(self.calls),1)
        events=[json.loads(r[0]) for r in self.db.execute("SELECT payload FROM research_events WHERE event='codex_group_completed'")]
        self.assertEqual(len(events),1);self.assertEqual(events[0]['usage']['input_tokens'],100)
        pages=[json.loads(r[0]) for r in self.db.execute("SELECT payload FROM research_events WHERE event='codex_group_page_imported'")]
        self.assertEqual(len(pages),2);self.assertTrue(all('usage' not in p for p in pages))
        self.assertEqual(self.db.execute("SELECT count(*) FROM research_archive_pages WHERE state='validated_draft'").fetchone()[0],2)
        for row in self.db.execute('SELECT payload FROM research_metadata_versions'):
            self.assertTrue(json.loads(row[0])['draftOnly'])

    def test_cross_page_quote_is_held_and_only_invalid_page_is_explicitly_repaired(self):
        ident=self.group()
        def wrong(raw):raw['results'][1]['contentEvidence']=['Scanning a document with HP M1005.']
        result=run_group(self.db,ident,'codex',self.executor(wrong))
        self.assertEqual([p['status'] for p in result['pages']],['validated_draft','held'])
        period,sources,attempt,feedback=repair_sources(self.db,ident)
        self.assertEqual([s['page'] for s in sources],[5])
        child=prepare_group(self.db,period,self.root/'groups',sources,ident,attempt,feedback)
        fixed=run_group(self.db,child,'codex',self.executor())
        self.assertEqual(fixed['pages'][0]['status'],'validated_draft')
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_metadata_versions').fetchone()[0],2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM research_events WHERE event='codex_group_completed'").fetchone()[0],2)

    def test_uncertain_reservation_blocks_single_planners_and_never_dispatches_again(self):
        ident=self.group();_,_,manifest,sources=load_group(self.db,ident);claim_group(self.db,ident,manifest,sources)
        result=run_group(self.db,ident,'codex',lambda *a:self.fail('Uncertain reservation must not call the model'))
        self.assertEqual(result['state'],'held')
        self.assertEqual(prepare(self.db,self.period,self.root/'single',10)['queued'],[])
        self.assertEqual(queue(self.db,self.root/'queue',10)['queued'],[])
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'group_held')
        with self.assertRaises((ValueError,FileNotFoundError)):repair_sources(self.db,ident)

    def test_single_prepared_task_cannot_bypass_a_group_reservation(self):
        task=prepare(self.db,self.period,self.root/'single',1)['queued'][0]
        ident=self.group();_,_,manifest,sources=load_group(self.db,ident);claim_group(self.db,ident,manifest,sources)
        with patch('codex_drafts.subprocess.run',side_effect=AssertionError('No independent call')):
            result=run_one(self.db,task,'codex')
        self.assertEqual(result['status'],'held')

    def test_duplicate_or_missing_identity_holds_entire_group_but_counts_completed_call(self):
        ident=self.group()
        def duplicate(raw):raw['results'][1]['requestId']=raw['results'][0]['requestId']
        result=run_group(self.db,ident,'codex',self.executor(duplicate))
        self.assertEqual(result['reason'],'group_response_identity_coverage_mismatch')
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_metadata_versions').fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM research_events WHERE event='codex_group_completed'").fetchone()[0],1)
        period,sources,attempt,feedback=repair_sources(self.db,ident)
        self.assertEqual(len(sources),2)

    def test_wrong_numeric_page_identity_cannot_import_other_case(self):
        ident=self.group()
        def wrong(raw):raw['results'][1]['page']=69
        result=run_group(self.db,ident,'codex',self.executor(wrong))
        self.assertEqual([p['status'] for p in result['pages']],['validated_draft','held'])
        self.assertIn('identity mismatch',result['pages'][1]['reason'])

    def test_malformed_completed_response_is_held_without_auto_retry(self):
        ident=self.group()
        result=run_group(self.db,ident,'codex',self.executor(lambda raw:raw.update(results='invalid')))
        self.assertEqual(result['reason'],'invalid_group_response')
        again=run_group(self.db,ident,'codex',lambda *a:self.fail('Completed invalid output must not repeat'))
        self.assertEqual(again['state'],'held')
        self.assertEqual(len(self.calls),1)

    def test_repair_queue_lists_completed_invalid_current_members_only(self):
        ident=self.group()
        def wrong(raw):raw['results'][1]['contentEvidence']=['This quote is absent from the exact page.']
        run_group(self.db,ident,'codex',self.executor(wrong))
        calls=len(self.calls);value=repair_queue(self.db,self.period,25)
        self.assertEqual(len(self.calls),calls)
        self.assertEqual(value['modelCallsMade'],0);self.assertEqual(value['providerRequestsMade'],0)
        self.assertEqual([(r['groupId'],r['kind'],r['nextAttempt']) for r in value['repairs']],[(ident,'normal',1)])
        self.assertEqual([p['sourcePdfId'] for p in value['repairs'][0]['pages']],[1234])
        period,sources,attempt,feedback=repair_sources(self.db,ident)
        child=prepare_group(self.db,period,self.root/'groups',sources,ident,attempt,feedback)
        run_group(self.db,child,'codex',self.executor())
        self.assertEqual(repair_queue(self.db,self.period)['repairs'],[])

    def test_repair_queue_never_repeats_uncertain_or_changed_parent_output(self):
        ident=self.group();claim_group(self.db,ident,*load_group(self.db,ident)[2:])
        from codex_groups import hold_group
        hold_group(self.db,ident,'uncertain_group_call_requires_reconciliation')
        value=repair_queue(self.db,self.period)
        self.assertEqual(value['repairs'],[]);self.assertEqual(value['held'],{'repair_evidence_unavailable':1})
        _,folder,_,_=load_group(self.db,ident)
        atomic_json(folder/'invocation.json',dict(status='uncertain_call'))
        value=repair_queue(self.db,self.period)
        self.assertEqual(value['repairs'],[]);self.assertIn('Uncertain groups cannot be automatically repaired',value['held'])
        self.assertEqual(self.calls,[])

    def test_repair_queue_checks_parent_response_hash_and_attempt_limit(self):
        ident=self.group()
        def wrong(raw):raw['results'][1]['contentEvidence']=['This quote is absent from the exact page.']
        run_group(self.db,ident,'codex',self.executor(wrong))
        _,folder,_,_=load_group(self.db,ident);original=(folder/'model-output.json').read_bytes()
        (folder/'model-output.json').write_bytes(b'{}')
        value=repair_queue(self.db,self.period)
        self.assertEqual(value['repairs'],[]);self.assertIn('Parent group output changed',value['held'])
        (folder/'model-output.json').write_bytes(original)
        for _ in range(3):
            period,sources,attempt,feedback=repair_sources(self.db,ident)
            ident=prepare_group(self.db,period,self.root/'groups',sources,ident,attempt,feedback)
            def invalid(raw):raw['results'][0]['contentEvidence']=['This quote is still absent from the source.']
            run_group(self.db,ident,'codex',self.executor(invalid))
        value=repair_queue(self.db,self.period)
        self.assertEqual(value['repairs'],[]);self.assertIn('Group repair limit reached',value['held'])

    def test_input_mutation_is_rejected_before_call_and_event_mutation_before_import(self):
        ident=self.group();_,folder,_,_=load_group(self.db,ident)
        original=(folder/'prompt.txt').read_bytes();(folder/'prompt.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'input changed'):run_group(self.db,ident,'codex',self.executor())
        self.assertEqual(self.calls,[]);(folder/'prompt.txt').write_bytes(original)
        run_group(self.db,ident,'codex',self.executor())
        (folder/'events.jsonl').write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'events changed'):run_group(self.db,ident,'codex',self.executor())

    def test_tool_execution_cannot_import_a_page(self):
        ident=self.group();result=run_group(self.db,ident,'codex',self.executor(tools=True))
        self.assertEqual(result['reason'],'unexpected_model_tool_use')
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_metadata_versions').fetchone()[0],0)

    def test_fresh_source_is_checked_before_import(self):
        ident=self.group();execute=self.executor()
        def changed(folder,command,environment):
            result=execute(folder,command,environment)
            source=dict(type='seo_context',sourcePdfId=1234,page=5,brand='Brother',models=['QL800'],readOnly=True,
                rawHtmlBase64=base64.b64encode(b'<p>Changed source page text.</p>').decode())
            path=self.root/'changed.jsonl';atomic_json(path,source);import_contexts(self.db,path);self.db.commit()
            return result
        result=run_group(self.db,ident,'codex',changed)
        self.assertEqual([p['status'] for p in result['pages']],['validated_draft','held'])
        self.assertIn('evidence changed',result['pages'][1]['reason'])

    def test_compact_history_preserves_old_queries_and_exact_provider_scope(self):
        source=page_bundle(self.db,286733,69)
        import copy
        older=copy.deepcopy(source['searchWindows'][0]);older['start']=older['end']='2026-04-01'
        older['queries'][0]['query']='historic scanning';source['searchWindows'].append(older)
        data=case_evidence(source)
        queries=[q[0] for scope in data['searchHistory'] for q in scope['rows']]
        self.assertEqual(set(queries),{'historic scanning','hp m1005 scanning'})
        old=next(q for scope in data['searchHistory'] for q in scope['rows'] if q[0]=='historic scanning')
        self.assertEqual(old[2],'2026-04-01');self.assertTrue(old[-1])
        self.assertEqual(data['originalWindowCount'],2)


if __name__=='__main__':unittest.main()
