import base64,json,unittest
import test_semrush_workflow
from research import bundle,import_contexts,address_literals,source_supported_query


class AddressQueryTests(unittest.TestCase):
    def setUp(self):
        fixture=test_semrush_workflow.SemrushTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.db,self.root=fixture.db,fixture.root

    def test_documented_default_addresses_are_kept_and_unsupported_addresses_stay_filtered(self):
        raw=b'<p>HP M1005 scanning. Open 192.168.0.1 for configuration.</p>'
        context=dict(type='seo_context',sourcePdfId=286733,page=69,brand='HP',models=['M1005'],readOnly=True,rawHtmlBase64=base64.b64encode(raw).decode())
        path=self.root/'address-source.jsonl';path.write_text(json.dumps(context),encoding='utf-8');import_contexts(self.db,path)
        row=self.db.execute('SELECT id,payload FROM research_windows').fetchone();payload=json.loads(row['payload'])
        for query in ('192.168.0.1 configuration','camera http://192.168.1.40/login'):
            self.db.execute('INSERT INTO research_queries VALUES (?,?,?,?,?)',(row['id'],query,1,10,12))
            payload['verified']['queries'].append(dict(query=query,clicks=1,impressions=10,position=12))
        self.db.execute('UPDATE research_windows SET payload=? WHERE id=?',(json.dumps(payload),row['id']))
        result=bundle(self.db,286733,69,allow_partial=True);window=result['searchWindows'][0]
        for queries in (window['queries'],window['payload']['verified']['queries']):
            self.assertIn('192.168.0.1 configuration',[r['query'] for r in queries])
            self.assertNotIn('camera http://192.168.1.40/login',[r['query'] for r in queries])
        self.assertEqual(window['privateAddressQueriesExcluded'],1)
        self.assertEqual(window['sourceBackedAddressQueriesRetained'],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_queries').fetchone()[0],3)

    def test_ipv6_equivalent_spellings_are_supported_but_substring_matches_are_not(self):
        source=set(address_literals('Default [fd00:0:0:0:0:0:0:1] and 192.168.0.10'))
        self.assertTrue(source_supported_query('device fd00::1 configuration',source))
        self.assertFalse(source_supported_query('device 192.168.0.1 configuration',source))

    def test_unrelated_bundles_do_not_gain_a_new_zero_counter(self):
        value=bundle(self.db,286733,69,allow_partial=True)
        self.assertNotIn('sourceBackedAddressQueriesRetained',value['searchWindows'][0])


if __name__=='__main__':unittest.main()
