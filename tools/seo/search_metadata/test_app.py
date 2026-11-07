import datetime as dt
import base64
import json
import tempfile
import unittest
from dataclasses import replace
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from app import ImportSettings, import_data, provider_key
from history import bind_scope, checkpoint, connect, ingest, ingest_page_metrics
from import_api_history import import_history
from research import ROOT, import_generation
from semrush_workflow import collect, init
from model_stage import page_bundle
from generate import atomic_json


class AppTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'artifacts/search-metadata-tests';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=connect(self.root/'research.sqlite3');self.addCleanup(self.db.close)
        init(self.db);self.db.commit()
        self.settings=ImportSettings(dt.date(2026,11,1),dt.date(2026,11,1),providers=('google',),
                                     approved=True,gsc_credentials=Path('fake-account-credentials.json'))
        self.url='https://manualsdump.com/en/manuals/hp-m1005/286733/69'

    def google(self,email='debsites2@gmail.com',site='https://manualsdump.com/'):
        provider=Mock();provider.call.return_value=dict(email=email,email_verified=True)
        provider.sites.return_value=[dict(siteUrl=site,permissionLevel='siteOwner')]
        def queries(history,site,start,end,max_days):
            bind_scope(history,'google',site)
            ingest(history,[dict(engine='google',start=str(start),end=str(end),url=self.url,
                                query='hp scanning',clicks=3,impressions=20,position=5)],'gsc-api-web-final')
            checkpoint(history,'google:web:'+site+':'+str(start),dict(done=True));history.commit()
        def positions(history,site,start,end,max_pages):
            ingest_page_metrics(history,'google',site,str(start),str(end),self.url,3,80,12,
                                dict(source='mocked exact page aggregate'));history.commit()
        provider.collect.side_effect=queries;provider.collect_page_metrics.side_effect=positions
        return provider

    def run_import(self,settings,provider):
        return import_data(self.db,self.root/'history.sqlite3',self.root/'run',settings,google_factory=Mock(return_value=provider))

    def test_archive_retains_search_history_before_research_preparation(self):
        provider = self.google()
        result = self.run_import(replace(self.settings, archive_only=True), provider)
        self.assertTrue(result['providers']['google']['batchSucceeded'])
        self.assertEqual(result['stage'], 'search_history_archive')
        with closing(connect(self.root/'history.sqlite3')) as history:
            self.assertEqual(history.execute('SELECT query FROM observations').fetchone()[0], 'hp scanning')
        provider.collect_page_metrics.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_requests').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM semrush_jobs').fetchone()[0], 0)

    def test_date_bound_import_persists_rows_positions_and_restarts(self):
        provider=self.google();first=self.run_import(self.settings,provider)
        self.assertTrue(first['providers']['google']['batchSucceeded'])
        self.assertEqual(first['historyImport']['importedWindows'],1)
        self.assertEqual(first['historyImport']['importedPageMetrics'],1)
        self.assertTrue(first['semrushCollection']['skipped'])
        self.assertFalse(first['fullHistoryVerified'])
        self.assertFalse(first['productionChanged'])
        self.assertEqual(self.run_import(self.settings,provider)['historyImport']['importedWindows'],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_windows').fetchone()[0],1)

    def test_wrong_account_or_property_never_collects_data(self):
        for provider in [self.google(email='another@example.com'),self.google(site='https://evilmanualsdump.com/')]:
            result=self.run_import(self.settings,provider)
            self.assertFalse(result['providers']['google']['batchSucceeded'])
            provider.collect.assert_not_called();provider.collect_page_metrics.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_windows').fetchone()[0],0)

    def test_google_uses_saved_default_without_generic_account_fallback(self):
        settings=replace(self.settings,gsc_credentials=None)
        factory=Mock(return_value=self.google());path=self.root/'google.private.json'
        with patch.dict('os.environ',{'GOOGLE_APPLICATION_CREDENTIALS':'unrelated.json'},clear=True), \
             patch('app.credential_path',return_value=path) as lookup:
            result=import_data(self.db,self.root/'history.sqlite3',self.root/'run',settings,google_factory=factory)
        self.assertTrue(result['providers']['google']['batchSucceeded'])
        factory.assert_called_once_with(str(path));lookup.assert_called_once_with('google')

    def test_approval_and_bounds_checked_before_provider_creation(self):
        factory=Mock()
        for settings in [replace(self.settings,approved=False),replace(self.settings,end=dt.date(2026,10,1))]:
            with self.assertRaises(ValueError):
                import_data(self.db,self.root/'history.sqlite3',self.root/'run',settings,google_factory=factory)
        factory.assert_not_called()

    def test_saved_history_outside_period_is_not_imported(self):
        with closing(connect(self.root/'history.sqlite3')) as history, history:
            bind_scope(history,'google',self.settings.site)
            for date in ('2026-10-31','2026-11-01'):
                ingest(history,[dict(engine='google',start=date,end=date,url=self.url,
                        query='hp scanning',clicks=2,impressions=10,position=5)],'gsc-api-web-final')
                checkpoint(history,'google:web:'+self.settings.site+':'+date,dict(done=True))
        result=import_history(self.db,self.root/'history.sqlite3',self.root/'evidence',start='2026-11-01',end='2026-11-01')
        self.assertEqual(result['importedWindows'],1)
        self.assertEqual(self.db.execute('SELECT start FROM research_windows').fetchone()[0],'2026-11-01')

    def test_private_key_file_is_scoped_to_the_provider(self):
        path=self.root/'bing.private.json';atomic_json(path,dict(provider='bing',api_key='fake-test-key'))
        self.assertEqual(provider_key('bing',path),'fake-test-key')
        with self.assertRaisesRegex(ValueError,'Invalid provider'): provider_key('semrush',path)
        with self.assertRaisesRegex(ValueError,'missing'): provider_key('bing',self.root/'missing.private.json')

    def test_inventory_only_page_completes_import_to_sol_without_invented_queries(self):
        provider=self.google()
        def inventory(history,site,start,end,max_days):
            bind_scope(history,'google',site)
            ingest_page_metrics(history,'google',site,str(start),str(end),self.url,3,80,12,
                                dict(kind='page_inventory',mocked=True));history.commit()
        def no_queries(history,site,start,end,max_days):
            checkpoint(history,'google:web:'+site+':'+str(start),dict(done=True));history.commit()
        provider.collect_page_inventory.side_effect=inventory;provider.collect.side_effect=no_queries
        contexts=self.root/'contexts.jsonl'
        atomic_json(contexts,dict(type='seo_context',sourcePdfId=286733,manualId=1286733,page=69,pageCount=100,
            readOnly=True,brand='HP',models=['M1005'],rawHtmlBase64=base64.b64encode(
                b'<h2>Scanning a document</h2><p>HP M1005 supports scanning at 300 dpi.</p>').decode()))
        result=self.run_import(replace(self.settings,contexts=contexts,semrush_source='api'),provider)
        self.assertTrue(result['providers']['google']['batchSucceeded'])
        self.assertEqual(result['historyImport']['importedWindows'],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queries').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'semrush_pending')
        def metrics(request,api_key):
            return json.dumps(dict(meta=dict(success=True,country=request['country'],month=request['month'],keyword=request['keyword']),
                                   data=dict(search_volume=10,keyword_difficulty=12)))
        collect(self.db,self.root/'semrush','fake-key',True,20,transport=metrics)
        request=page_bundle(self.db,286733,69);candidate=request['semrushCandidates'][0]
        self.assertEqual(candidate['seedSources'][0]['kind'],'content_derived')
        response=self.root/'model-response.json'
        atomic_json(response,dict(requestId=request['requestId'],model='gpt-6.1-sol',effort='medium',
            pageTitle='HP M1005 scanning',h1Heading='HP M1005 scanning',pageDescription='Scanning a document at 300 dpi.',
            requiresReview=False,selectedKeywords=[candidate['metrics']['keyword']],
            contentEvidence=['HP M1005 supports scanning at 300 dpi.'],keywordDecisions=[dict(
                candidateId=candidate['candidateId'],decision='keep',reason='Exact scanning topic',
                contentEvidence=['HP M1005 supports scanning at 300 dpi.'])]))
        self.assertEqual(import_generation(self.db,response,self.root/'runtime')['status'],'validated_draft')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM semrush_reviews').fetchone()[0],0)
        self.assertTrue((self.root/'runtime/733/286733/69.json').is_file())


if __name__=='__main__': unittest.main()
