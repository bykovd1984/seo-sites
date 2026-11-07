import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from export_runtime import export
from history import connect
from ranking_policy import eligibility, record
from research import ROOT, bundle, generation_queue, import_generation, init, start_run
from semrush_workflow import collect, init as init_semrush, plan
import test_research


class RankingPolicyTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'artifacts/search-metadata-tests';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=connect(self.root/'research.sqlite3');self.addCleanup(self.db.close)
        init_semrush(self.db);start_run(self.db,'test')
        self.fixture=test_research.ResearchTests()
        self.fixture.root=self.root;self.fixture.db=self.db
        self.fixture.url='https://manualsdump.com/en/manuals/hp-m1005/286733/69'
        self.request=self.fixture.ready()

    def rank(self,value,engine='google',start='2026-11-01',end='2026-11-03',url=None,impressions=50):
        record(self.db,engine,start,end,url or self.fixture.url,value,impressions,'test-proof-'+str(value),'test_page_aggregate')

    def test_inclusive_eight_boundary_and_unknown_values(self):
        for value,allowed in [(7.999,False),(8,True),(8.001,True),(40,True),(None,False),(0,False),(float('nan'),False)]:
            with self.subTest(position=value):
                self.rank(value)
                self.assertEqual(eligibility(self.db,286733,69)['eligible'],allowed)

    def test_query_positions_are_not_used_as_page_average(self):
        # The fixture has query position 4 and reported page position 12.
        self.assertTrue(eligibility(self.db,286733,69)['eligible'])
        self.rank(None)
        self.assertFalse(eligibility(self.db,286733,69)['eligible'])
        with self.assertRaisesRegex(ValueError,'page_position_unknown'): bundle(self.db,286733,69,True)

    def test_top_position_in_either_engine_protects_whole_page(self):
        self.rank(3,engine='bing')
        result=eligibility(self.db,286733,69)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['reason'],'protected_top_positions')
        self.assertEqual(generation_queue(self.db,10,self.root/'bundles'),[])

    def test_newer_period_and_alias_have_independent_protection(self):
        self.rank(2,start='2026-10-01',end='2026-10-20')
        self.assertTrue(eligibility(self.db,286733,69)['eligible'])
        self.rank(3,start='2026-11-04',end='2026-11-04')
        self.assertFalse(eligibility(self.db,286733,69)['eligible'])
        self.rank(20,start='2026-11-04',end='2026-11-04')
        self.rank(2,url=self.fixture.url.replace('/en/','/amp/en/'))
        self.assertFalse(eligibility(self.db,286733,69)['eligible'])

    def query_only_window(self,engine='bing',url=None):
        import json
        row=dict(self.db.execute('SELECT * FROM research_windows LIMIT 1').fetchone())
        row.update(id='query-only-'+engine+str(url),engine=engine,start='2026-11-04',end='2026-11-04')
        payload=json.loads(row['payload']);payload['verified']['url']=url or self.fixture.url
        row['payload']=json.dumps(payload)
        columns=list(row)
        self.db.execute('INSERT INTO research_windows ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row[c] for c in columns))

    def test_new_query_report_does_not_erase_a_reported_page_average(self):
        self.rank(8,engine='bing',start='2026-09-18',end='2026-09-18')
        self.query_only_window()
        result=eligibility(self.db,286733,69)
        self.assertTrue(result['eligible'])
        bing=next(r for r in result['observations'] if r['engine']=='bing')
        self.assertEqual((bing['position'],bing['end']),(8,'2026-09-18'))

    def test_new_query_report_cannot_hide_a_protected_page_position(self):
        self.rank(3,engine='bing',start='2026-09-18',end='2026-09-18')
        self.query_only_window()
        self.assertEqual(eligibility(self.db,286733,69)['reason'],'protected_top_positions')

    def test_query_only_scopes_without_page_measurements_stay_unknown(self):
        self.query_only_window()
        self.assertEqual(eligibility(self.db,286733,69)['reason'],'page_position_unknown')
        self.rank(8,engine='bing')
        self.query_only_window(engine='google',url=self.fixture.url.replace('/en/','/amp/en/'))
        self.assertEqual(eligibility(self.db,286733,69)['reason'],'page_position_unknown')

    def test_explicit_new_unknown_page_report_still_blocks_generation(self):
        self.rank(8,engine='bing',start='2026-09-18',end='2026-09-18')
        self.rank(None,engine='bing',start='2026-11-04',end='2026-11-04')
        self.query_only_window()
        self.assertEqual(eligibility(self.db,286733,69)['reason'],'page_position_unknown')

    def test_preexisting_draft_and_paid_job_rechecked_before_use(self):
        plan(self.db,'US','2026-11',1,1);self.db.commit()
        import_generation(self.db,self.fixture.response(self.request))
        self.rank(5);self.db.commit()
        transport=Mock()
        result=collect(self.db,self.root/'api','fake-key',True,1000,transport=transport)
        self.assertEqual(result['reservedUnits'],0);transport.assert_not_called()
        snapshot=export(self.db,self.root/'runtime')
        self.assertEqual(snapshot['exportedPages'],0)
        self.assertEqual(snapshot['heldPages'],1)
        self.assertIn('protected_top_positions',snapshot['held'][0]['reason'])

    def test_zero_impressions_cannot_qualify(self):
        self.rank(10,impressions=0)
        self.assertFalse(eligibility(self.db,286733,69)['eligible'])


if __name__=='__main__': unittest.main()
