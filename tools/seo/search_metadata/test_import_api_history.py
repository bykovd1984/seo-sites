import json
import base64
import tempfile
import unittest
from pathlib import Path

from history import bind_scope, checkpoint, connect, ingest, ingest_page_metrics
from import_api_history import import_history
from research import ROOT, context_queue, import_contexts, import_page, init, research_queue, start_run
from ranking_policy import backfill


class ApiImportTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'artifacts/search-metadata-tests'
        base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.history=connect(self.root/'history.sqlite3')
        bind_scope(self.history,'google','https://manualsdump.com/')
        self.db=connect(self.root/'research.sqlite3')
        self.addCleanup(self.db.close)
        self.addCleanup(self.history.close)
        init(self.db)
        start_run(self.db,'api-history')
        self.url='https://manualsdump.com/en/manuals/hp/286733/69'

    def add(self, url=None, date='2026-11-01', query='hp manual'):
        ingest(self.history,[dict(engine='google',start=date,end=date,url=url or self.url,
               query=query,clicks=2,impressions=10,position=3)],'gsc-api-web-final')
        self.history.commit()

    def run_import(self, limit=100):
        return import_history(self.db,self.root/'history.sqlite3',self.root/'api',limit)

    def test_requires_completed_day_and_is_idempotent(self):
        self.add()
        self.assertEqual(self.run_import()['importedWindows'],0)
        checkpoint(self.history,'google:web:https://manualsdump.com/:2026-11-01',
                   dict(done=True,possibly_truncated=True))
        self.history.commit()
        self.assertEqual(self.run_import()['importedWindows'],1)
        self.assertEqual(self.run_import()['importedWindows'],0)
        row=self.db.execute('SELECT * FROM research_windows').fetchone()
        self.assertIsNone(row['page_clicks'])
        self.assertIsNone(row['page_impressions'])
        self.assertTrue(json.loads(row['payload'])['identityReviewRequired'])
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'identity_review')
        evidence=self.db.execute('SELECT path FROM research_artifacts').fetchone()[0]
        self.assertTrue(json.loads(Path(evidence).read_text(encoding='utf-8'))['checkpoint']['possibly_truncated'])

    def test_resume_and_distinct_urls(self):
        self.add()
        self.add(url='https://manualsdump.com/en/manuals/hp/286733/70')
        checkpoint(self.history,'google:web:https://manualsdump.com/:2026-11-01',dict(done=True))
        self.history.commit()
        self.assertEqual(self.run_import(1)['importedWindows'],1)
        self.assertEqual(self.run_import(1)['importedWindows'],1)
        self.assertEqual(self.run_import(1)['importedWindows'],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_windows').fetchone()[0],2)

    def test_mixed_or_unbound_property_is_rejected(self):
        self.add()
        with self.assertRaisesRegex(ValueError,'separate history'):
            bind_scope(self.history,'google','sc-domain:manualsdump.com')
        self.history.execute('DELETE FROM provider_scopes');self.history.commit()
        with self.assertRaisesRegex(ValueError,'property binding'): self.run_import()

    def test_page_average_has_separate_raw_provenance_and_resumes(self):
        ingest_page_metrics(self.history,'google','https://manualsdump.com/','2026-11-01','2026-11-01',self.url,
                            3,80,7.5,dict(method='SearchAnalytics.query',dimensions=[],position=7.5))
        self.history.commit()
        self.assertEqual(self.run_import()['importedPageMetrics'],1)
        self.assertEqual(self.run_import()['importedPageMetrics'],0)
        rank=self.db.execute('SELECT * FROM research_page_rankings').fetchone()
        self.assertEqual(rank['position'],7.5)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queries').fetchone()[0],0)
        self.assertEqual(len(research_queue(self.db,10)),1)
        self.assertEqual(context_queue(self.db,10),[dict(sourcePdfId=286733,page=69)])
        self.assertIn('counts',backfill(self.db))

    def test_traffic_without_disclosed_queries_stays_empty_and_queues_context(self):
        ingest_page_metrics(self.history,'google','https://manualsdump.com/','2026-11-01','2026-11-01',self.url,
                            3,80,12,dict(method='SearchAnalytics.query',dimensions=[]))
        self.history.commit()
        self.assertEqual(self.run_import()['importedWindows'],0)
        checkpoint(self.history,'google:web:https://manualsdump.com/:2026-11-01',dict(done=True,possibly_truncated=True))
        self.history.commit()
        self.assertEqual(self.run_import()['importedWindows'],1)
        self.assertEqual(self.run_import()['importedWindows'],0)
        window=self.db.execute('SELECT * FROM research_windows').fetchone()
        self.assertEqual((window['page_clicks'],window['page_impressions']),(3,80))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queries').fetchone()[0],0)
        self.assertEqual(context_queue(self.db,10),[dict(sourcePdfId=286733,page=69)])
        proof=self.db.execute('SELECT path FROM research_artifacts WHERE id=?',(window['raw_artifact'],)).fetchone()[0]
        self.assertTrue(json.loads(Path(proof).read_text(encoding='utf-8'))['checkpoint']['possibly_truncated'])

    def test_imported_query_window_still_gets_source_export(self):
        self.add()
        checkpoint(self.history,'google:web:https://manualsdump.com/:2026-11-01',dict(done=True))
        self.history.commit();self.run_import()
        self.assertEqual(research_queue(self.db,10),[])
        self.assertEqual(context_queue(self.db,10),[dict(sourcePdfId=286733,page=69)])

    def test_guarded_source_mapping_clears_only_technical_api_uncertainty(self):
        self.add();checkpoint(self.history,'google:web:https://manualsdump.com/:2026-11-01',dict(done=True))
        self.history.commit();self.run_import()
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'identity_review')
        data=dict(type='seo_context',sourcePdfId=286733,manualId=1286733,page=69,pageCount=100,readOnly=True,
                  rawHtmlBase64=base64.b64encode(b'<h2>Scanning a document</h2>').decode())
        path=self.root/'guarded-context.jsonl';path.write_text(json.dumps(data),encoding='utf-8')
        import_contexts(self.db,path)
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'semrush_pending')
        # A later explicit catalog/content mismatch remains quarantined.
        row=self.db.execute('SELECT id,payload FROM research_windows').fetchone()
        payload=json.loads(row['payload']);payload.pop('identityReviewReason')
        self.db.execute('UPDATE research_windows SET payload=? WHERE id=?',(json.dumps(payload),row['id']))
        import_contexts(self.db,path)
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'identity_review')


if __name__ == '__main__': unittest.main()
