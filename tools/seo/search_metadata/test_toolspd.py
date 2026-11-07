import datetime as dt
import json
import unittest
from unittest.mock import Mock

import test_semrush_workflow as fixtures
from model_stage import page_bundle
from ranking_policy import record
from semrush_workflow import collect, plan
from toolspd import ReportUnavailable, ingest_snapshot, init_ui, parse_snapshot, pending, reserve, retry, url


class ToolsPdTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.SemrushTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.db,self.root,self.save=fixture.db,fixture.root,fixture.save
        self.month=dt.date.today().strftime('%Y-%m')
        init_ui(self.db)
        plan(self.db,'US',self.month,1,1,transport='toolspd');self.db.commit()
        self.job=pending(self.db,1)[0];self.request=self.job['request']

    def snapshot(self,**changes):
        return dict(dict(schemaVersion=1,kind='toolspd_keywordmagic_ui',sourceUrl=url(self.request),
                         heading='Keyword Magic Tool: '+self.request['keyword'],countryLabel='United States',
                         observedAt=dt.datetime.now(dt.timezone.utc).isoformat(),
                         headers=['Keyword','Volume','KD %','CPC (USD)','Updated'],
                         rows=[[self.request['keyword'],'1.2K','n/a','0.25','3 months ago']],
                         tableText='Keyword table',pageText='Keyword table',coverage='Rendered UI subset'),**changes)

    def test_visible_metrics_keep_unknown_kd_and_country_scope(self):
        result=parse_snapshot(self.request,self.snapshot())[0]
        self.assertEqual(result['volume'],1200);self.assertIsNone(result['kd'])
        self.assertEqual(result['scope'],'country');self.assertEqual(result['country'],'US')
        self.assertIsNone(result['snapshot'])

    def test_query_country_and_month_must_match_observed_report(self):
        invalid=[self.snapshot(sourceUrl=url({**self.request,'keyword':'wrong query'})),
                 self.snapshot(countryLabel='United Kingdom'),
                 self.snapshot(observedAt='2025-01-01T00:00:00+00:00'),
                 self.snapshot(sourceUrl='https://sktiman.toolspd.com.evil.example/analytics/keywordmagic/')]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError): parse_snapshot(self.request,value)

    def test_explicit_no_results_is_not_zero_demand_or_provider_error(self):
        value=self.snapshot(rows=[],tableText='Nothing found')
        row=parse_snapshot(self.request,value)[0]
        self.assertEqual(row['status'],'nothing found');self.assertIsNone(row['volume'])
        for text in ('Daily Limit Reached','Something went wrong','Verify you are human','Error 524: A timeout occurred'):
            with self.assertRaises(ReportUnavailable): parse_snapshot(self.request,{**value,'pageText':text})
        with self.assertRaises(ReportUnavailable): parse_snapshot(self.request,self.snapshot(rows=[],tableText='Loading'))

    def test_import_is_idempotent_and_reaches_sol_without_paid_api(self):
        path=self.save('ui.json',self.snapshot())
        self.assertTrue(ingest_snapshot(self.db,self.job['jobId'],path)['imported'])
        self.assertFalse(ingest_snapshot(self.db,self.job['jobId'],path)['imported'])
        bundle=page_bundle(self.db,286733,69)
        self.assertEqual(len(bundle['semrushCandidates']),1)
        self.assertEqual(bundle['semrushCandidates'][0]['request']['method'],'toolspd_keywordmagic')
        self.assertEqual(self.db.execute('SELECT SUM(reserved_units) FROM semrush_jobs').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_metadata_versions').fetchone()[0],0)

    def test_ranking_protection_is_rechecked_before_import(self):
        record(self.db,'google','2026-11-05','2026-11-05','https://manualsdump.com/en/manuals/hp-m1005/286733/69',3,50,'test','test')
        self.db.commit()
        with self.assertRaisesRegex(ValueError,'ranking protection'): ingest_snapshot(self.db,self.job['jobId'],self.save('ui.json',self.snapshot()))
        self.assertEqual(self.db.execute('SELECT status FROM semrush_jobs').fetchone()[0],'planned')

    def test_daily_reservations_survive_retry_and_interruption(self):
        self.assertIsNotNone(reserve(self.db,self.job['jobId'],1))
        self.assertEqual(pending(self.db),[])
        retry(self.db,self.job['jobId'])
        self.assertIsNone(reserve(self.db,self.job['jobId'],1))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM semrush_ui_attempts').fetchone()[0],1)

    def test_api_collector_never_dispatches_ui_jobs(self):
        transport=Mock()
        self.assertEqual(collect(self.db,self.root/'api','fake-key',True,100,transport=transport)['completedRequests'],0)
        transport.assert_not_called()

    def test_ui_plan_explicitly_supersedes_unspent_api_plan(self):
        plan(self.db,'US',self.month,1,1,transport='api');self.db.commit()
        plan(self.db,'US',self.month,1,1,transport='toolspd');self.db.commit()
        states={json.loads(r['request'])['method']:r['status'] for r in self.db.execute('SELECT request,status FROM semrush_jobs')}
        self.assertEqual(states['metrics_v4'],'superseded')
        self.assertEqual(states['toolspd_keywordmagic'],'planned')
        ingest_snapshot(self.db,self.job['jobId'],self.save('ui.json',self.snapshot()))
        self.assertEqual(len(page_bundle(self.db,286733,69)['semrushCandidates']),1)

    def test_bad_columns_and_out_of_range_kd_are_rejected(self):
        for changes in [dict(headers=['Keyword','Volume']),dict(rows=[[self.request['keyword'],'20','101','0.25','today']])]:
            with self.assertRaises(ValueError): parse_snapshot(self.request,self.snapshot(**changes))


if __name__=='__main__': unittest.main()
