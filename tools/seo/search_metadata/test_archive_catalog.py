import json
import gzip
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from archive_catalog import archive_queue, open_snapshot, prepare_period, hydrate_pages, archive_context_queue, reconcile_period
from history import bind_scope, checkpoint, connect, ingest, ingest_page_metrics
from research import ROOT, init


class ArchiveCatalogTests(unittest.TestCase):
    def setUp(self):
        base = ROOT/'artifacts/search-metadata-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.history = connect(self.root/'history.sqlite3')
        self.addCleanup(self.history.close)
        self.db = connect(self.root/'research.sqlite3')
        self.addCleanup(self.db.close)
        init(self.db)
        self.site = 'https://manualsdump.com/'
        bind_scope(self.history,'google',self.site)

    def metric(self, pdf, date, position=12, clicks=0, amp=False):
        url = self.site + ('amp/' if amp else '') + f'en/manuals/model/{pdf}/1'
        ingest_page_metrics(self.history,'google',self.site,date,date,url,clicks,50,position,{'fixture':True})
        return url

    def prepare(self):
        self.history.commit()
        return prepare_period(self.db,self.root/'history.sqlite3',self.root/'archive','2026-01-01','2026-11-04')

    def test_full_period_includes_old_and_impression_only_pages_and_protects_aliases(self):
        url = self.metric(1,'2026-02-01')
        self.metric(2,'2026-11-03',clicks=4)
        self.metric(3,'2026-11-04')
        self.metric(3,'2026-06-01',position=3,amp=True)
        ingest(self.history,[dict(engine='google',start='2026-02-01',end='2026-02-01',url=url,
            query='old relevant query',clicks=0,impressions=12,position=15),
            dict(engine='google',start='2026-03-01',end='2026-03-01',url=self.site+'en/manuals/unknown/4/1',
            query='query without page average',clicks=1,impressions=12,position=20)],'gsc-api-web-final')
        result = self.prepare()
        self.assertEqual((result['discoveredPages'],result['candidates']),(4,2))
        queue = archive_queue(self.db,result['periodId'])['pages']
        self.assertEqual([r['pdf'] for r in queue],[2,1])
        self.assertEqual(queue[1]['priority_clicks'],0)
        reasons = dict(self.db.execute('SELECT pdf,reason FROM research_archive_pages'))
        self.assertEqual(reasons[3],'protected_top_positions')
        self.assertEqual(reasons[4],'page_position_unknown')
        snapshot = open_snapshot(result['snapshot'])
        try:
            self.assertEqual(snapshot.execute('SELECT COUNT(*) FROM observations').fetchone()[0],2)
            with self.assertRaises(sqlite3.OperationalError):
                snapshot.execute('DELETE FROM observations')
        finally:
            snapshot.close()

    def test_snapshot_is_frozen_and_retries_are_idempotent(self):
        self.metric(1,'2026-02-01')
        first, second = self.prepare(), self.prepare()
        self.assertEqual(first['periodId'],second['periodId'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_archive_pages').fetchone()[0],1)
        self.metric(1,'2026-11-04',position=2)
        newer = self.prepare()
        self.assertNotEqual(first['periodId'],newer['periodId'])
        self.assertEqual((first['candidates'],newer['candidates']),(1,0))
        source = open_snapshot(first['snapshot'])
        try:
            self.assertEqual(source.execute('SELECT COUNT(*) FROM api_page_metrics').fetchone()[0],1)
        finally:
            source.close()

    def test_interrupted_index_preserves_progress_and_recovers_missing_rows(self):
        self.metric(1,'2026-02-01'); self.metric(2,'2026-03-01')
        first = self.prepare()
        with self.db:
            self.db.execute("UPDATE research_archive_periods SET status='indexing'")
            self.db.execute('UPDATE research_archive_pages SET history_imported=1 WHERE pdf=1')
            self.db.execute('DELETE FROM research_archive_pages WHERE pdf=2')
        result = self.prepare()
        self.assertEqual((result['status'],result['historyImportedPages'],result['discoveredPages']),('indexed',1,2))
        self.assertEqual([r['pdf'] for r in archive_queue(self.db,result['periodId'])['pages']],[2])

    def test_wrong_property_cannot_enter_a_catalog(self):
        self.metric(1,'2026-02-01')
        self.history.execute('UPDATE provider_scopes SET site=?',('https://another.example/',))
        with self.assertRaisesRegex(ValueError,'property binding'):
            self.prepare()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_archive_pages').fetchone()[0],0)

    def seed_page_history(self, pdf=1):
        for date,query in [('2026-02-01','historical phrase'),('2026-11-03','current phrase')]:
            url=self.metric(pdf,date)
            ingest(self.history,[dict(engine='google',start=date,end=date,url=url,query=query,
                clicks=0,impressions=20,position=14)],'gsc-api-web-final')
            checkpoint(self.history,'google:web:'+self.site+':'+date,dict(done=True,possibly_truncated=False))

    def test_hydration_retains_all_query_dates_in_one_compressed_batch(self):
        self.seed_page_history(1);self.seed_page_history(2)
        period=self.prepare()['periodId'];directory=self.root/'batch'
        result=hydrate_pages(self.db,period,directory,10)
        self.assertEqual((result['importedPages'],result['importedWindows']),(2,4))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queries').fetchone()[0],4)
        self.assertEqual(self.db.execute('SELECT COUNT(DISTINCT raw_artifact) FROM research_windows').fetchone()[0],1)
        files=list(directory.glob('*'))
        self.assertEqual(len(files),1)
        evidence=json.loads(gzip.decompress(files[0].read_bytes()))
        self.assertEqual({r['start'] for p in evidence['pages'] for r in p['queries']},{'2026-02-01','2026-11-03'})
        self.assertEqual([p['sourcePdfId'] for p in archive_context_queue(self.db,period)['pages']],[1,2])
        self.assertEqual(hydrate_pages(self.db,period,directory,10)['importedPages'],0)

    def test_page_transaction_rolls_back_after_interruption_and_resumes(self):
        self.seed_page_history()
        period=self.prepare()['periodId'];directory=self.root/'batch'
        from import_api_history import store_window
        calls=[]
        def interrupted(*args,**kwargs):
            calls.append(1)
            if len(calls)==2: raise RuntimeError('fixture interruption')
            return store_window(*args,**kwargs)
        with patch('import_api_history.store_window',side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError,'fixture interruption'):
                hydrate_pages(self.db,period,directory,10)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_windows').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT history_imported FROM research_archive_pages').fetchone()[0],0)
        result=hydrate_pages(self.db,period,directory,10)
        self.assertEqual((result['importedPages'],result['importedWindows']),(1,2))

    def test_missing_query_checkpoint_cannot_be_treated_as_complete(self):
        self.metric(1,'2026-02-01')
        period=self.prepare()['periodId']
        result=hydrate_pages(self.db,period,self.root/'batch',10)
        self.assertEqual((result['importedPages'],result['held'][0]['reason']),(0,'archive_query_checkpoint_incomplete'))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_windows').fetchone()[0],0)

    def test_modified_snapshot_is_rejected_before_history_import(self):
        self.seed_page_history()
        result=self.prepare()
        path=Path(result['snapshot']);data=path.read_bytes();path.write_bytes(data[:-1]+bytes([data[-1]^1]))
        with self.assertRaisesRegex(ValueError,'recorded hash'):
            hydrate_pages(self.db,result['periodId'],self.root/'batch',10)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_windows').fetchone()[0],0)

    def test_reconciliation_never_calls_unprepared_pages_completed(self):
        self.seed_page_history(1);self.seed_page_history(2)
        period=self.prepare()['periodId']
        hydrate_pages(self.db,period,self.root/'batch',1)
        result=reconcile_period(self.db,period)
        self.assertEqual(result['assessedImportedPages'],1)
        self.assertEqual(sum(r['pages'] for r in result['states'] if r['state']=='pending'),2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM research_archive_pages WHERE state='validated_draft'").fetchone()[0],0)


if __name__ == '__main__':
    unittest.main()
