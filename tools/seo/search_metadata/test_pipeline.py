import base64
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from generate import propose, generate
from history import bind_scope, checkpoint, connect, evidence, ingest, page_key, queue
from providers import Bing, Google


def row(**changes):
    return dict(dict(engine='google', start='2026-11-01', end='2026-11-01', url='https://manualsdump.com/en/manuals/hp-m1005/286733/69',
                     query='hp m1005 scanning', clicks=3, impressions=50, position=5.5), **changes)


def context():
    return dict(sourcePdfId=286733, page=69, brand='HP', models=['M1005'], headings=['Scanning a document'],
                rawHtmlBase64=base64.b64encode('<style>ignore</style><main><p>Scanning a document</p><p>Scan using the Windows software.</p></main>'.encode()).decode())


class PipelineTests(unittest.TestCase):
    def setUp(self):
        base = (Path(__file__).resolve().parents[3] / 'artifacts/search-metadata-tests').resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=base)
        assert Path(self.directory.name).resolve().is_relative_to(base)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name); self.db = connect(self.root/'history.sqlite3'); self.addCleanup(self.db.close)

    def test_aliases_and_foreign_hosts(self):
        self.assertEqual(page_key('https://www.manualsdump.com/amp/en/manuals/hp/286733/69?tracking=x'), (286733,69))
        for url in ['https://manualsdump.com.evil.test/en/manuals/hp/1/1', 'https://manualsdump.com/en/manuals/hp/1/0']:
            with self.assertRaises(ValueError): page_key(url)

    def test_idempotence_and_newest_first(self):
        ingest(self.db,[row(),row(end='2026-11-02',start='2026-11-02',url='https://manualsdump.com/en/manuals/dell/1/2')],'test')
        ingest(self.db,[row()],'rerun')
        self.assertEqual(self.db.execute('select count(*) from observations').fetchone()[0],2)
        self.assertEqual(queue(self.db,2)[0]['sourcePdfId'],1)

    def test_queue_focuses_on_observed_visits(self):
        ingest(self.db,[row(clicks=0)],'test')
        self.assertEqual(queue(self.db,2),[])
        self.assertEqual(len(queue(self.db,2,include_impressions=True)),1)

    def test_overlapping_windows_not_double_counted(self):
        ingest(self.db,[row(),row(start='2026-10-01',end='2026-11-01',clicks=100)],'test')
        rows, skipped = evidence(self.db,286733,69)
        self.assertEqual(sum(r['clicks'] for r in rows),3); self.assertEqual(len(skipped),1)

    def test_clicked_query_generates_source_supported_topic(self):
        proposal = propose(context(),[row()],[])
        self.assertEqual(proposal['status'],'active'); self.assertIn('Scanning a document',proposal['metadata']['pageTitle'])

    def test_query_selects_matching_model_in_multi_model_manual(self):
        source=context(); source['models']=['M1004','M1005']
        self.assertTrue(propose(source,[row()],[])['metadata']['pageTitle'].startswith('HP M1005:'))

    def test_query_topic_works_without_either_heading_parser(self):
        source=context(); source['headings']=[]
        source['rawHtmlBase64']=base64.b64encode(b'<main><p>The default password is documented here.</p></main>').decode()
        proposal=propose(source,[row(query='hp m1005 default password')],[])
        self.assertEqual(proposal['status'],'active'); self.assertIn('Default password',proposal['metadata']['pageTitle'])

    def test_missing_context_advances_queue_and_recheck_retries(self):
        ingest(self.db,[row()],'test'); file=self.root/'contexts.jsonl'; file.write_text('')
        generate(self.db,file,self.root/'active',[{'sourcePdfId':286733,'page':69}])
        self.assertEqual(queue(self.db,1),[]); self.assertEqual(len(queue(self.db,1,recheck=True)),1)

    def test_bing_collects_page_specific_queries_and_resumes(self):
        bing=Bing('unused'); url=row()['url']
        requests=[]
        def api(method, **fields):
            if method=='GetPageStats': return [{'Query':url,'Date':'2026-11-01','Clicks':3}]
            requests.append(method)
            self.assertEqual(fields['page'],url)
            return [{'Query':'hp m1005 scanning','Date':'2026-11-01','Clicks':3,'Impressions':50,'AvgImpressionPosition':5.5}]
        with patch.object(bing,'call',side_effect=api),patch('providers.time.sleep'):
            bing.collect(self.db,'https://manualsdump.com/',dt.date(2026,10,1),dt.date(2026,11,1),1)
            bing.collect(self.db,'https://manualsdump.com/',dt.date(2026,10,1),dt.date(2026,11,1),1)
            bing.collect(self.db,'https://manualsdump.com/',dt.date(2026,10,2),dt.date(2026,11,1),1)
        self.assertEqual(len(requests),2)
        self.assertEqual(self.db.execute('select count(*) from observations').fetchone()[0],1)

    def test_wrong_model_or_impression_only_is_not_activated(self):
        for item in [row(query='hp m9999 scanning'),row(clicks=0),row(query='hp m1005 default password'),row(query='hp m1005 scanner driver download')]:
            self.assertEqual(propose(context(),[item],[])['status'],'needs_content_review')

    def test_atomic_publication_and_older_history_cannot_replace_newer(self):
        ingest(self.db,[row()],'test'); path=self.root/'contexts.jsonl'; path.write_text(json.dumps(context()))
        output=self.root/'active'; generate(self.db,path,output)
        file=output/'733/286733/69.json'; value=json.loads(file.read_text()); value['evidenceThrough']='2026-11-03T00:00:00Z'
        file.write_text(json.dumps(value)); generate(self.db,path,output)
        self.assertEqual(json.loads(file.read_text())['evidenceThrough'],'2026-11-03T00:00:00Z')

    def test_completed_pages_allow_older_pages_to_progress_and_updates_requeue(self):
        ingest(self.db,[row(),row(start='2026-10-01',end='2026-10-01',url='https://manualsdump.com/en/manuals/1/1')],'test')
        path=self.root/'contexts.jsonl'; path.write_text(json.dumps(context())); generate(self.db,path,self.root/'active')
        self.assertEqual(queue(self.db,1)[0]['sourcePdfId'],1)
        ingest(self.db,[row()],'identical retry'); self.assertEqual(queue(self.db,1)[0]['sourcePdfId'],1)
        ingest(self.db,[row(clicks=4)],'updated metrics'); self.assertEqual(queue(self.db,1)[0]['sourcePdfId'],286733)

    def test_gsc_resumes_interrupted_day_at_committed_offset(self):
        google=Google('unused'); fake={'keys':[row()['url'],row()['query']],'clicks':3,'impressions':50,'position':5.5}
        with patch.object(google,'call',side_effect=[{'rows':[fake]*25000},RuntimeError('interrupted')]), patch('providers.time.sleep'):
            with self.assertRaises(RuntimeError): google.collect(self.db,'https://manualsdump.com/',dt.date(2026,11,1),dt.date(2026,11,1),1)
        with patch.object(google,'call',return_value={'rows':[]}) as request, patch('providers.time.sleep'):
            google.collect(self.db,'https://manualsdump.com/',dt.date(2026,11,1),dt.date(2026,11,1),1)
            self.assertEqual(request.call_args.args[1]['startRow'],25000)

    def test_gsc_page_average_is_fetched_separately_and_resumes(self):
        google=Google('unused');bind_scope(self.db,'google','https://manualsdump.com/')
        ingest(self.db,[row(position=20)],'gsc-api-web-final')
        checkpoint(self.db,'google:web:https://manualsdump.com/:2026-11-01',dict(done=True));self.db.commit()
        with patch.object(google,'call',return_value={'rows':[dict(clicks=3,impressions=70,position=4)]}) as api,patch('providers.time.sleep'):
            google.collect_page_metrics(self.db,'https://manualsdump.com/',dt.date(2026,11,1),dt.date(2026,11,1),1)
            payload=api.call_args.args[1]
            self.assertEqual(payload['dimensions'],[])
            self.assertEqual(payload['dimensionFilterGroups'][0]['filters'][0],
                             dict(dimension='page',operator='equals',expression=row()['url']))
            google.collect_page_metrics(self.db,'https://manualsdump.com/',dt.date(2026,11,1),dt.date(2026,11,1),1)
            self.assertEqual(api.call_count,1)
        self.assertEqual(self.db.execute('SELECT position FROM api_page_metrics').fetchone()[0],4)
        self.assertEqual(self.db.execute('SELECT position FROM observations').fetchone()[0],20)

    def test_page_inventory_discovers_traffic_without_any_query_rows(self):
        google=Google('unused')
        def api(url,payload):
            self.assertEqual(payload['dimensions'],['page'])
            return dict(rows=[dict(keys=[row()['url']],clicks=4,impressions=70,position=12)])
        with patch.object(google,'call',side_effect=api) as request,patch('providers.time.sleep'):
            google.collect_page_inventory(self.db,'https://manualsdump.com/',dt.date(2026,11,1),dt.date(2026,11,1),1)
            google.collect_page_inventory(self.db,'https://manualsdump.com/',dt.date(2026,11,1),dt.date(2026,11,1),1)
            self.assertEqual(request.call_count,1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT clicks FROM api_page_metrics').fetchone()[0],4)
        checkpoint(self.db,'google:web:https://manualsdump.com/:2026-11-01',dict(done=True));self.db.commit()
        with patch.object(google,'call',return_value=dict(rows=[dict(clicks=4,impressions=80,position=11)])) as request,patch('providers.time.sleep'):
            google.collect_page_metrics(self.db,'https://manualsdump.com/',dt.date(2026,11,1),dt.date(2026,11,1),1)
            self.assertEqual(request.call_args.args[1]['dimensions'],[])

    def test_gsc_pagination_restart_and_newest_day_first(self):
        google=Google('unused'); calls=[]
        fake={'keys':[row()['url'],row()['query']],'clicks':3,'impressions':50,'position':5.5}
        def response(url, body):
            calls.append((body['endDate'],body['startRow']))
            return {'rows':[fake]*25000 if body['startRow']==0 else []}
        with patch.object(google,'call',side_effect=response), patch('providers.time.sleep'):
            google.collect(self.db,'https://manualsdump.com/',dt.date(2026,10,31),dt.date(2026,11,1),1)
            self.assertEqual(calls,[('2026-11-01',0),('2026-11-01',25000)])
            calls.clear(); google.collect(self.db,'https://manualsdump.com/',dt.date(2026,10,31),dt.date(2026,11,1),1)
            self.assertEqual(calls[0],('2026-10-31',0))


if __name__=='__main__': unittest.main()
