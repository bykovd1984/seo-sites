import base64
import json
import unittest
import zlib

import test_archive_catalog as fixtures
from archive_catalog import archive_context_queue, hydrate_pages
from history import checkpoint, ingest, ingest_page_metrics
from ranking_policy import record


class ReviewContextQueueTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ArchiveCatalogTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db=self.fixture.db

    def period(self,pages):
        for pdf,page,date in pages:
            url=self.fixture.site+f'en/manuals/model/{pdf}/{page}'
            ingest_page_metrics(self.fixture.history,'google',self.fixture.site,date,date,url,1,50,12,{'fixture':True})
            ingest(self.fixture.history,[dict(engine='google',start=date,end=date,url=url,query='source review topic',
                clicks=1,impressions=20,position=12)],'gsc-api-web-final')
            checkpoint(self.fixture.history,'google:web:'+self.fixture.site+':'+date,dict(done=True,possibly_truncated=False))
        period=self.fixture.prepare()['periodId']
        hydrate_pages(self.db,period,self.fixture.root/'batch',100)
        return period

    def context(self,pdf,page,count=20,review=False,legacy=False):
        identity=f'context-{pdf}-{page}'
        context=dict(type='legacy_seo_example' if legacy else 'seo_context',sourcePdfId=pdf,page=page,
            readOnly=True,pageCount=count,manualId=10000+pdf,format='legacy_page' if legacy else 'converted',
            rawHtmlBase64=base64.b64encode(b'<p>Saved guarded source text.</p>').decode())
        with self.db:
            self.db.execute('INSERT INTO research_content VALUES (?,?,?,?,?,?,?)',
                (identity,pdf,page,'source-sha','source-proof',zlib.compress(json.dumps(context).encode()),'2026-11-04'))
            if review:
                self.db.execute("UPDATE research_pages SET content_id=?,stage='ready_for_generation' WHERE pdf=? AND page=?",(identity,pdf,page))
                self.db.execute("UPDATE research_archive_pages SET reason='needs_review' WHERE pdf=? AND page=?",(pdf,page))

    def test_covers_without_search_traffic_share_bounded_deduplicated_queue(self):
        period=self.period([(1,5,'2026-11-03'),(1,6,'2026-11-03'),(2,1,'2026-11-03')])
        self.context(1,5,review=True);self.context(1,6,review=True)
        result=archive_context_queue(self.db,period,3)
        self.assertEqual(result['pages'],[{'sourcePdfId':1,'page':1},{'sourcePdfId':1,'page':2},{'sourcePdfId':2,'page':1}])
        self.assertEqual(result['reviewContextPages'],2)
        self.assertEqual(len(archive_context_queue(self.db,period,1)['pages']),1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_windows WHERE pdf=1 AND page IN (1,2)').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_content').fetchone()[0],2)

    def test_newer_target_keeps_priority_over_older_review_cover(self):
        period=self.period([(1,5,'2026-11-03'),(2,1,'2026-11-04')])
        self.context(1,5,review=True)
        result=archive_context_queue(self.db,period,1)
        self.assertEqual(result['pages'],[{'sourcePdfId':2,'page':1}])
        self.assertEqual(result['reviewContextPages'],0)

    def test_known_failures_need_explicit_retry_but_batch_limit_does_not(self):
        period=self.period([(1,5,'2026-11-03')]);self.context(1,5,review=True)
        with self.db:
            for page,reason in [(1,'file_missing'),(2,'batch_byte_limit')]:
                self.db.execute('INSERT INTO research_context_attempts VALUES (?,?,?,?,?)',(1,page,reason,'proof','2026-11-04'))
        self.assertEqual(archive_context_queue(self.db,period)['pages'],[{'sourcePdfId':1,'page':2}])
        self.assertEqual(archive_context_queue(self.db,period,retry_unavailable=True)['reviewContextPages'],2)
        self.context(1,1,legacy=True)
        self.assertEqual(archive_context_queue(self.db,period,retry_unavailable=True)['pages'],[{'sourcePdfId':1,'page':2}])

    def test_live_ranking_guard_and_resolved_review_do_not_queue_covers(self):
        period=self.period([(1,5,'2026-11-03'),(2,5,'2026-11-03')])
        self.context(1,5,review=True);self.context(2,5,review=True)
        with self.db:
            record(self.db,'google','2026-11-04','2026-11-04',self.fixture.site+'en/manuals/model/1/5',3,100,'proof','fixture')
            self.db.execute("UPDATE research_archive_pages SET state='validated_draft' WHERE pdf=2")
        self.assertEqual(archive_context_queue(self.db,period)['pages'],[])

    def test_single_page_manual_does_not_request_nonexistent_second_page(self):
        period=self.period([(1,1,'2026-11-03')]);self.context(1,1,count=1,review=True)
        self.assertEqual(archive_context_queue(self.db,period)['pages'],[])


if __name__=='__main__':unittest.main()
