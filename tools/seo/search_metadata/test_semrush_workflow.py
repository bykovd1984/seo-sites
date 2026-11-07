import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from history import connect
from research import ROOT, bundle, import_contexts, import_page, start_run
from semrush_workflow import candidates, collect, init, parse, plan, review, status
from workflow import prepare
import test_research


class SemrushTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'artifacts/search-metadata-tests';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=connect(self.root/'research.sqlite3');self.addCleanup(self.db.close)
        init(self.db);start_run(self.db,'test')
        self.url='https://manualsdump.com/en/manuals/hp-m1005/286733/69'
        # Reuse a real page-filtered export fixture; no provider traffic is involved.
        fixture=test_research.ResearchTests();fixture.root=self.root;fixture.url=self.url
        manifest=fixture.manifest(semrush=[])
        import_page(self.db,manifest,'test')
        source=dict(type='seo_context',sourcePdfId=286733,page=69,brand='HP',models=['M1005'],readOnly=True,
                    rawHtmlBase64=base64.b64encode(b'<p>Scanning a document with HP M1005. Resolution 300 dpi.</p>').decode())
        path=self.save('context.jsonl',source);import_contexts(self.db,path)
        self.db.commit()

    def save(self,name,data):
        path=self.root/name;path.write_text(json.dumps(data),encoding='utf-8');return path

    def metrics(self,request,api_key):
        return json.dumps(dict(meta=dict(country=request['country'],keyword=request['keyword'],month=request['month'],success=True),
                               data=dict(search_volume='120',keyword_difficulty=17,competitive_density=91)))

    def ready(self):
        plan(self.db,'US','2026-11',1,1);self.db.commit()
        return collect(self.db,self.root/'api','fake-key',True,20,transport=self.metrics)

    def review_item(self,item,**changes):
        value={k:item[k] for k in ('sourcePdfId','page','contentSha256','jobId')}
        value.update(keyword=item['candidate']['keyword'],decision='keep',reason='Exact scanning topic supported by the source text',
                     contentEvidence=['Scanning a document with HP M1005.'])
        value.update(changes)
        return self.save('review.json',dict(model='gpt-6.1-terra',effort='high',reviews=[value]))

    def test_full_handoff_preserves_metrics_and_waits_for_content_review(self):
        self.assertEqual(self.ready()['completedRequests'],1)
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'semrush_pending')
        values=candidates(self.db)
        self.assertEqual(len(values),1)
        self.assertEqual(values[0]['candidate']['advertiserCompetition'],91)
        path=self.review_item(values[0])
        self.assertEqual(review(self.db,path)['importedReviews'],1)
        self.assertEqual(review(self.db,path)['importedReviews'],0)
        result=bundle(self.db,286733,69)
        self.assertFalse(result['partialResearch'])
        self.assertEqual(result['semrush'][0]['kd'],17)
        self.assertEqual(result['semrush'][0]['country_database'],'us')
        self.assertEqual(result['semrush'][0]['payload']['providerMetrics']['advertiserCompetition'],91)
        self.assertEqual(candidates(self.db),[])

    def test_budget_approval_dedup_and_restart(self):
        plan(self.db,'US','2026-11',1,1,3)
        self.assertEqual(status(self.db)['plannedMaximumUnits'],140)
        self.assertEqual(plan(self.db,'US','2026-11',1,1,3)['newLinks'],0)
        self.db.commit();transport=Mock(side_effect=self.metrics)
        with self.assertRaisesRegex(ValueError,'approval'):
            collect(self.db,self.root/'api','fake-key',False,1000,transport=transport)
        self.assertEqual(collect(self.db,self.root/'api','fake-key',True,1,transport=transport)['completedRequests'],0)
        transport.assert_not_called()
        # A committed reservation simulates interruption immediately before/after the request.
        self.db.execute("UPDATE semrush_jobs SET status='reserved',reserved_units=max_units")
        self.db.commit()
        self.assertEqual(collect(self.db,self.root/'api','fake-key',True,1000,transport=transport)['completedRequests'],0)
        transport.assert_not_called()
        self.assertEqual(status(self.db)['reservedUnits'],140)

    def test_uncertain_requests_never_reissue_and_do_not_disclose_key(self):
        plan(self.db,'US','2026-11',1,1);self.db.commit()
        transport=Mock(side_effect=RuntimeError('https://example.invalid/?key=fake-key'))
        result=collect(self.db,self.root/'api','fake-key',True,20,transport=transport)
        self.assertEqual(result['jobs'],{'uncertain':1})
        self.assertEqual(result['reservedUnits'],20)
        collect(self.db,self.root/'api','fake-key',True,40,transport=transport)
        self.assertEqual(transport.call_count,1)
        error=self.db.execute('SELECT error FROM semrush_jobs').fetchone()[0]
        self.assertEqual(error,'RuntimeError')

    def test_wrong_response_and_advertiser_competition_cannot_become_kd(self):
        request=dict(method='metrics_v4',keyword='hp scanning',country='US',month='2026-11')
        body=json.loads(self.metrics(request,'fake-key'));body['data'].pop('keyword_difficulty')
        self.assertIsNone(parse(request,json.dumps(body))[0]['kd'])
        body['meta']['country']='UK'
        with self.assertRaisesRegex(ValueError,'context'): parse(request,json.dumps(body))
        body['meta']['country']='US';body['data']['keyword_difficulty']=101
        with self.assertRaisesRegex(ValueError,'difficulty'): parse(request,json.dumps(body))

    def test_related_csv_and_explicit_no_results(self):
        request=dict(method='related_v3',keyword='hp scanning',country='US',limit=2)
        result=parse(request,'Keyword;Search Volume;Keyword Difficulty Index;Competition\n"hp m1005 scanning";20;14;0.9\n')
        self.assertEqual(result[0]['kd'],14)
        self.assertEqual(result[0]['advertiserCompetition'],'0.9')
        self.assertIsNone(result[0]['snapshot'])
        self.assertEqual(parse(request,'ERROR 50 :: NOTHING FOUND')[0]['status'],'nothing found')
        with self.assertRaises(ValueError): parse(request,'ERROR 120 :: WRONG KEY')
        with self.assertRaises(ValueError): parse(request,'')

    def test_review_rejects_unsupported_claim_and_stale_source(self):
        self.ready();item=candidates(self.db)[0]
        with self.assertRaisesRegex(ValueError,'verbatim'):
            review(self.db,self.review_item(item,contentEvidence=['This page provides a driver download']))
        self.assertEqual(status(self.db)['reviews'],0)
        with self.assertRaisesRegex(ValueError,'changed'):
            review(self.db,self.review_item(item,contentSha256='a'*64))
        self.assertEqual(status(self.db)['reviews'],0)

    def test_rejected_candidate_does_not_unlock_generation(self):
        self.ready();item=candidates(self.db)[0]
        review(self.db,self.review_item(item,decision='reject',contentEvidence=[]))
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'semrush_pending')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_keywords').fetchone()[0],0)

    def test_saved_response_redacts_key_and_failure_keeps_raw_proof(self):
        plan(self.db,'US','2026-11',1,1);self.db.commit()
        transport=Mock(return_value='unexpected response fake-key')
        collect(self.db,self.root/'api','fake-key',True,20,transport=transport)
        job=self.db.execute('SELECT * FROM semrush_jobs').fetchone()
        self.assertEqual(job['status'],'uncertain')
        path=self.db.execute('SELECT path FROM research_artifacts WHERE id=?',(job['artifact_id'],)).fetchone()[0]
        body=Path(path).read_text(encoding='utf-8')
        self.assertNotIn('fake-key',body)
        self.assertIn('[REDACTED]',body)

    def test_local_orchestration_resumes_without_network_or_duplicate_jobs(self):
        result=prepare(self.db,self.root/'absent.sqlite3',self.root/'workflow','US','2026-11',1,1,2)
        self.assertFalse(result['productionChanged'])
        self.assertEqual(result['semrush']['plannedMaximumUnits'],100)
        self.assertEqual(result['apiCandidates'],0)
        self.assertEqual(result['solQueue'],[])
        self.db.commit()
        repeated=prepare(self.db,self.root/'absent.sqlite3',self.root/'workflow','US','2026-11',1,1,2)
        self.assertEqual(repeated['semrush']['newLinks'],0)
        self.assertEqual(status(self.db)['reservedUnits'],0)
        self.assertTrue((self.root/'workflow/status.json').is_file())

    def test_shared_keyword_request_is_reused_across_page_contexts(self):
        from semrush_workflow import add_job
        request=dict(method='metrics_v4',keyword='hp scanning',country='US',month='2026-11')
        add_job(self.db,request,286733,69,'a'*64,'hp scanning','2026-11-01',2)
        add_job(self.db,request,286733,70,'b'*64,'hp scanning','2026-11-01',1)
        self.assertEqual(status(self.db)['plannedMaximumUnits'],20)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM semrush_links').fetchone()[0],2)

    def test_overlapping_query_reports_are_not_added_together(self):
        from semrush_workflow import selected_queries
        fixture=test_research.ResearchTests();fixture.root=self.root;fixture.url=self.url
        # Same window and URL, new raw export supersedes the previous observation.
        fixture.export(query_clicks=3)
        manifest=json.loads((self.root/'page.json').read_text())
        manifest['coverage']='newer export'
        import_page(self.db,self.save('new-page.json',manifest),'test')
        self.assertEqual(selected_queries(self.db,286733,69)[0]['clicks'],3)

    def test_requested_period_and_allowed_jobs_bound_paid_collection(self):
        outside=plan(self.db,'US','2026-11',1,1,start='2026-10-01',end='2026-10-03')
        self.assertEqual(outside['jobIds'],[])
        inside=plan(self.db,'US','2026-11',1,1,start='2026-11-01',end='2026-11-03')
        self.assertEqual(len(inside['jobIds']),1)
        self.db.commit();transport=Mock()
        result=collect(self.db,self.root/'api','fake-key',True,1000,transport=transport,allowed_job_ids=set())
        self.assertEqual(result['reservedUnits'],0);transport.assert_not_called()


if __name__=='__main__': unittest.main()
