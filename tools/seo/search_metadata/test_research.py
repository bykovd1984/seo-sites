import base64
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from history import connect
from research import ROOT, artifact, bing_export, bundle, context_queue, generation_queue, gsc_export, import_contexts, import_generation, import_inventory, import_inventory_ui, import_keyword_evidence, import_page, init, request_signature, research_queue, resolve_ui_urls, start_run


class ResearchTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'artifacts/search-metadata-tests';base.mkdir(parents=True,exist_ok=True)
        temporary=tempfile.TemporaryDirectory(dir=base)
        assert Path(temporary.name).resolve().is_relative_to(base.resolve())
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.db=connect(self.root/'research.sqlite3');self.addCleanup(self.db.close)
        init(self.db);start_run(self.db,'test')
        self.url='https://manualsdump.com/en/manuals/hp-m1005/286733/69'

    def save(self,name,value):
        path=self.root/name;path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');return path

    def export(self,name='report.zip',url=None,start='2026-11-01',end='2026-11-03',query_clicks=2):
        path=self.root/name
        tables={'Filters.csv':[['Filter','Value'],['Page',url or self.url]],
                'Chart.csv':[['Date','Clicks'],[start,1],[end,1]],
                'Pages.csv':[['Top pages','Clicks','Impressions','Position'],[url or self.url,3,50,12]],
                'Queries.csv':[['Top queries','Clicks','Impressions','Position'],['hp m1005 scanning',query_clicks,5,4]]}
        with zipfile.ZipFile(path,'w') as archive:
            for name,rows in tables.items():
                stream=io.StringIO();csv.writer(stream).writerows(rows);archive.writestr(name,stream.getvalue())
        return path

    def manifest(self,**changes):
        self.export();proof=self.root/'semrush.txt';proof.write_text('Visible US report: Nothing found',encoding='utf-8')
        value=dict(engine='GSC',start='2026-11-01',end='2026-11-03',sourcePdfId=286733,page=69,url=self.url,
                   observedClicks=3,observedImpressions=50,rawExport='report.zip',coverage='Disclosed subset',
                   semrush=[dict(seed='hp m1005 scanning',keyword='hp m1005 scanning',countryDatabase='US',volume=None,kd=None,
                                 sourceUrl='https://www.semrush.com/',observedAt='2026-11-05T00:00:00Z',status='Nothing found',
                                 proofArtifact='semrush.txt',relevance='Content supported')])
        value.update(changes);return self.save('page.json',value)

    def ready(self):
        import_page(self.db,self.manifest(),'test')
        raw='<p>Scanning a document with HP M1005. Resolution 300 dpi.</p>'
        source=dict(type='seo_context',sourcePdfId=286733,page=69,brand='HP',models=['M1005'],readOnly=True,
                    rawHtmlBase64=base64.b64encode(raw.encode()).decode())
        path=self.root/'context.jsonl';path.write_text(json.dumps(source),encoding='utf-8');import_contexts(self.db,path)
        return bundle(self.db,286733,69)

    def response(self,request,**changes):
        result=dict(requestId=request['requestId'],model='gpt-6.1-sol',effort='medium',pageTitle='HP M1005 scanning',
                    h1Heading='HP M1005 scanning',pageDescription='Scanning a document at 300 dpi.',
                    requiresReview=False,contentEvidence=['Scanning a document with HP M1005.'])
        result.update(changes);return self.save('response.json',result)

    def test_global_query_join_and_wrong_page_are_rejected(self):
        wrong=self.export(url='https://manualsdump.com/en/manuals/hp/286733/68')
        with self.assertRaisesRegex(ValueError,'exact page'): gsc_export(wrong,286733,69,'2026-11-01','2026-11-03')
        with zipfile.ZipFile(self.root/'global.zip','w') as archive:
            archive.writestr('Pages.csv','Top pages,Clicks,Impressions\n'+self.url+',3,50\n')
        with self.assertRaises(ValueError): gsc_export(self.root/'global.zip',286733,69,'2026-11-01','2026-11-03')

    def test_partial_inventory_ui_is_idempotent_and_separate_from_exports(self):
        value=dict(kind='partial_gsc_page_inventory_ui_transcription',property='https://manualsdump.com/',searchType='Web',
                   start='2026-09-23',end='2026-09-29',reportedPageRows=644,visibleRows=1,
                   siteTotals=dict(clicks=19,impressionsApproximate=1240),
                   pages=[dict(label='HP',sourcePdfId=286733,page=69,clicks=4,impressions=12)],coverage='partial')
        path=self.save('inventory-ui.json',value); first=import_inventory_ui(self.db,path);second=import_inventory_ui(self.db,path)
        self.assertTrue(first['inserted']);self.assertFalse(second['inserted'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_inventory_ui_observations').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_inventory').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_discovered_pages').fetchone()[0],0)
        value['visibleRows']=2;self.save('inventory-ui.json',value)
        with self.assertRaisesRegex(ValueError,'row count'): import_inventory_ui(self.db,path)

    def test_partial_inventory_queue_orders_deduplicates_and_requires_url_resolution(self):
        value=dict(kind='partial_gsc_page_inventory_ui_transcription',property='https://manualsdump.com/',searchType='Web',
                   start='2026-09-23',end='2026-09-29',reportedPageRows=10,visibleRows=2,
                   siteTotals=dict(clicks=19,impressionsApproximate=1240),
                   pages=[dict(label='A',sourcePdfId=1,page=2,clicks=4,impressions=12),
                          dict(label='B',sourcePdfId=3,page=4,clicks=1,impressions=3)])
        path=self.save('inventory-ui.json',value);import_inventory_ui(self.db,path)
        value['coverage']='another observation';self.save('inventory-ui.json',value);import_inventory_ui(self.db,path)
        self.db.execute('INSERT INTO research_inventory VALUES (?,?,?,?,?,?,?)',('i','bing','2026-10-29','2026-11-04','raw',1,''))
        self.db.execute('INSERT INTO research_discovered_pages VALUES (?,?,?,?,?,?)',('i',286733,69,self.url,1,5))
        rows=research_queue(self.db,10);self.assertEqual([x['pdf'] for x in rows],[286733,1,3])
        self.assertIsNone(rows[1]['url']);self.assertTrue(rows[1]['urlResolutionRequired']);self.assertTrue(rows[1]['partialCoverage'])
        self.assertEqual(rows[1]['clicks'],4)
        self.db.execute('INSERT INTO research_inventory VALUES (?,?,?,?,?,?,?)',('g','google','2026-09-23','2026-09-29','raw',1,''))
        self.db.execute('INSERT INTO research_discovered_pages VALUES (?,?,?,?,?,?)',('g',1,2,'https://manualsdump.com/en/manuals/a/1/2',4,12))
        rows=research_queue(self.db,10);self.assertEqual(len(rows),3);self.assertEqual(rows[1]['inventory_id'],'g')

    def test_ui_url_resolution_is_independent_idempotent_and_refuses_ambiguity(self):
        value=dict(kind='partial_gsc_page_inventory_ui_transcription',property='https://manualsdump.com/',searchType='Web',
                   start='2026-09-23',end='2026-09-29',reportedPageRows=1,visibleRows=1,
                   siteTotals=dict(clicks=1,impressionsApproximate=1),
                   pages=[dict(label='HP',sourcePdfId=286733,page=69,clicks=1,impressions=1)])
        import_inventory_ui(self.db,self.save('inventory-ui.json',value))
        self.db.execute('INSERT INTO research_inventory VALUES (?,?,?,?,?,?,?)',('i','bing','2026-10-29','2026-11-04','raw',1,''))
        self.db.execute('INSERT INTO research_discovered_pages VALUES (?,?,?,?,?,?)',('i',286733,69,self.url,1,1))
        self.assertEqual(resolve_ui_urls(self.db)['added'],1);self.assertEqual(resolve_ui_urls(self.db)['added'],0)
        ui=next(x for x in research_queue(self.db,10) if x.get('partialCoverage'))
        self.assertEqual(ui['url'],self.url);self.assertEqual(ui['urlResolutionSource']['inventoryId'],'i')
        self.assertFalse(ui['urlResolutionRequired']);self.assertTrue(ui['pageFilterVerificationRequired'])
        self.db.execute('INSERT INTO research_inventory VALUES (?,?,?,?,?,?,?)',('j','google','2026-11-01','2026-11-03','raw2',1,''))
        alternate='https://manualsdump.com/amp/en/manuals/hp-m1005/286733/69'
        self.db.execute('INSERT INTO research_discovered_pages VALUES (?,?,?,?,?,?)',('j',286733,69,alternate,1,1))
        self.assertEqual(resolve_ui_urls(self.db)['ambiguous'],1)
        ui=next(x for x in research_queue(self.db,10) if x.get('partialCoverage'))
        self.assertIsNone(ui['url']);self.assertTrue(ui['urlResolutionRequired'])

    def test_context_queue_resumes_and_retries_unavailable(self):
        self.db.execute('INSERT INTO research_inventory VALUES (?,?,?,?,?,?,?)',('i','google','2026-11-01','2026-11-03','x',2,''))
        for page in (1,2): self.db.execute('INSERT INTO research_discovered_pages VALUES (?,?,?,?,?,?)',('i',286733,page,self.url,3,5))
        self.assertEqual([x['page'] for x in context_queue(self.db,10)],[1,2])
        path=self.root/'missing.jsonl';path.write_text(json.dumps(dict(type='legacy_source_unavailable',sourcePdfId=286733,page=1,reason='file_missing')))
        import_contexts(self.db,path)
        self.assertEqual([x['page'] for x in context_queue(self.db,10)],[2])
        self.assertEqual([x['page'] for x in context_queue(self.db,10,True)],[1,2])
        path.write_text(json.dumps(dict(type='legacy_source_unavailable',sourcePdfId=286733,page=1,reason='batch_byte_limit')))
        import_contexts(self.db,path)
        self.assertEqual([x['page'] for x in context_queue(self.db,10)],[1,2])

    def test_report_dates_cannot_be_mislabeled(self):
        path=self.export(start='2026-10-31')
        with self.assertRaisesRegex(ValueError,'date'): gsc_export(path,286733,69,'2026-11-01','2026-11-03')

    def test_raw_queries_and_undisclosed_totals_are_separate(self):
        manifest=self.manifest(queries=[dict(query='fabricated',clicks=999,impressions=999)])
        import_page(self.db,manifest,'test');import_page(self.db,manifest,'test')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_windows').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT query FROM research_queries').fetchone()[0],'hp m1005 scanning')
        self.assertEqual(self.db.execute('SELECT page_clicks FROM research_windows').fetchone()[0],3)
        self.assertEqual(self.db.execute('SELECT SUM(clicks) FROM research_queries').fetchone()[0],2)

    def test_bing_transcription_keeps_provenance_and_rejects_mismatched_dates(self):
        data=dict(kind='bing_ui_transcription',url=self.url,start='2026-11-01',end='2026-11-03',
                  observedClicks=3,observedImpressions=50,queries=[dict(query='hp m1005 scanning',clicks=2,impressions=5,position=4)])
        self.save('visible.json',data); (self.root/'proof.txt').write_text('Visible exact page filter')
        manifest=self.manifest(engine='Bing',sourceType='bing_ui_transcription',rawExport='visible.json',
                               pageFilterVerified=True,pageFilterProofArtifact='proof.txt')
        data['end']='2026-11-02';self.save('visible.json',data)
        with self.assertRaisesRegex(ValueError,'date provenance'): import_page(self.db,manifest,'test')
        data['end']='2026-11-03';self.save('visible.json',data);import_page(self.db,manifest,'test')
        payload=json.loads(self.db.execute('SELECT payload FROM research_windows').fetchone()[0])
        self.assertEqual(payload['verified']['sourceType'],'bing_ui_transcription')
        self.assertEqual(self.db.execute('SELECT query FROM research_queries').fetchone()[0],'hp m1005 scanning')

    def test_gsc_page_ui_transcription_requires_property_filter_and_keeps_partial_totals(self):
        data=dict(kind='gsc_ui_transcription',property='https://manualsdump.com/',searchType='Web',url=self.url,
                  start='2026-11-01',end='2026-11-03',observedClicks=3,observedImpressions=50,
                  queries=[dict(query='hp m1005 scanning',clicks=2,impressions=5,position=None)])
        self.save('gsc-visible.json',data); (self.root/'proof.txt').write_text('Visible exact page filter')
        path=self.manifest(sourceType='gsc_ui_transcription',rawExport='gsc-visible.json',pageFilterVerified=True,pageFilterProofArtifact='proof.txt')
        data['property']='https://example.com/';self.save('gsc-visible.json',data)
        with self.assertRaisesRegex(ValueError,'property'): import_page(self.db,path,'test')
        data['property']='https://manualsdump.com/';self.save('gsc-visible.json',data);import_page(self.db,path,'test')
        row=self.db.execute('SELECT page_clicks,page_impressions,payload FROM research_windows').fetchone()
        self.assertEqual((row['page_clicks'],row['page_impressions']),(3,50))
        self.assertEqual(json.loads(row['payload'])['verified']['sourceType'],'gsc_ui_transcription')
        self.assertEqual(self.db.execute('SELECT SUM(clicks) FROM research_queries').fetchone()[0],2)

    def test_bundle_excludes_private_address_queries_from_both_copies(self):
        self.ready()
        row=self.db.execute('SELECT id,payload FROM research_windows').fetchone()
        private='camera http://192.168.1.40/login'
        self.db.execute('INSERT INTO research_queries VALUES (?,?,?,?,?)',(row['id'],private,1,1,2))
        payload=json.loads(row['payload'])
        payload['verified']['queries'].append(dict(query=private,clicks=1,impressions=1,position=2))
        self.db.execute('UPDATE research_windows SET payload=? WHERE id=?',(json.dumps(payload),row['id']))
        result=bundle(self.db,286733,69)
        self.assertNotIn(private,json.dumps(result))
        self.assertEqual(result['searchWindows'][0]['privateAddressQueriesExcluded'],1)
        self.assertEqual(result['searchWindows'][0]['queries'][0]['query'],'hp m1005 scanning')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queries WHERE query=?',(private,)).fetchone()[0],1)

    def test_missing_semrush_metrics_remain_null_and_country_bound(self):
        self.ready();row=self.db.execute('SELECT * FROM research_keywords').fetchone()
        self.assertIsNone(row['volume']);self.assertIsNone(row['kd']);self.assertEqual(row['country_database'],'us')
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'ready_for_generation')

    def test_keyword_only_requires_exact_discovery_and_context_and_never_creates_window(self):
        import hashlib
        raw='<p>Scanning a document with HP M1005.</p>'; sha=hashlib.sha256(raw.encode()).hexdigest()
        context=self.root/'context.jsonl';context.write_text(json.dumps(dict(type='seo_context',sourcePdfId=286733,page=69,
                   rawHtmlBase64=base64.b64encode(raw.encode()).decode())))
        import_contexts(self.db,context)
        proof=self.root/'keywords.txt';proof.write_text('US: Nothing found')
        item=dict(seed='hp m1005 scanning',keyword='hp m1005 scanning',countryDatabase='US',volume=None,kd=None,
                  sourceUrl='https://www.semrush.com/',observedAt='2026-11-05',status='Nothing found',
                  relevance='Page topic',proofArtifact='keywords.txt')
        m=dict(sourcePdfId=286733,page=69,url=self.url,contentSha256=sha,semrush=[item]); path=self.save('keyword.json',m)
        with self.assertRaisesRegex(ValueError,'discovered URL'): import_keyword_evidence(self.db,path)
        self.db.execute('INSERT INTO research_discovered_pages VALUES (?,?,?,?,?,?)',('i',286733,69,self.url,2,5))
        m['contentSha256']='0'*64;path=self.save('keyword.json',m)
        with self.assertRaisesRegex(ValueError,'context hash'): import_keyword_evidence(self.db,path)
        m['contentSha256']=sha;path=self.save('keyword.json',m)
        self.assertEqual(import_keyword_evidence(self.db,path)['inserted'],1)
        self.assertEqual(import_keyword_evidence(self.db,path)['inserted'],0)
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'search_evidence_pending')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_windows').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queries').fetchone()[0],0)
        self.assertIsNone(self.db.execute('SELECT volume FROM research_keywords').fetchone()[0])
        self.assertEqual(generation_queue(self.db,10,self.root/'bundles'),[])
        with self.assertRaises(ValueError): bundle(self.db,286733,69)
        with self.assertRaisesRegex(ValueError,'search report'): bundle(self.db,286733,69,allow_partial=True)
        item['proofArtifact']='missing.txt';path=self.save('keyword.json',m)
        with self.assertRaisesRegex(ValueError,'proof'): import_keyword_evidence(self.db,path)
        import_page(self.db,self.manifest(semrush=[]),'test')
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'ready_for_generation')
        import_page(self.db,self.manifest(semrush=[],identityReviewRequired=True),'test')
        item['proofArtifact']='keywords.txt';path=self.save('keyword.json',m)
        import_keyword_evidence(self.db,path)
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'identity_review')

    def test_bing_positions_come_from_raw_export(self):
        path=self.root/'bing.csv';path.write_text('Keyword,Impressions,Clicks,Avg. Position\nscanning,6,2,2.6667\n',encoding='utf-8')
        page=dict(url=self.url,pageFilterVerified=True,pageFilterProofArtifact='proof.txt',observedClicks=3,observedImpressions=9)
        result=bing_export(path,page)
        self.assertEqual(result['queries'][0]['position'],2.6667);self.assertEqual(result['exportedClicks'],2)
        page.pop('pageFilterProofArtifact')
        with self.assertRaisesRegex(ValueError,'provenance'): bing_export(path,page)

    def test_source_artifact_is_immutable_and_credentials_rejected(self):
        path=self.root/'proof.txt';path.write_text('original');ident=artifact(self.db,path,'test')
        archived=Path(self.db.execute('SELECT path FROM research_artifacts WHERE id=?',(ident,)).fetchone()[0])
        path.write_text('changed');self.assertEqual(archived.read_text(),'original')
        secret=self.root/'token.private.json';secret.write_text('{}')
        with self.assertRaisesRegex(ValueError,'Credentials'): artifact(self.db,secret,'test')

    def test_newest_nonoverlapping_windows_only(self):
        self.ready()
        path=self.manifest(start='2026-10-01',end='2026-11-03')
        self.export(start='2026-10-01')
        import_page(self.db,path,'test');request=bundle(self.db,286733,69)
        self.assertEqual(sum(w['selectedForGeneration'] for w in request['searchWindows']),1)

    def test_amp_and_regular_query_reports_remain_separate(self):
        self.ready();url=self.url.replace('/en/','/amp/en/')
        path=self.manifest(url=url);self.export(url=url);import_page(self.db,path,'test')
        request=bundle(self.db,286733,69)
        self.assertEqual(sum(w['selectedForGeneration'] for w in request['searchWindows']),2)

    def test_model_and_unsupported_numeric_claims_rejected(self):
        request=self.ready()
        for changes in [dict(model='other'),dict(pageDescription='Scanning at 30 dpi.'),dict(contentEvidence=['unsupported fact'])]:
            with self.assertRaises(ValueError): import_generation(self.db,self.response(request,**changes))

    def test_hash_changed_after_request_blocks_generation(self):
        request=self.ready();path=self.root/'changed.jsonl'
        path.write_text(json.dumps(dict(type='seo_context',sourcePdfId=286733,page=69,
                             rawHtmlBase64=base64.b64encode(b'<p>New conversion</p>').decode())))
        import_contexts(self.db,path)
        with self.assertRaisesRegex(ValueError,'changed'): import_generation(self.db,self.response(request))

    def test_legacy_context_preserves_bom_in_content_hash(self):
        import hashlib
        import_page(self.db,self.manifest(),'test');raw='\ufeff<p>Legacy source page</p>'
        path=self.root/'legacy.jsonl';path.write_text(json.dumps(dict(type='legacy_seo_example',sourcePdfId=286733,page=69,
                    rawHtmlBase64=base64.b64encode(raw.encode('utf-8')).decode())))
        import_contexts(self.db,path)
        source=self.db.execute('SELECT c.raw_sha256 FROM research_content c JOIN research_pages p ON p.content_id=c.id').fetchone()
        self.assertEqual(source['raw_sha256'],hashlib.sha256(raw.encode('utf-8')).hexdigest())

    def test_context_before_manifest_is_attached_and_converted_wins(self):
        def write_context(name,kind,text):
            path=self.root/name;path.write_text(json.dumps(dict(type=kind,sourcePdfId=286733,page=69,
                  rawHtmlBase64=base64.b64encode(text.encode()).decode())));import_contexts(self.db,path)
        write_context('legacy.jsonl','legacy_seo_example','legacy')
        import_page(self.db,self.manifest(),'test')
        self.assertIsNotNone(self.db.execute('SELECT content_id FROM research_pages').fetchone()[0])
        write_context('converted.jsonl','seo_context','converted')
        converted=self.db.execute('SELECT content_id FROM research_pages').fetchone()[0]
        write_context('newer-legacy.jsonl','legacy_seo_example','newer legacy')
        self.assertEqual(self.db.execute('SELECT content_id FROM research_pages').fetchone()[0],converted)

    def test_review_required_cannot_activate(self):
        request=self.ready();response=self.response(request,requiresReview=True)
        self.assertEqual(import_generation(self.db,response)['status'],'needs_review')
        with self.assertRaisesRegex(ValueError,'Review-required'): import_generation(self.db,response,self.root/'active')
        self.assertFalse((self.root/'active').exists())

    def test_identity_mismatch_blocks_generation_until_explicitly_resolved(self):
        self.ready();manifest=self.manifest(identityReviewRequired=True)
        import_page(self.db,manifest,'test')
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'identity_review')
        with self.assertRaisesRegex(ValueError,'not complete'): bundle(self.db,286733,69)
        self.assertEqual(generation_queue(self.db,10,self.root/'bundles'),[])
        manifest=self.manifest(identityReviewRequired=False)
        import_page(self.db,manifest,'test')
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages').fetchone()[0],'ready_for_generation')

    def test_publishing_old_request_after_identity_hold_is_rejected(self):
        request=self.ready();response=self.response(request)
        import_page(self.db,self.manifest(identityReviewRequired=True),'test')
        with self.assertRaisesRegex(ValueError,'not complete'): import_generation(self.db,response,self.root/'active')
        self.assertFalse((self.root/'active').exists())

    def test_publishing_old_request_after_changed_evidence_is_rejected(self):
        request=self.ready();response=self.response(request)
        self.export(query_clicks=1);import_page(self.db,self.root/'page.json','test')
        with self.assertRaisesRegex(ValueError,'Research changed'): import_generation(self.db,response,self.root/'active')
        self.assertFalse((self.root/'active').exists())

    def test_runtime_export_uses_new_snapshot_and_holds_stale_drafts(self):
        from export_runtime import export
        request=self.ready();import_generation(self.db,self.response(request))
        first=export(self.db,self.root/'snapshot-1')
        self.assertEqual(first['exportedPages'],1)
        with self.assertRaises(FileExistsError): export(self.db,self.root/'snapshot-1')
        import_page(self.db,self.manifest(identityReviewRequired=True),'test')
        second=export(self.db,self.root/'snapshot-2')
        self.assertEqual(second['exportedPages'],0)
        self.assertEqual(second['heldPages'],1)
        self.assertFalse((self.root/'snapshot-2/metadata/733/286733/69.json').exists())

    def test_resume_skips_generated_and_requeues_changed_evidence(self):
        request=self.ready();directory=self.root/'bundles'
        self.assertEqual(len(generation_queue(self.db,10,directory)),1)
        import_generation(self.db,self.response(request),self.root/'active')
        self.assertEqual(generation_queue(self.db,10,directory),[])
        self.export(query_clicks=1);import_page(self.db,self.root/'page.json','test')
        self.assertEqual(len(generation_queue(self.db,10,directory)),1)

    def test_reordered_evidence_does_not_repeat_model_work(self):
        request=self.ready()
        left=dict(request);right=dict(request)
        left['semrush']=[dict(keyword='a'),dict(keyword='b')]
        right['semrush']=list(reversed(left['semrush']))
        self.assertEqual(request_signature(left),request_signature(right))
        import_generation(self.db,self.response(request))
        self.db.execute('PRAGMA reverse_unordered_selects=ON')
        self.assertEqual(generation_queue(self.db,10,self.root/'bundles'),[])

    def test_older_evidence_cannot_replace_active_record(self):
        request=self.ready();output=self.root/'active';response=self.response(request)
        import_generation(self.db,response,output);path=output/'733/286733/69.json'
        metadata=json.loads(path.read_text());metadata['evidenceThrough']='2026-12-01T00:00:00Z';path.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError,'Older evidence'): import_generation(self.db,response,output)

    def test_inventory_discovers_clicked_pages_without_inventing_queries(self):
        source=self.export()
        with zipfile.ZipFile(source) as original:
            tables={name:original.read(name) for name in original.namelist()}
        tables['Filters.csv']=b'Filter,Value\nSearch type,Web\n'
        with zipfile.ZipFile(self.root/'inventory.zip','w') as archive:
            for name,data in tables.items(): archive.writestr(name,data)
        import_inventory(self.db,self.root/'inventory.zip','2026-11-01','2026-11-03')
        self.assertEqual(len(research_queue(self.db,10)),1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queries').fetchone()[0],0)
        self.ready()
        self.assertEqual(research_queue(self.db,10),[])

    def test_bing_inventory_preserves_reported_values_and_requires_provenance(self):
        path=self.root/'pages.csv';path.write_text('Page,Impressions,Clicks\n'+self.url+',6,7\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'provenance'):
            import_inventory(self.db,path,'2026-10-29','2026-11-04','bing')
        proof=self.root/'proof.txt';proof.write_text('Bing Pages report, 7 D, October 29 to November 4')
        import_inventory(self.db,path,'2026-10-29','2026-11-04','bing',proof)
        row=research_queue(self.db,1)[0]
        self.assertEqual((row['clicks'],row['impressions']),(7,6))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queries').fetchone()[0],0)

    def test_recent_shorter_window_precedes_overlapping_older_window(self):
        for ident,start,page,clicks in [('recent','2026-10-29',1,2),('long','2026-10-06',2,100)]:
            self.db.execute('INSERT INTO research_inventory VALUES (?,?,?,?,?,?,?)',(ident,'bing',start,'2026-11-04','x',1,''))
            self.db.execute('INSERT INTO research_discovered_pages VALUES (?,?,?,?,?,?)',(ident,286733,page,self.url,clicks,100))
        self.assertEqual([row['page'] for row in research_queue(self.db,2)],[1,2])


if __name__=='__main__': unittest.main()
