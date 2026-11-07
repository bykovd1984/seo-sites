import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

SEO = Path(__file__).resolve().parents[2]
TEST_ROOT = SEO.parents[1] / 'artifacts/seo-research/tests'
TEST_ROOT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SEO))
from research_hub.cli import write_config
from research_hub.service import Service
from research_hub.store import now, digest
from research_hub.collectors import collect_google, collect_bing, collect_keywords, save_keyword_snapshot, cache_key, ReportUnavailable
from research_hub.worker import work, worker_lock


class HubTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.home = Path(self.temporary.name)
        self.credential = self.home / 'google.private.json'
        self.credential.write_text('{}')
        self.bing = self.home / 'bing.private.json'
        self.bing.write_text('{"provider":"bing","api_key":"test-only-not-a-real-key"}')
        self.config = dict(schemaVersion=1, projects={
            'manuals': dict(hosts=['manuals.example'], minimumPosition=8, google=dict(property='https://manuals.example/',
                account='owner@example.com', credentialFile=str(self.credential), enabled=True)),
            'grammar': dict(hosts=['grammar.example'], languages=['en','ru'], google=dict(property='sc-domain:grammar.example',
                account='owner@example.com', credentialFile=str(self.credential), enabled=True),
                bing=dict(property='https://grammar.example/', credentialFile=str(self.bing), enabled=True))},
            semrush=dict(enabled=False, origin='https://sktiman.toolspd.com', dailyLimit=2, delaySeconds=10))
        write_config(self.home, self.config)
        self.service = Service(self.home)
        self.day = str(dt.datetime.now(dt.timezone.utc).date()-dt.timedelta(days=3))

    def tearDown(self):
        self.service.close()
        self.assertTrue(self.home.resolve().is_relative_to(TEST_ROOT.resolve()))
        self.temporary.cleanup()

    def subject(self, project='grammar', kind='topic'):
        return self.service.put_subject(project, kind, 'Present Simple exercises', 'ru',
            url=f'https://{project}.example/lesson' if kind=='page' else None,
            text='Present Simple practice with answers.', studied_language='en')['id']

    def report(self, project='grammar', position=12, query=None, observed=None, rows=None):
        return dict(provider='google', kind='queries' if query else 'pages', start=self.day, end=self.day,
            scope=dict(property=self.config['projects'][project]['google']['property'], searchType='web'),
            observedAt=observed or now(), rows=rows if rows is not None else [dict(url=f'https://{project}.example/lesson',
                clicks=2, impressions=100, position=position, **({'query':query} if query else {}))],
            sourceReference='fixture', coverage=dict(limitation='Test fixture subset'))

    def snapshot(self, keyword='present simple', country='US', label='United States', empty=False):
        from urllib.parse import urlencode
        return dict(kind='toolspd_keywordmagic_ui', schemaVersion=1,
            sourceUrl='https://sktiman.toolspd.com/analytics/keywordmagic/?'+urlencode(dict(q=keyword,db=country.lower(),type='all',mode=1)),
            heading='Keyword Magic Tool: '+keyword, countryLabel=label, observedAt=now(), pageText='',
            headers=['Keyword','Intent','Volume','KD %','CPC (USD)','Updated'],
            rows=[] if empty else [['present simple exercises','I','100','n/a','0.00','1 month']],
            tableText='Nothing found' if empty else 'present simple exercises', coverage='Rendered subset')

    def test_page_and_topic_research_without_pdf_identity(self):
        topic = self.subject()
        page = self.subject(kind='page')
        self.service.import_search('grammar', self.report(query='present simple practice'))
        bundle = self.service.bundle('grammar', topic)
        self.assertEqual(bundle['search'], {})
        self.assertTrue(bundle['rankingPolicy']['eligible'])
        self.assertEqual(bundle['subject']['studiedLanguage'], 'en')
        draft = self.service.save_decision('grammar', bundle['bundleId'], 'new_content', 'Practice intent', {'outline':['Rules','Exercises']})
        self.assertEqual(draft['status'], 'draft'); self.assertFalse(draft['published'])
        page_bundle = self.service.bundle('grammar', page)
        self.assertEqual(page_bundle['search']['queries']['rows'][0]['query'], 'present simple practice')

    def test_project_and_property_isolation(self):
        topic = self.subject()
        with self.assertRaises(ValueError): self.service.bundle('manuals', topic)
        with self.assertRaises(ValueError): self.service.import_search('manuals', self.report())
        report = self.report(); report['rows'][0]['url']='https://other.example/lesson'
        with self.assertRaises(ValueError): self.service.import_search('grammar', report)
        with self.assertRaises(ValueError): self.service.put_subject('grammar','page','Title','en',url='https://grammar.example.attacker.invalid/a')

    def test_idempotent_report_and_latest_empty_snapshot(self):
        report = self.report()
        self.assertTrue(self.service.import_search('grammar',report)['imported'])
        self.assertFalse(self.service.import_search('grammar',report)['imported'])
        self.assertEqual(len(self.service.search_rows('grammar')['rows']),1)
        self.service.import_search('grammar',self.report(rows=[],observed=report['observedAt']))
        self.assertEqual(self.service.search_rows('grammar')['rows'],[])
        self.assertEqual(len(self.service.datasets('grammar')['items']),2)

    def test_pagination_reuses_snapshot_and_latest_rank_filter(self):
        report = self.report(); report['snapshotId']='batch-one'
        self.service.import_search('grammar',report)
        second = self.report(); second['snapshotId']='batch-one'; second['rows'][0]['url']='https://grammar.example/second'
        self.service.import_search('grammar',second)
        self.assertEqual(len(self.service.search_rows('grammar')['rows']),2)
        self.service.import_search('grammar',self.report(position=3))
        self.assertEqual(self.service.search_rows('grammar',minimum_position=8)['rows'],[])

    def test_page_totals_separate_from_query_subsets(self):
        page = self.subject('manuals','page')
        self.service.import_search('manuals',self.report('manuals',position=12))
        self.service.import_search('manuals',self.report('manuals',position=2,query='small query subset'))
        self.assertTrue(self.service.bundle('manuals',page)['rankingPolicy']['eligible'])
        self.service.import_search('manuals',self.report('manuals',position=3))
        bundle = self.service.bundle('manuals',page)
        self.assertFalse(bundle['rankingPolicy']['eligible'])
        with self.assertRaises(ValueError): self.service.save_decision('manuals',bundle['bundleId'],'metadata','test',{'title':'Changed'})
        self.service.save_decision('manuals',bundle['bundleId'],'no_change','Protected ranking',{})

    def test_unknown_page_rank_and_changed_content_are_held(self):
        page = self.subject('manuals','page')
        self.assertFalse(self.service.bundle('manuals',page)['rankingPolicy']['eligible'])
        topic = self.subject(); bundle = self.service.bundle('grammar',topic)
        self.service.put_subject('grammar','topic','Present Simple exercises','ru',text='Changed source')
        with self.assertRaises(ValueError): self.service.save_decision('grammar',bundle['bundleId'],'new_content','test',{})

    def test_metric_validation_is_atomic(self):
        report=self.report(); report['rows'].append(dict(url='https://grammar.example/b',clicks=0,impressions=-1,position=9))
        with self.assertRaises(ValueError): self.service.import_search('grammar',report)
        self.assertEqual(self.service.datasets('grammar')['items'],[])
        report=self.report(); report['scope']['dimensions']=['page','query']
        with self.assertRaises(ValueError): self.service.import_search('grammar',report)

    def test_google_resume_checkpoints_and_exact_account(self):
        calls=[]
        class FakeGoogle:
            def __init__(self,path): pass
            def sites(self): return [dict(siteUrl='sc-domain:grammar.example',permissionLevel='siteOwner')]
            def call(self,url,payload=None):
                if payload is None: return dict(email='owner@example.com',email_verified=True)
                calls.append(payload)
                keys=['https://grammar.example/lesson']
                if 'query' in payload['dimensions']: keys+=['present simple']
                if 'country' in payload['dimensions']: keys+=['usa']
                return dict(rows=[dict(keys=keys,clicks=2,impressions=100,position=12)])
        job=self.service.queue_search('grammar','google',self.day,self.day,max_requests=1,dimensions=['country'])
        collect_google(self.service,job,FakeGoogle)
        self.assertEqual(self.service.jobs('grammar',job['id'])['state'],'partial')
        job=self.service.resume_job('grammar',job['id'])
        collect_google(self.service,job,FakeGoogle)
        self.assertEqual(self.service.jobs('grammar',job['id'])['state'],'done')
        self.assertEqual([c['dimensions'] for c in calls],[['page'],['page','query','country']])
        self.assertEqual(self.service.search_rows('grammar','queries')['rows'][0]['country'],'usa')
        class WrongGoogle(FakeGoogle):
            def call(self,url,payload=None): return dict(email='wrong@example.com',email_verified=True)
        with self.assertRaises(ValueError): collect_google(self.service,job,WrongGoogle)
        self.assertEqual(len(calls),2)

    def test_bing_retained_snapshot_and_bounded_resume(self):
        day=self.day; calls=[]
        class FakeBing:
            def __init__(self,key): pass
            def sites(self): return [dict(Url='https://grammar.example/')]
            def call(self,method,**kwargs):
                calls.append(method)
                return [dict(Date=day,Query='https://grammar.example/lesson' if method=='GetPageStats' else 'present simple',
                             Clicks=2,Impressions=100,AvgImpressionPosition=10)]
        job=self.service.queue_search('grammar','bing',day,day,max_requests=1)
        collect_bing(self.service,job,FakeBing)
        job=self.service.resume_job('grammar',job['id']); collect_bing(self.service,job,FakeBing)
        self.assertEqual(calls,['GetPageStats','GetPageQueryStats'])
        report=self.service.search_rows('grammar','queries',provider='bing')['rows'][0]
        self.assertEqual(report['coverage']['temporalResolution'],'provider_labelled_snapshot')
        self.assertNotIn('pages',self.service.jobs('grammar',job['id'])['progress'])

    def test_keyword_import_null_metrics_and_reuse_across_projects(self):
        topic=self.subject(); job=self.service.queue_keywords('grammar',topic,['present simple'],'US','en')
        result=self.service.import_keywords('grammar',job['id'],'present simple',self.snapshot())
        again=self.service.import_keywords('grammar',job['id'],'present simple',self.snapshot())
        self.assertEqual(result['state'],'done')
        candidates=self.service.keywords('grammar',topic)['items']
        self.assertEqual(len(candidates),1); self.assertIsNone(candidates[0]['kd'])
        other=self.subject('manuals'); other_job=self.service.queue_keywords('manuals',other,['present simple'],'US','en')
        def forbidden(settings): raise AssertionError('Cache should avoid a browser')
        collect_keywords(self.service,other_job,forbidden)
        self.assertEqual(self.service.jobs('manuals',other_job['id'])['progress']['cacheHits'],1)
        self.assertEqual(self.service.keywords('manuals',other)['total'],1)

    def test_keyword_country_mismatch_and_no_results(self):
        topic=self.subject(); job=self.service.queue_keywords('grammar',topic,['present simple'],'US','en')
        with self.assertRaises(ValueError): self.service.import_keywords('grammar',job['id'],'present simple',self.snapshot(country='UK',label='United Kingdom'))
        self.service.import_keywords('grammar',job['id'],'present simple',self.snapshot(empty=True))
        item=self.service.keywords('grammar',topic)['items'][0]
        self.assertIsNone(item['volume']); self.assertEqual(item['status'],'nothing found')

    def test_pause_requires_no_browser_and_worker_reports_blocker(self):
        topic=self.subject(); job=self.service.queue_keywords('grammar',topic,['present simple'],'US','en')
        work(self.home)
        result=self.service.jobs('grammar',job['id'])
        self.assertEqual(result['state'],'blocked')
        self.assertEqual(result['error'],'semrush_collection_paused_in_configuration')
        self.assertEqual(self.service.store.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],0)

    def test_global_daily_budget_survives_failed_attempt_and_retry(self):
        self.service.settings.data['semrush'].update(enabled=True,dailyLimit=1)
        topic=self.subject(); job=self.service.queue_keywords('grammar',topic,['present simple'],'US','en',max_age_days=0)
        class FailingBrowser:
            def __init__(self,settings): pass
            def capture(self,request): raise ReportUnavailable('login_required')
            def close(self): pass
        with self.assertRaises(ReportUnavailable): collect_keywords(self.service,job,FailingBrowser,sleeper=lambda n:None)
        with self.assertRaisesRegex(ReportUnavailable,'daily_limit_reached'):
            collect_keywords(self.service,job,FailingBrowser,sleeper=lambda n:None)
        self.assertEqual(self.service.store.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],1)

    def test_worker_recovers_search_but_holds_interrupted_browser(self):
        search=self.service.queue_search('grammar','google',self.day,self.day)
        topic=self.subject(); browser=self.service.queue_keywords('grammar',topic,['present simple'],'US','en')
        for job in (search,browser): self.service.store.update_job(job['id'],'running',{'checkpoint':'kept'})
        seen=[]
        def fake(service,job):
            seen.append(job['progress']); service.store.update_job(job['id'],'done',job['progress'])
        work(self.home,handlers={'google':fake})
        self.assertEqual(seen,[{'checkpoint':'kept'}])
        self.assertEqual(self.service.jobs('grammar',browser['id'])['state'],'blocked')
        with worker_lock(self.home) as first:
            with worker_lock(self.home) as second:
                self.assertTrue(first); self.assertFalse(second)


if __name__ == '__main__':
    unittest.main()
