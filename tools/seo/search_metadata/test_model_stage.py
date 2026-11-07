import json
import unittest
from unittest.mock import patch

from generate import atomic_json
from model_stage import page_bundle, queue
from ranking_policy import record
from research import historical_queries, import_generation
from semrush_workflow import collect, plan
import test_semrush_workflow


class ModelStageTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_semrush_workflow.SemrushTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db=self.fixture.db;self.root=self.fixture.root

    def imported(self):
        plan(self.db,'US','2026-11',1,1);self.db.commit()
        collect(self.db,self.root/'api','fake-key',True,20,transport=self.fixture.metrics)
        return page_bundle(self.db,286733,69)

    def response(self,request,**changes):
        value=dict(requestId=request['requestId'],model='gpt-6.1-sol',effort='medium',
                   sourcePdfId=286733,page=69,contentSha256=request['contentSha256'],
                   pageTitle='HP M1005 scanning',h1Heading='HP M1005 scanning',
                   pageDescription='Scanning a document with HP M1005 at 300 dpi.',requiresReview=False,
                   contentEvidence=['Scanning a document with HP M1005.'],selectedKeywords=['hp m1005 scanning'],
                   keywordDecisions=[dict(candidateId=item['candidateId'],decision='keep',reason='Scanning is the exact page topic',
                       contentEvidence=['Scanning a document with HP M1005.']) for item in request['semrushCandidates']])
        value.update(changes);path=self.root/'sol.json';atomic_json(path,value);return path

    def test_api_import_to_single_model_response_without_terra(self):
        request=self.imported()
        self.assertEqual(request['pipeline'],'import_then_sol')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM semrush_reviews').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_keywords').fetchone()[0],0)
        self.assertEqual(len(queue(self.db,self.root/'bundles')['queued']),1)
        result=import_generation(self.db,self.response(request),self.root/'runtime')
        self.assertEqual(result['status'],'validated_draft')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_model_keyword_decisions').fetchone()[0],1)
        self.assertEqual(queue(self.db,self.root/'bundles')['queued'],[])
        self.assertTrue((self.root/'runtime/733/286733/69.json').is_file())
        self.assertEqual(page_bundle(self.db,286733,69)['requestId'],request['requestId'])

    def test_old_term_survives_newer_reports_without_mixing_url_or_provider(self):
        def report(engine, url, date, words):
            return dict(engine=engine, id=engine+url+date, start=date, end=date,
                        payload={'verified': {'url': url}}, queries=[dict(query=q) for q in words])
        old = report('google', 'manual', '2026-04-01', ['still visible', 'older term'])
        recent = report('google', 'manual', '2026-11-03', ['still visible'])
        other = report('bing', 'manual', '2026-11-03', ['older term'])
        alias = report('google', 'amp', '2026-11-03', ['older term'])
        result = historical_queries([other, recent, alias, old])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['latestEnd'], '2026-11-03')
        self.assertEqual(result[0]['notReportedInLatest'], [
            dict(query='older term', start=old['start'], end=old['end'], windowId=old['id'])])

    def test_missing_decisions_or_fabricated_selection_do_not_store_draft(self):
        request=self.imported()
        for changes in [dict(keywordDecisions=[]),dict(selectedKeywords=['download a scanner driver']),
                        dict(keywordDecisions=[dict(candidateId='invented',decision='keep',reason='x')])]:
            with self.assertRaises(ValueError): import_generation(self.db,self.response(request,**changes))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_metadata_versions').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_model_keyword_decisions').fetchone()[0],0)

    def test_rejected_candidate_cannot_be_selected(self):
        request=self.imported()
        decisions=[dict(candidateId=request['semrushCandidates'][0]['candidateId'],decision='reject',reason='Wrong intent')]
        with self.assertRaisesRegex(ValueError,'rejected'):
            import_generation(self.db,self.response(request,keywordDecisions=decisions))

    def test_incomplete_collection_and_unsupported_excerpts_stay_held(self):
        plan(self.db,'US','2026-11',1,1);self.db.commit()
        with self.assertRaisesRegex(ValueError,'collection is not complete'): page_bundle(self.db,286733,69)
        self.db.commit()
        collect(self.db,self.root/'api','fake-key',True,20,transport=self.fixture.metrics)
        request=page_bundle(self.db,286733,69)
        decisions=[dict(candidateId=request['semrushCandidates'][0]['candidateId'],decision='keep',reason='x',contentEvidence=['Wrong content'])]
        with self.assertRaisesRegex(ValueError,'verbatim'): import_generation(self.db,self.response(request,keywordDecisions=decisions))

    def test_ranking_protection_is_rechecked_for_completed_model_response(self):
        request=self.imported();path=self.response(request)
        record(self.db,'google','2026-11-01','2026-11-03',self.fixture.url,4,50,'new-rank','test')
        with self.assertRaisesRegex(ValueError,'Ranking protection'): import_generation(self.db,path,self.root/'runtime')
        self.assertFalse((self.root/'runtime').exists())

    def test_new_provider_data_changes_frozen_model_request(self):
        request=self.imported();import_generation(self.db,self.response(request))
        row=self.db.execute('SELECT id,payload FROM research_windows').fetchone()
        payload=json.loads(row['payload']);payload['coverage']='updated source snapshot'
        self.db.execute('UPDATE research_windows SET payload=? WHERE id=?',(json.dumps(payload),row['id']))
        next_request=page_bundle(self.db,286733,69)
        self.assertNotEqual(next_request['requestId'],request['requestId'])
        self.assertEqual(len(queue(self.db,self.root/'bundles')['queued']),1)

    def test_effort_change_preserves_existing_requests_and_creates_medium_work(self):
        with patch('research.GENERATOR', ('gpt-6.1-sol', 'xhigh')):
            legacy = self.imported()
        current = page_bundle(self.db, 286733, 69)
        self.assertEqual(current['generatorEffort'], 'medium')
        self.assertNotEqual(current['requestId'], legacy['requestId'])
        with self.assertRaisesRegex(ValueError, 'model/effort'):
            import_generation(self.db, self.response(legacy, effort='medium'))
        import_generation(self.db, self.response(legacy, effort='xhigh'))
        effort = self.db.execute('SELECT effort FROM research_metadata_versions WHERE request_id=?',
                                 (legacy['requestId'],)).fetchone()[0]
        self.assertEqual(effort, 'xhigh')
        pending = queue(self.db, self.root/'bundles')['queued']
        self.assertEqual([item['requestId'] for item in pending], [current['requestId']])

    def test_period_outcomes_include_pages_outside_the_generation_queue(self):
        from outcomes import reconcile
        request = self.imported()
        import_generation(self.db, self.response(request))
        second = 'https://manualsdump.com/en/manuals/other/1234/7'
        record(self.db,'google','2026-11-04','2026-11-04',second,8,30,'inventory','page_inventory')
        record(self.db,'bing','2026-09-01','2026-09-01',
               'https://manualsdump.com/en/manuals/other/88/1',9,10,'old','page_inventory')
        result = reconcile(self.db, '2026-11-01', '2026-11-04')
        self.assertEqual(result['states'], {'pending':1, 'validated_draft':1})
        rows = self.db.execute('SELECT pdf,reason FROM research_period_outcomes ORDER BY last_seen DESC').fetchall()
        self.assertEqual([tuple(r) for r in rows], [(1234,'page_search_report_missing'), (286733,None)])
        record(self.db,'google','2026-11-05','2026-11-05',second,7.9,30,'new','page_inventory')
        refreshed = reconcile(self.db, '2026-11-01', '2026-11-04')
        self.assertEqual(refreshed['reasons'], {'protected_top_positions':1})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_period_outcomes').fetchone()[0], 2)

    def test_toolspd_plans_an_eligible_page_with_impressions_and_no_clicks(self):
        self.db.execute('UPDATE research_windows SET page_clicks=0,page_impressions=20')
        self.db.execute('DELETE FROM research_queries')
        planned = plan(self.db,'US','2026-11',1,1,transport='toolspd')
        self.assertEqual(planned['pagesPlanned'],1)
        source = self.db.execute('SELECT kind,payload FROM semrush_seed_sources').fetchone()
        self.assertEqual(source['kind'],'content_derived')
        self.assertEqual(json.loads(source['payload'])['clicks'],0)

    def test_explicit_no_results_is_reviewed_in_the_same_model_response(self):
        plan(self.db,'US','2026-11',1,1,1);self.db.commit()
        def transport(request,api_key):
            return 'ERROR 50 :: NOTHING FOUND' if request['method']=='related_v3' else self.fixture.metrics(request,api_key)
        collect(self.db,self.root/'api','fake-key',True,60,transport=transport)
        request=page_bundle(self.db,286733,69)
        decisions=[dict(candidateId=item['candidateId'],
                       decision='no_results' if item['metrics']['status']=='nothing found' else 'keep',
                       reason='Preserve missing metrics; scanning is supported by the page',
                       contentEvidence=['Scanning a document with HP M1005.']) for item in request['semrushCandidates']]
        result=import_generation(self.db,self.response(request,keywordDecisions=decisions))
        self.assertEqual(result['status'],'validated_draft')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_model_keyword_decisions').fetchone()[0],2)

    def test_no_disclosed_queries_uses_labelled_content_seeds_without_inventing_traffic(self):
        row=self.db.execute('SELECT id,payload FROM research_windows').fetchone()
        payload=json.loads(row['payload']);payload['verified']['queries']=[]
        self.db.execute('DELETE FROM research_queries')
        self.db.execute('UPDATE research_windows SET payload=? WHERE id=?',(json.dumps(payload),row['id']))
        request=self.imported()
        self.assertEqual(request['searchWindows'][0]['queries'],[])
        seed=request['semrushCandidates'][0]['seedSources'][0]
        self.assertEqual(seed['kind'],'content_derived')
        self.assertEqual(seed['provenance']['clicks'],0)
        keyword=request['semrushCandidates'][0]['metrics']['keyword']
        result=import_generation(self.db,self.response(request,selectedKeywords=[keyword]))
        self.assertEqual(result['status'],'validated_draft')


if __name__=='__main__': unittest.main()
