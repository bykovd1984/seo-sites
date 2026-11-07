"""Durable Terra research -> immutable Sol generation bundles -> versioned metadata."""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import io
import ipaddress
import json
import math
import os
import re
import sqlite3
import tempfile
import time
import unicodedata
from urllib.parse import urlsplit
import zipfile
import zlib
from pathlib import Path

from generate import PageText, atomic_json, plain, safe
from history import connect, page_key
from ranking_policy import eligibility, init as init_rankings, record as record_ranking

from paths import ROOT
COLLECTOR=('gpt-6.1-terra','high')
GENERATOR=('gpt-6.1-sol','medium')


def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def packed(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def key(value): return hashlib.sha256(packed(value).encode()).hexdigest()


def request_signature(value):
    # SQL index changes can reorder equal-date evidence rows. This must not consume another model run.
    def canonical(item):
        if isinstance(item,dict): return {name:canonical(child) for name,child in item.items() if name!='requestId'}
        if isinstance(item,list): return sorted((canonical(child) for child in item),key=packed)
        return item
    return key(canonical(value))


def init(db):
    init_rankings(db)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS research_settings (name TEXT PRIMARY KEY,value TEXT NOT NULL,updated TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS research_runs (id TEXT PRIMARY KEY, created TEXT, collector_model TEXT,
      collector_effort TEXT, generator_model TEXT, generator_effort TEXT, status TEXT);
    CREATE TABLE IF NOT EXISTS research_artifacts (id TEXT PRIMARY KEY, path TEXT NOT NULL, kind TEXT,
      source_url TEXT, observed_at TEXT, bytes INTEGER);
    CREATE TABLE IF NOT EXISTS research_pages (pdf INTEGER,page INTEGER,url TEXT,content_id TEXT,
      stage TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(pdf,page));
    CREATE TABLE IF NOT EXISTS research_windows (id TEXT PRIMARY KEY, run_id TEXT,pdf INTEGER,page INTEGER,
      engine TEXT,start TEXT,end TEXT,page_clicks INTEGER,page_impressions INTEGER,
      raw_artifact TEXT,collector_model TEXT,collector_effort TEXT,coverage TEXT,payload TEXT);
    CREATE INDEX IF NOT EXISTS research_recent ON research_windows(end DESC,page_clicks DESC);
    CREATE TABLE IF NOT EXISTS research_queries (window_id TEXT,query TEXT,clicks INTEGER,impressions INTEGER,
      position REAL,PRIMARY KEY(window_id,query));
    CREATE TABLE IF NOT EXISTS research_keywords (id TEXT PRIMARY KEY,pdf INTEGER,page INTEGER,seed TEXT,
      keyword TEXT,country_database TEXT,volume REAL,kd REAL,source_url TEXT,observed_at TEXT,
      status TEXT,relevance TEXT,proof_artifact TEXT,payload TEXT,collector_model TEXT,collector_effort TEXT);
    CREATE TABLE IF NOT EXISTS research_content (id TEXT PRIMARY KEY,pdf INTEGER,page INTEGER,
      raw_sha256 TEXT,source_artifact TEXT,context_zlib BLOB,created TEXT);
    CREATE TABLE IF NOT EXISTS research_context_attempts (pdf INTEGER,page INTEGER,reason TEXT,source_artifact TEXT,created TEXT,PRIMARY KEY(pdf,page));
    CREATE TABLE IF NOT EXISTS research_requests (id TEXT PRIMARY KEY,pdf INTEGER,page INTEGER,model TEXT,
      effort TEXT,created TEXT,bundle TEXT,status TEXT);
    CREATE TABLE IF NOT EXISTS research_metadata_versions (id TEXT PRIMARY KEY,request_id TEXT,pdf INTEGER,
      page INTEGER,model TEXT,effort TEXT,created TEXT,status TEXT,payload TEXT);
    CREATE TABLE IF NOT EXISTS research_events (id INTEGER PRIMARY KEY,created TEXT,pdf INTEGER,page INTEGER,
      event TEXT,payload TEXT);
    CREATE TABLE IF NOT EXISTS research_model_keyword_decisions (
      version_id TEXT NOT NULL,request_id TEXT NOT NULL,candidate_id TEXT NOT NULL,
      decision TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(version_id,candidate_id));
    CREATE TABLE IF NOT EXISTS research_inventory (id TEXT PRIMARY KEY,engine TEXT,start TEXT,end TEXT,
      raw_artifact TEXT,rows INTEGER,coverage TEXT);
    CREATE TABLE IF NOT EXISTS research_discovered_pages (inventory_id TEXT,pdf INTEGER,page INTEGER,url TEXT,
      clicks INTEGER,impressions INTEGER,PRIMARY KEY(inventory_id,pdf,page));
    CREATE TABLE IF NOT EXISTS research_inventory_ui_observations (id TEXT PRIMARY KEY,artifact_id TEXT NOT NULL,
      start TEXT NOT NULL,end TEXT NOT NULL,reported_rows INTEGER NOT NULL,visible_rows INTEGER NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS research_ui_url_resolutions (pdf INTEGER NOT NULL,page INTEGER NOT NULL,url TEXT NOT NULL,
      inventory_id TEXT NOT NULL,raw_artifact TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(pdf,page,url,inventory_id));
    CREATE INDEX IF NOT EXISTS research_windows_page ON research_windows(pdf,page,engine,start,end);
    CREATE INDEX IF NOT EXISTS research_content_page ON research_content(pdf,page);
    CREATE INDEX IF NOT EXISTS research_keywords_page ON research_keywords(pdf,page,observed_at);
    CREATE INDEX IF NOT EXISTS research_requests_page ON research_requests(pdf,page,status);
    CREATE INDEX IF NOT EXISTS research_versions_page ON research_metadata_versions(pdf,page,created);
    CREATE INDEX IF NOT EXISTS research_clicked_discovery ON research_discovered_pages(clicks,pdf,page) WHERE clicks>0;
    ''')
    if 'semantic_hash' not in {row['name'] for row in db.execute('PRAGMA table_info(research_requests)')}:
        db.execute('ALTER TABLE research_requests ADD COLUMN semantic_hash TEXT')
    while True:
        rows=db.execute('SELECT id,bundle FROM research_requests WHERE semantic_hash IS NULL LIMIT 500').fetchall()
        if not rows: break
        for row in rows: db.execute('UPDATE research_requests SET semantic_hash=? WHERE id=?',(request_signature(json.loads(row['bundle'])),row['id']))
    db.execute('CREATE INDEX IF NOT EXISTS research_request_signature ON research_requests(semantic_hash)')


def start_run(db, run_id):
    db.execute('INSERT OR IGNORE INTO research_runs VALUES (?,?,?,?,?,?,?)',
               (run_id,now(),*COLLECTOR,*GENERATOR,'collecting'))


def artifact(db,path,kind,source_url=''):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT/'artifacts') or not path.is_file(): raise ValueError('Evidence must be a saved workspace artifact')
    if '.private.' in path.name.lower(): raise ValueError('Credentials cannot be research evidence')
    data=path.read_bytes()
    if len(data)>100*1024**2: raise ValueError('Evidence artifact exceeds 100 MiB')
    ident=hashlib.sha256(data).hexdigest()
    database=next(row['file'] for row in db.execute('PRAGMA database_list') if row['name']=='main')
    archived=Path(database).resolve().parent/'evidence'/ident/path.name
    if not archived.exists():
        archived.parent.mkdir(parents=True,exist_ok=True)
        handle,temporary=tempfile.mkstemp(dir=archived.parent,suffix='.tmp')
        try:
            with os.fdopen(handle,'wb') as stream: stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,archived)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    db.execute('INSERT OR IGNORE INTO research_artifacts VALUES (?,?,?,?,?,?)',
               (ident,str(archived),kind,source_url,now(),len(data)))
    return ident


def metric(value,integer=False):
    if value is None or value=='': return None
    value=float(str(value).replace('\u00a0','').replace('\u202f','').replace(' ','').replace(',','.'))
    if not math.isfinite(value) or value<0 or (integer and not value.is_integer()): raise ValueError('Invalid numeric evidence')
    return int(value) if integer else value


def field(row,*names):
    return next((row[name] for name in names if name in row),None)


def csv_rows(data): return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))


def gsc_tables(path,start,end):
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist())>50*1024**2: raise ValueError('Export is too large')
        tables={Path(name).name:csv_rows(archive.read(name)) for name in archive.namelist() if name.endswith('.csv')}
    chart=tables.get('Диаграмма.csv',tables.get('Chart.csv',[]))
    dates=[str(dt.date.fromisoformat(field(row,'Дата','Date'))) for row in chart]
    if not dates or min(dates)!=start or max(dates)!=end: raise ValueError('Export date range differs from the declared window')
    if any(not start<=date<=end for date in dates): raise ValueError('Export date lies outside the declared window')
    return tables


def import_inventory_ui(db,path):
    """Keep partial UI inventory observations separate from exported discovery and query metrics."""
    path=Path(path); value=json.loads(path.read_text(encoding='utf-8-sig'))
    if value.get('kind')!='partial_gsc_page_inventory_ui_transcription' or value.get('property')!='https://manualsdump.com/' or value.get('searchType')!='Web':
        raise ValueError('Unsupported inventory UI observation')
    start=str(dt.date.fromisoformat(value['start'])); end=str(dt.date.fromisoformat(value['end']))
    if start>end: raise ValueError('Invalid inventory date range')
    rows=value.get('pages'); visible=value.get('visibleRows'); total=value.get('reportedPageRows')
    if not isinstance(rows,list) or type(visible)!=int or type(total)!=int or visible!=len(rows) or not 0<visible<=total:
        raise ValueError('Invalid visible or reported inventory row count')
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('label'),str) or not row['label'].strip(): raise ValueError('Invalid visible inventory row')
        pdf,page=row.get('sourcePdfId'),row.get('page')
        if pdf is None and page is None and row['label']=='homepage': identity=('homepage',)
        elif type(pdf)==int and type(page)==int and pdf>0 and page>0: identity=(pdf,page)
        else: raise ValueError('Invalid visible inventory page identity')
        if identity in seen: raise ValueError('Duplicate visible inventory page')
        seen.add(identity)
        if any(type(row.get(k))!=int or row[k]<0 for k in ('clicks','impressions')): raise ValueError('Invalid visible inventory metrics')
    totals=value.get('siteTotals',{})
    if type(totals.get('clicks'))!=int or totals['clicks']<0 or type(totals.get('impressionsApproximate'))!=int or totals['impressionsApproximate']<0:
        raise ValueError('Invalid inventory site totals')
    proof=artifact(db,path,'gsc_partial_inventory_ui',value['property'])
    ident=key(('gsc_partial_inventory_ui',proof))
    inserted=db.execute('INSERT OR IGNORE INTO research_inventory_ui_observations VALUES (?,?,?,?,?,?,?)',
                        (ident,proof,start,end,total,visible,packed(value))).rowcount
    return dict(observationId=ident,inserted=bool(inserted),visibleRows=visible,reportedRows=total,coverage='partial UI transcription; separate from exports')


def resolve_ui_urls(db):
    """Record only unambiguous exact IDs from independent exported inventories."""
    identities=set()
    for item in db.execute('SELECT payload FROM research_inventory_ui_observations'):
        for row in json.loads(item['payload'])['pages']:
            if row.get('sourcePdfId') is not None: identities.add((row['sourcePdfId'],row['page']))
    added=ambiguous=missing=0
    for pdf,page in identities:
        candidates=db.execute('''SELECT DISTINCT d.url,i.id,i.raw_artifact FROM research_discovered_pages d
          JOIN research_inventory i ON i.id=d.inventory_id WHERE d.pdf=? AND d.page=? ORDER BY i.id''',(pdf,page)).fetchall()
        valid=[]
        for row in candidates:
            try:
                if page_key(row['url'])==(pdf,page): valid.append(row)
            except (ValueError,TypeError): continue
        urls={row['url'] for row in valid}
        if not urls: missing+=1;continue
        if len(urls)!=1: ambiguous+=1;continue
        source=valid[0]
        added+=db.execute('INSERT OR IGNORE INTO research_ui_url_resolutions VALUES (?,?,?,?,?,?)',
                          (pdf,page,source['url'],source['id'],source['raw_artifact'],now())).rowcount
    return dict(identities=len(identities),added=added,ambiguous=ambiguous,missing=missing,
                coverage='URL source is independent exported inventory; exact GSC page filter still requires verification')


def import_inventory(db,path,start,end,engine='google',proof_path=None):
    start=str(dt.date.fromisoformat(start));end=str(dt.date.fromisoformat(end))
    if start>end: raise ValueError('Invalid inventory date range')
    if engine=='bing':
        if not proof_path: raise ValueError('Bing inventory requires saved report provenance')
        rows=csv_rows(Path(path).read_bytes())
        if not rows or not {'Page','Clicks','Impressions'}.issubset(rows[0]): raise ValueError('Expected Bing page report')
        proof=artifact(db,path,'bing_page_inventory')
        provenance=artifact(db,proof_path,'bing_inventory_provenance')
        ident=key(('bing',start,end,proof,provenance))
        db.execute('INSERT OR IGNORE INTO research_inventory VALUES (?,?,?,?,?,?,?)',
                   (ident,'bing',start,end,proof,len(rows),'UI page report; query relationships require separate page-filtered evidence. Provenance: '+provenance))
        count=0
        for row in rows:
            try: pdf,page=page_key(row['Page'])
            except (ValueError,TypeError): continue
            record_ranking(db,'bing',start,end,row['Page'],metric(field(row,'Avg. Position','Average Position','Position')),
                           metric(row['Impressions'],True),proof,'page_inventory')
            db.execute('INSERT OR IGNORE INTO research_discovered_pages VALUES (?,?,?,?,?,?)',
                       (ident,pdf,page,row['Page'],metric(row['Clicks'],True),metric(row['Impressions'],True)))
            count+=1
        return dict(inventoryId=ident,exportedRows=len(rows),manualPages=count)
    if engine!='google': raise ValueError('Unknown inventory provider')
    tables=gsc_tables(path,start,end);filters=tables.get('Фильтры.csv',tables.get('Filters.csv',[]))
    if any(field(row,'Фильтр','Filter') in ('Страница','Page') for row in filters):
        raise ValueError('Discovery inventory must not have a page filter')
    rows=tables.get('Страницы.csv',tables.get('Pages.csv',[]));proof=artifact(db,path,'gsc_page_inventory')
    ident=key(('google',start,end,proof))
    db.execute('INSERT OR IGNORE INTO research_inventory VALUES (?,?,?,?,?,?,?)',
               (ident,'google',start,end,proof,len(rows),'Top exported pages only; does not prove complete site coverage. Global queries are not linked to pages.'))
    count=0
    for row in rows:
        url=field(row,'Популярные страницы','Top pages','Page')
        try: pdf,page=page_key(url)
        except (ValueError,TypeError): continue
        record_ranking(db,'google',start,end,url,metric(field(row,'Позиция','Position')),
                       metric(field(row,'Показы','Impressions'),True),proof,'page_inventory')
        db.execute('INSERT OR IGNORE INTO research_discovered_pages VALUES (?,?,?,?,?,?)',
                   (ident,pdf,page,url,metric(field(row,'Клики','Kлики','Clicks'),True),metric(field(row,'Показы','Impressions'),True)))
        count+=1
    return dict(inventoryId=ident,exportedRows=len(rows),manualPages=count)


def research_queue(db,limit):
    rows=db.execute('''SELECT d.*,i.start,i.end,i.engine,i.raw_artifact FROM research_discovered_pages d
      JOIN research_inventory i ON i.id=d.inventory_id
      WHERE d.clicks>0 AND NOT EXISTS(SELECT 1 FROM research_windows w WHERE w.pdf=d.pdf AND w.page=d.page
        AND w.engine=i.engine AND w.start<=i.start AND w.end>=i.end)
      ORDER BY i.end DESC,i.start DESC,d.clicks DESC,d.impressions DESC,d.pdf,d.page''')
    candidates=[]
    for row in rows:
        candidates.append(dict(row))
    for observation in db.execute('SELECT * FROM research_inventory_ui_observations ORDER BY rowid DESC'):
        data=json.loads(observation['payload'])
        for row in data['pages']:
            pdf,page=row.get('sourcePdfId'),row.get('page')
            if pdf is None or row['clicks']<=0: continue
            if db.execute('SELECT 1 FROM research_windows WHERE pdf=? AND page=? AND engine=? AND start<=? AND end>=? LIMIT 1',
                          (pdf,page,'google',observation['start'],observation['end'])).fetchone(): continue
            urls={r['url'] for r in db.execute('SELECT DISTINCT url FROM research_discovered_pages WHERE pdf=? AND page=?',(pdf,page))}
            resolution=db.execute('SELECT * FROM research_ui_url_resolutions WHERE pdf=? AND page=? ORDER BY created DESC LIMIT 1',(pdf,page)).fetchone()
            verified=resolution is not None and len(urls)==1 and resolution['url'] in urls
            candidates.append(dict(pdf=pdf,page=page,url=resolution['url'] if verified else None,clicks=row['clicks'],impressions=row['impressions'],
                                   start=observation['start'],end=observation['end'],engine='google',
                                   inventory_id=observation['id'],raw_artifact=observation['artifact_id'],
                                   sourceType='partial_gsc_inventory_ui',partialCoverage=True,urlResolutionRequired=not verified,
                                   urlResolutionSource=dict(inventoryId=resolution['inventory_id'],rawArtifact=resolution['raw_artifact']) if verified else None,
                                   pageFilterVerificationRequired=True))
    # Prefer a real export over UI observations for the same engine/date/page; never sum observations.
    unique={}
    for row in candidates:
        identity=(row['engine'],row['start'],row['end'],row['pdf'],row['page'])
        if identity not in unique: unique[identity]=row
    ordered=sorted(unique.values(),key=lambda r:(-dt.date.fromisoformat(r['end']).toordinal(),
                   -dt.date.fromisoformat(r['start']).toordinal(),-r['clicks'],-r['impressions'],r['pdf'],r['page']))
    return ordered[:limit]


def gsc_export(path,pdf,page,start,end):
    """A page/query relationship must be proved by the report's own filter, not a global join."""
    tables=gsc_tables(path,start,end)
    filters=tables.get('Фильтры.csv',tables.get('Filters.csv',[]))
    page_filters=[field(r,'Значение','Value') for r in filters if field(r,'Фильтр','Filter') in ('Страница','Page')]
    if len(page_filters)!=1 or page_key(page_filters[0])!=(pdf,page): raise ValueError('GSC export is not filtered to this exact page')
    pages=tables.get('Страницы.csv',tables.get('Pages.csv',[]))
    selected=[r for r in pages if page_key(field(r,'Популярные страницы','Top pages','Page'))==(pdf,page)]
    if len(selected)!=1: raise ValueError('Expected one exported landing page')
    queries=[]
    for row in tables.get('Запросы.csv',tables.get('Queries.csv',[])):
        query=field(row,'Популярные запросы','Top queries','Query')
        if query:
            queries.append(dict(query=query,clicks=metric(field(row,'Клики','Kлики','Clicks'),True),
                                impressions=metric(field(row,'Показы','Impressions'),True),position=metric(field(row,'Позиция','Position'))))
    return dict(url=page_filters[0],queries=queries,
                observedClicks=metric(field(selected[0],'Клики','Kлики','Clicks'),True),
                observedImpressions=metric(field(selected[0],'Показы','Impressions'),True),
                pageAveragePosition=metric(field(selected[0],'Позиция','Position')),
                queryRows=len(queries),possiblyCapped=len(queries)>=1000,filterProof=filters)


def bing_export(path,page):
    """Bing CSV lacks a page column: require saved page-filter provenance and parse its actual metrics."""
    if not page.get('pageFilterVerified') or not page.get('pageFilterProofArtifact'):
        raise ValueError('Bing export needs saved verified page-filter provenance')
    rows=csv_rows(Path(path).read_bytes()); queries=[]
    for row in rows:
        query=field(row,'Keyword','Query')
        if not query: raise ValueError('Bing export has no keyword column')
        position=metric(field(row,'Avg. Position','Average Position'))
        queries.append(dict(query=query,clicks=metric(field(row,'Clicks'),True),
                            impressions=metric(field(row,'Impressions'),True),position=position or None))
    return dict(url=page['url'],queries=queries,observedClicks=metric(page['observedClicks'],True),
                observedImpressions=metric(page['observedImpressions'],True),queryRows=len(queries),
                exportedClicks=sum(r['clicks'] for r in queries),exportedImpressions=sum(r['impressions'] for r in queries),
                coverage=page.get('coverage',''),pageFilterProofArtifact=page['pageFilterProofArtifact'])


def ui_transcription(path,page,provider):
    """Import a clearly identified page-filtered UI transcription, never as an export."""
    if not page.get('pageFilterVerified') or not page.get('pageFilterProofArtifact'):
        raise ValueError('UI transcription needs saved verified page-filter provenance')
    source=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if source.get('kind')!=provider+'_ui_transcription' or any(source.get(k)!=page.get(k) for k in ('url','start','end','observedClicks','observedImpressions')):
        raise ValueError('UI transcription does not match page and date provenance')
    if provider=='gsc' and (source.get('property')!='https://manualsdump.com/' or source.get('searchType')!='Web'):
        raise ValueError('GSC transcription requires exact property and search type')
    rows=source.get('queries')
    if not isinstance(rows,list) or not rows: raise ValueError('Bing transcription needs visible query rows')
    queries=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('query'),str) or not row['query'].strip():
            raise ValueError('Invalid Bing transcription query')
        clicks=metric(row.get('clicks'),True); impressions=metric(row.get('impressions'),True)
        if clicks is None or impressions is None: raise ValueError('Missing Bing transcription metrics')
        queries.append(dict(query=row['query'],clicks=clicks,impressions=impressions,position=metric(row.get('position'))))
    return dict(url=page['url'],queries=queries,observedClicks=source['observedClicks'],observedImpressions=source['observedImpressions'],
                queryRows=len(queries),exportedClicks=sum(r['clicks'] for r in queries),exportedImpressions=sum(r['impressions'] for r in queries),
                coverage=page.get('coverage',''),pageFilterProofArtifact=page['pageFilterProofArtifact'],sourceType=provider+'_ui_transcription')


def import_page(db,path,run_id):
    path=Path(path).resolve(); page=json.loads(path.read_text(encoding='utf-8-sig'))
    pdf,number=page_key(page['url'])
    if page['page']!=number or (page['sourcePdfId']!=pdf and not(page['sourcePdfId'] is None and page.get('identityReviewRequired'))):
        raise ValueError('Manifest/page ID mismatch')
    start=str(dt.date.fromisoformat(page['start']));end=str(dt.date.fromisoformat(page['end']))
    if start>end: raise ValueError('Invalid research window')
    engine={'gsc':'google','google':'google','bing':'bing'}.get(page['engine'].lower())
    if not engine: raise ValueError('Unknown search provider')
    manifest_artifact=artifact(db,path,'collector_manifest',page['url'])
    source_type=page.get('sourceType'); is_transcription=source_type in ('bing_ui_transcription','gsc_ui_transcription')
    if is_transcription and (source_type=='bing_ui_transcription')!=(engine=='bing'): raise ValueError('UI transcription provider mismatch')
    raw=path.parent/page['rawExport']; raw_artifact=artifact(db,raw,source_type if is_transcription else 'page_query_export',page['url'])
    verified=ui_transcription(raw,page,'bing' if engine=='bing' else 'gsc') if is_transcription else gsc_export(raw,pdf,number,start,end) if engine=='google' else bing_export(raw,page)
    if engine=='bing' or is_transcription:
        verified['pageFilterProofArtifact']=artifact(db,path.parent/page['pageFilterProofArtifact'],('bing' if engine=='bing' else 'gsc')+'_page_filter',page['url'])
    if page.get('observedClicks')!=verified['observedClicks'] or page.get('observedImpressions')!=verified['observedImpressions']:
        raise ValueError('Collector page totals differ from raw report')
    queries=verified['queries']
    record_ranking(db,engine,start,end,verified['url'],verified.get('pageAveragePosition'),
                   verified['observedImpressions'],raw_artifact,'page_filtered_export')
    window_id=key((engine,pdf,number,start,end,raw_artifact,manifest_artifact))
    db.execute('INSERT OR IGNORE INTO research_pages VALUES (?,?,?,NULL,?,?)',(pdf,number,page['url'],'content_pending',now()))
    attach_context(db,pdf,number)
    inserted=db.execute('INSERT OR IGNORE INTO research_windows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (window_id,run_id,pdf,number,engine,start,end,verified['observedClicks'],verified['observedImpressions'],
                raw_artifact,*COLLECTOR,page.get('coverage',''),packed({'manifestArtifact':manifest_artifact,'verified':verified,'contentInspection':page.get('content'),
                'identityReviewRequired':bool(page.get('identityReviewRequired')),'verifiedSourcePdfId':page['sourcePdfId']}))).rowcount
    for row in queries:
        text=unicodedata.normalize('NFKC',row['query']).strip()
        clicks,impressions=metric(row['clicks'],True),metric(row['impressions'],True)
        if not text or clicks is None or impressions is None: raise ValueError('Incomplete query evidence')
        db.execute('INSERT OR IGNORE INTO research_queries VALUES (?,?,?,?,?)',(window_id,text,clicks,impressions,metric(row.get('position'))))
    for item in page.get('semrush',[]):
        country=str(item.get('countryDatabase','unknown')).lower()
        volume,kd=metric(item.get('volume')),metric(item.get('kd'))
        if kd is not None and kd>100: raise ValueError('Keyword difficulty outside 0..100')
        proof=artifact(db,path.parent/item['proofArtifact'],'semrush_ui',item['sourceUrl']) if item.get('proofArtifact') else manifest_artifact
        ident=key((pdf,number,item))
        db.execute('INSERT OR IGNORE INTO research_keywords VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (ident,pdf,number,item['seed'],item['keyword'],country,volume,kd,item['sourceUrl'],item['observedAt'],
                    item.get('status','unknown'),item.get('relevance','unassessed'),proof,packed(item),*COLLECTOR))
    if inserted:
        db.execute('INSERT INTO research_events(created,pdf,page,event,payload) VALUES (?,?,?,?,?)',
                   (now(),pdf,number,'research_imported',packed({'windowId':window_id,'manifestArtifact':manifest_artifact})))
    refresh_stage(db,pdf,number)
    return window_id


def source_mapping_proof(db,pdf,page):
    """A guarded catalog export can resolve technical API source-ID uncertainty.

    This never clears an explicit catalog/content identity quarantine.
    """
    row=db.execute('''SELECT c.* FROM research_pages p JOIN research_content c ON c.id=p.content_id
        WHERE p.pdf=? AND p.page=?''',(pdf,page)).fetchone()
    if not row: return None
    context=json.loads(zlib.decompress(row['context_zlib']))
    if context.get('readOnly') is not True or context.get('sourcePdfId')!=pdf or context.get('page')!=page:
        return None
    if context.get('type')=='seo_context':
        if not isinstance(context.get('manualId'),int) or context['manualId']<=0: return None
    elif context.get('type')=='legacy_seo_example':
        if context.get('format') not in ('bcl_html','legacy_page'): return None
    else: return None
    if not isinstance(context.get('pageCount'),int) or not page<=context['pageCount']<=65535: return None
    return dict(kind='catalog_source_mapping',sourcePdfId=pdf,page=page,contentSha256=row['raw_sha256'],
                sourceArtifact=row['source_artifact'])


def refresh_stage(db,pdf,page):
    record=db.execute('SELECT content_id FROM research_pages WHERE pdf=? AND page=?',(pdf,page)).fetchone()
    if not record: return
    keywords=db.execute('SELECT status,volume,kd FROM research_keywords WHERE pdf=? AND page=?',(pdf,page)).fetchall()
    # Unknown metric age is a quality limitation, not a failed lookup. An explicit no-results report is also a completed check.
    checked=any(row['volume'] is not None or row['kd'] is not None or 'nothing found' in row['status'].lower()
                or row['status'].lower() in ('observed','reported') for row in keywords)
    mapping=source_mapping_proof(db,pdf,page)
    def requires_identity_review(row):
        payload=json.loads(row['payload'])
        return payload.get('identityReviewRequired') and not (mapping and payload.get('identityReviewReason')=='api_source_mapping_pending')
    identity_review=any(requires_identity_review(row) for row in db.execute('''
      SELECT payload FROM research_windows w WHERE pdf=? AND page=? AND w.rowid=(SELECT MAX(v.rowid)
        FROM research_windows v WHERE v.pdf=w.pdf AND v.page=w.page AND v.engine=w.engine AND v.start=w.start AND v.end=w.end)''',(pdf,page)))
    has_window=db.execute('SELECT 1 FROM research_windows WHERE pdf=? AND page=? LIMIT 1',(pdf,page)).fetchone()
    stage='identity_review' if identity_review else 'content_pending' if not record['content_id'] else 'search_evidence_pending' if not has_window else 'ready_for_generation' if checked else 'semrush_pending'
    db.execute('UPDATE research_pages SET stage=?,updated=? WHERE pdf=? AND page=?',(stage,now(),pdf,page))


def import_keyword_evidence(db,path):
    """Attach observed keywords to a discovered, hash-bound page without inventing a search window."""
    path=Path(path).resolve(); manifest=json.loads(path.read_text(encoding='utf-8-sig'))
    pdf,page=page_key(manifest['url'])
    if manifest.get('sourcePdfId')!=pdf or manifest.get('page')!=page:
        raise ValueError('Keyword evidence page identity mismatch')
    if manifest.get('identityReviewRequired'): raise ValueError('Keyword-only import cannot resolve an identity review')
    if not db.execute('SELECT 1 FROM research_discovered_pages WHERE pdf=? AND page=? AND url=?',
                      (pdf,page,manifest['url'])).fetchone():
        raise ValueError('Keyword evidence requires an exact discovered URL')
    source=db.execute('SELECT id FROM research_content WHERE pdf=? AND page=? AND raw_sha256=?',
                      (pdf,page,manifest.get('contentSha256'))).fetchone()
    if not source: raise ValueError('Keyword evidence requires matching source context hash')
    items=manifest.get('semrush')
    if not isinstance(items,list) or not 1<=len(items)<=100: raise ValueError('Expected 1..100 keyword observations')
    # Validate every observation before writing any database rows.
    for item in items:
        if not all(isinstance(item.get(k),str) and item[k].strip() for k in
                   ('seed','keyword','countryDatabase','sourceUrl','observedAt','status','relevance','proofArtifact')):
            raise ValueError('Keyword observation lacks provenance')
        if not re.fullmatch(r'[A-Za-z]{2}',item['countryDatabase']): raise ValueError('Expected country database code')
        u=urlsplit(item['sourceUrl'])
        if u.scheme!='https' or not u.hostname or u.username or u.password: raise ValueError('Invalid keyword source URL')
        try: dt.date.fromisoformat(item['observedAt'][:10])
        except ValueError: raise ValueError('Invalid keyword observation date')
        if item.get('volume') is not None: metric(item['volume'])
        kd=metric(item.get('kd'))
        if kd is not None and kd>100: raise ValueError('Keyword difficulty outside 0..100')
        proof=(path.parent/item['proofArtifact']).resolve()
        if not proof.is_relative_to(ROOT/'artifacts') or not proof.is_file(): raise ValueError('Missing keyword proof artifact')
    manifest_id=artifact(db,path,'keyword_only_manifest',manifest['url'])
    db.execute('INSERT OR IGNORE INTO research_pages VALUES (?,?,?,NULL,?,?)',(pdf,page,manifest['url'],'content_pending',now()))
    attach_context(db,pdf,page)
    current=db.execute('SELECT content_id FROM research_pages WHERE pdf=? AND page=?',(pdf,page)).fetchone()
    if not current or current['content_id']!=source['id']: raise ValueError('Keyword evidence does not match attached source context')
    inserted=0
    for item in items:
        proof=artifact(db,path.parent/item['proofArtifact'],'semrush_ui',item['sourceUrl'])
        ident=key((pdf,page,item)); payload={**item,'keywordOnlyManifestArtifact':manifest_id}
        inserted+=db.execute('INSERT OR IGNORE INTO research_keywords VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (ident,pdf,page,item['seed'],item['keyword'],item['countryDatabase'].lower(),metric(item.get('volume')),
                     metric(item.get('kd')),item['sourceUrl'],item['observedAt'],item['status'],item['relevance'],proof,
                     packed(payload),*COLLECTOR)).rowcount
    if inserted: db.execute('INSERT INTO research_events(created,pdf,page,event,payload) VALUES (?,?,?,?,?)',
                            (now(),pdf,page,'keyword_only_imported',packed({'manifestArtifact':manifest_id,'inserted':inserted})))
    refresh_stage(db,pdf,page)
    return dict(sourcePdfId=pdf,page=page,inserted=inserted,manifestArtifact=manifest_id)


def attach_context(db,pdf,page):
    """Attach pre-existing content and keep converted content ahead of legacy examples."""
    rows=db.execute('SELECT id,context_zlib FROM research_content WHERE pdf=? AND page=? ORDER BY rowid DESC',(pdf,page))
    legacy=None;selected=None
    for row in rows:
        item=json.loads(zlib.decompress(row['context_zlib']))
        if item.get('type')=='seo_context': selected=row['id'];break
        if legacy is None: legacy=row['id']
    selected=selected or legacy
    if selected:
        db.execute('UPDATE research_pages SET content_id=?,updated=? WHERE pdf=? AND page=? AND (content_id IS NULL OR content_id<>?)',
                   (selected,now(),pdf,page,selected))


def import_contexts(db,path):
    source=artifact(db,path,'converted_page_context')
    count=0
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        item=json.loads(line)
        if item.get('type')=='legacy_source_unavailable':
            pdf,page=int(item['sourcePdfId']),int(item['page'])
            db.execute('INSERT OR REPLACE INTO research_context_attempts VALUES (?,?,?,?,?)',(pdf,page,item['reason'],source,now()))
            continue
        if item.get('type') not in ('seo_context','legacy_seo_example'): continue
        pdf,page=int(item['sourcePdfId']),int(item['page'])
        # The legacy exporter reproduces its runtime's chunked UTF-8 decoder, including any leading BOM.
        encoding='utf-8' if item['type']=='legacy_seo_example' else 'utf-8-sig'
        raw=base64.b64decode(item['rawHtmlBase64'],validate=True).decode(encoding)
        sha=hashlib.sha256(raw.encode()).hexdigest(); ident=key((pdf,page,sha))
        db.execute('INSERT OR IGNORE INTO research_content VALUES (?,?,?,?,?,?,?)',(ident,pdf,page,sha,source,zlib.compress(packed(item).encode()),now()))
        db.execute('DELETE FROM research_context_attempts WHERE pdf=? AND page=?',(pdf,page))
        attach_context(db,pdf,page)
        refresh_stage(db,pdf,page); count+=1
    return count


def import_context_file(db,path,attempts=3,retry_delay=.25):
    """Atomically import saved evidence; only transient SQLite lock failures retry."""
    if db.in_transaction:raise ValueError('Commit initialization before importing a context file')
    if not 1<=attempts<=5 or not 0<=retry_delay<=5:raise ValueError('Invalid bounded context retry settings')
    for attempt in range(attempts):
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                result=import_contexts(db,path)
            return result
        except sqlite3.OperationalError as exc:
            code=getattr(exc,'sqlite_errorcode',0) & 255
            if code not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED) or attempt+1==attempts:
                raise
            time.sleep(retry_delay*(attempt+1))


def context_queue(db,limit,retry_unavailable=False):
    result=[];seen=set()
    # Imported API windows can already exist before their source context does.
    # Those pages have left research_queue but still need a source export.
    pending=[dict(row) for row in db.execute('''SELECT p.pdf,p.page,MAX(w.end) AS end,MAX(w.start) AS start,
        MAX(COALESCE(w.page_clicks,(SELECT SUM(q.clicks) FROM research_queries q WHERE q.window_id=w.id),0)) clicks
        FROM research_pages p JOIN research_windows w ON w.pdf=p.pdf AND w.page=p.page
        WHERE p.content_id IS NULL GROUP BY p.pdf,p.page HAVING clicks>0''')]
    pending.extend(research_queue(db,1000000))
    pending.sort(key=lambda row:(row['end'],row['start'],row['clicks']),reverse=True)
    for row in pending:
        identity=(row['pdf'],row['page'])
        if identity in seen: continue
        seen.add(identity)
        if db.execute('SELECT 1 FROM research_content WHERE pdf=? AND page=?',identity).fetchone(): continue
        if not retry_unavailable and db.execute("SELECT 1 FROM research_context_attempts WHERE pdf=? AND page=? AND reason!='batch_byte_limit'",identity).fetchone(): continue
        result.append(dict(sourcePdfId=identity[0],page=identity[1]))
        if len(result)>=limit: break
    return result


def address_literals(query):
    # Match address literals inside ordinary queries or URLs, including bracketed IPv6.
    result=[]
    for token in re.findall(r'(?<![\w:])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])|(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F]{0,4}(?![\w:])', query):
        try:
            result.append(ipaddress.ip_address(token))
        except ValueError:
            continue
    return result


def private_address_query(query):
    return any(not address.is_global for address in address_literals(query))


def source_supported_query(query,source_addresses):
    # A documented default LAN address is relevant search evidence, not a URL to fetch.
    return all(address.is_global or address in source_addresses for address in address_literals(query))


def historical_queries(windows):
    """Find queries in older reports that the latest report for the same URL did not disclose."""
    reports = {}
    for window in windows:
        identity = (window['engine'], window['payload']['verified']['url'])
        reports.setdefault(identity, []).append(window)
    evidence = []
    for (engine, url), group in sorted(reports.items()):
        latest_end, latest_start = max((w['end'], w['start']) for w in group)
        recent = {q['query'] for w in group if (w['end'], w['start']) == (latest_end, latest_start)
                  for q in w['queries']}
        previous = {}
        for window in sorted(group, key=lambda w: (w['end'], w['start'], w['id']), reverse=True):
            if window['end'] >= latest_start:
                continue
            for row in window['queries']:
                if row['query'] not in recent and row['query'] not in previous:
                    previous[row['query']] = dict(row, start=window['start'], end=window['end'], windowId=window['id'])
        if previous:
            evidence.append(dict(engine=engine, url=url, latestStart=latest_start, latestEnd=latest_end,
                                 notReportedInLatest=[previous[q] for q in sorted(previous)]))
    return evidence


def bundle(db,pdf,page,allow_partial=False,imported_candidates=None,draft_coverage=None):
    record=db.execute('SELECT * FROM research_pages WHERE pdf=? AND page=?',(pdf,page)).fetchone()
    if not record or not record['content_id']: raise ValueError('Exact source context is required')
    if imported_candidates is not None and record['stage']=='identity_review':
        raise ValueError('Source identity requires review')
    if not db.execute('SELECT 1 FROM research_windows WHERE pdf=? AND page=? LIMIT 1',(pdf,page)).fetchone():
        raise ValueError('Exact page search report is required')
    rank_policy=eligibility(db,pdf,page)
    if not rank_policy['eligible']: raise ValueError('Ranking protection: '+rank_policy['reason'])
    if imported_candidates is None and record['stage']!='ready_for_generation' and not allow_partial:
        raise ValueError('Semrush research is not complete')
    content=db.execute('SELECT * FROM research_content WHERE id=?',(record['content_id'],)).fetchone()
    context=json.loads(zlib.decompress(content['context_zlib']))
    mapping=source_mapping_proof(db,pdf,page)
    encoding='utf-8' if context.get('type')=='legacy_seo_example' else 'utf-8-sig'
    raw=base64.b64decode(context.pop('rawHtmlBase64')).decode(encoding); parser=PageText();parser.feed(raw)
    page_text=plain(' '.join(parser.text));source_addresses=set(address_literals(page_text))
    windows=[]; selected=[]; intervals={}
    for row in db.execute('SELECT * FROM research_windows WHERE pdf=? AND page=? ORDER BY end DESC,start DESC,rowid DESC',(pdf,page)):
        # Keep URL aliases distinct: AMP and regular reports can disclose different real queries.
        window=dict(row); engine=row['engine']; payload=json.loads(row['payload'])
        if mapping and payload.get('identityReviewReason')=='api_source_mapping_pending':
            payload=dict(payload,identityReviewRequired=False,verifiedSourcePdfId=pdf,identityResolution=mapping)
        reported_url=payload['verified']['url'];used=intervals.setdefault((engine,reported_url),[])
        overlap=any(row['start']<=end and row['end']>=start for start,end in used)
        window['selectedForGeneration']=not overlap
        all_queries=[dict(q) for q in db.execute('SELECT query,clicks,impressions,position FROM research_queries WHERE window_id=?',(row['id'],))]
        window['queries']=[q for q in all_queries if source_supported_query(q['query'],source_addresses)]
        window['privateAddressQueriesExcluded']=len(all_queries)-len(window['queries'])
        retained=sum(private_address_query(q['query']) for q in window['queries'])
        if retained:window['sourceBackedAddressQueriesRetained']=retained
        payload['verified']['queries']=[q for q in payload['verified']['queries'] if source_supported_query(q['query'],source_addresses)]
        window['payload']=payload; windows.append(window)
        if not overlap: used.append((row['start'],row['end'])); selected.append(row['end'])
    keywords=[{**dict(row),'payload':json.loads(row['payload'])} for row in db.execute('SELECT * FROM research_keywords WHERE pdf=? AND page=? ORDER BY observed_at DESC',(pdf,page))]
    result=dict(schemaVersion=1,sourcePdfId=pdf,page=page,url=record['url'],contentSha256=content['raw_sha256'],
                collectorModel=COLLECTOR[0],collectorEffort=COLLECTOR[1],generatorModel=GENERATOR[0],generatorEffort=GENERATOR[1],
                researchStage=record['stage'],partialResearch=record['stage']!='ready_for_generation',
                evidenceThrough=max(selected,default=''),context=context,pageText=page_text,
                searchWindows=windows,semrush=keywords,
                rules=['Use only facts supported by pageText and catalog identity.',
                       'Do not treat country volume as global demand; preserve missing KD and stale/refresh notices.',
                       'Do not infer undisclosed queries or combine overlapping windows/engine positions.',
                       'Reject purchase/price/driver/service-manual intent unless this exact page supports it.',
                       'Return plain title, H1, description, selected keywords, rationale and verbatim contentEvidence.'])
    if imported_candidates is not None:
        result.update(schemaVersion=2,pipeline='import_then_sol',collectorModel='application',collectorEffort='none',
                      researchStage='ready_for_model',partialResearch=False,semrushCandidates=imported_candidates)
        historical = historical_queries(windows)
        if historical:
            result['historicalQueryEvidence'] = historical
            result['rules'].append('Consider historical queries alongside current ones when the present page answers them. A query missing from the latest disclosed report has unknown current rank. Keep the original windows and avoid adding overlapping metrics.')
        result['rules'].append('Review every semrushCandidates entry in keywordDecisions before selecting supported keywords and writing metadata. No separate Terra stage is required.')
    if draft_coverage is not None:
        result.update(researchCoverage=draft_coverage,draftOnly=True)
        result['rules'].append('Semrush is optional for this draft. Missing reports/metrics are unknown, never zero or a no-results finding. Use available completed reports and source-supported historical queries. This draft cannot be activated until enrichment is complete.')
    ident=request_signature(result)
    existing=db.execute("SELECT bundle FROM research_requests WHERE semantic_hash=? ORDER BY (status='generated') DESC,created,id LIMIT 1",(ident,)).fetchone()
    if existing: return json.loads(existing['bundle'])
    result['requestId']=ident
    db.execute('INSERT OR IGNORE INTO research_requests(id,pdf,page,model,effort,created,bundle,status,semantic_hash) VALUES (?,?,?,?,?,?,?,?,?)',
               (ident,pdf,page,*GENERATOR,now(),packed(result),'pending',ident))
    return result


def import_generation(db,path,output=None):
    response=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    request=db.execute('SELECT * FROM research_requests WHERE id=?',(response['requestId'],)).fetchone()
    if not request: raise ValueError('Unknown generation request')
    requested_generator=(request['model'],request['effort'])
    if (response.get('model'),response.get('effort'))!=requested_generator:
        raise ValueError('Unexpected generating model/effort for this frozen request')
    rank=eligibility(db,request['pdf'],request['page'])
    if not rank['eligible']: raise ValueError('Ranking protection: '+rank['reason'])
    source=json.loads(request['bundle'])
    if 'sourceReviewEvidence' in response:
        from draft_reviews import evidence_is_current
        if not evidence_is_current(db,response['sourceReviewEvidence']):raise ValueError('Supplemental manual source changed')
    if source.get('pipeline')=='import_then_sol':
        from model_stage import validate_keyword_decisions
        validate_keyword_decisions(source,response)
    for name,limit in [('pageTitle',160),('h1Heading',180),('pageDescription',320)]:
        if not safe(response.get(name,''),limit): raise ValueError('Invalid plain metadata field: '+name)
    citations=response.get('contentEvidence',[])
    normalized=lambda s: re.sub(r'\s+',' ',unicodedata.normalize('NFKC',s)).casefold().strip()
    text=normalized(source['pageText'])
    if not citations or any(normalized(s) not in text or len(normalized(s))<5 for s in citations):
        raise ValueError('Content evidence is missing or not in the source page')
    # Numeric claims such as default IPs, capacities and model IDs must exist in the actual source/catalog.
    catalog={name:source['context'].get(name) for name in ('brand','models','headings')}
    allowed=normalized(source['pageText']+' '+packed(catalog)+' '+str(source['page']))
    numbers=set(re.findall(r'\d+(?:[.,-]\d+)*',allowed))
    for name in ('pageTitle','h1Heading','pageDescription'):
        for number in re.findall(r'\d+(?:[.,-]\d+)*',response[name]):
            if number not in numbers: raise ValueError('Unsupported numeric claim: '+number)
    current=db.execute('SELECT content_id FROM research_pages WHERE pdf=? AND page=?',(request['pdf'],request['page'])).fetchone()
    content=db.execute('SELECT raw_sha256 FROM research_content WHERE id=?',(current['content_id'],)).fetchone()
    if content['raw_sha256']!=source['contentSha256']: raise ValueError('Source content changed after generation request')
    if 'requiresReview' not in response or not isinstance(response['requiresReview'],bool):
        raise ValueError('Generation must explicitly declare requiresReview')
    if response.get('sourcePdfId',request['pdf'])!=request['pdf'] or response.get('page',request['page'])!=request['page']:
        raise ValueError('Generated page identity mismatch')
    if response.get('contentSha256',source['contentSha256'])!=source['contentSha256']:
        raise ValueError('Generated content hash mismatch')
    if output:
        if source.get('draftOnly'): raise ValueError('Semrush-deferred drafts cannot activate metadata')
        if source['partialResearch']: raise ValueError('Partial research cannot activate metadata')
        if response['requiresReview']: raise ValueError('Review-required metadata cannot activate automatically')
        refresh_stage(db,request['pdf'],request['page'])
        if source.get('pipeline')=='import_then_sol':
            from model_stage import page_bundle
            latest=page_bundle(db,request['pdf'],request['page'])
        else: latest=bundle(db,request['pdf'],request['page'])
        if request_signature(latest)!=request_signature(source):
            raise ValueError('Research changed after generation request; regenerate before activation')
    if source.get('researchCoverage') is not None:
        response=dict(response,researchCoverage=source['researchCoverage'],draftOnly=source.get('draftOnly',False))
    ident=key(response)
    status='needs_review' if response['requiresReview'] else 'draft_partial_research' if source['partialResearch'] else 'validated_draft'
    db.execute('INSERT OR IGNORE INTO research_metadata_versions VALUES (?,?,?,?,?,?,?,?,?)',
               (ident,request['id'],request['pdf'],request['page'],*requested_generator,now(),status,packed(response)))
    db.execute('UPDATE research_requests SET status=? WHERE id=?',('generated',request['id']))
    if source.get('pipeline')=='import_then_sol':
        for decision in response['keywordDecisions']:
            db.execute('INSERT OR IGNORE INTO research_model_keyword_decisions VALUES (?,?,?,?,?)',
                (ident,request['id'],decision['candidateId'],decision['decision'],packed(decision)))
    if output:
        value=dict(schemaVersion=1,status='active',sourcePdfId=request['pdf'],page=request['page'],contentSha256=source['contentSha256'],
                   pageTitle=response['pageTitle'],h1Heading=response['h1Heading'],pageDescription=response['pageDescription'],
                   evidenceThrough=source['evidenceThrough']+'T00:00:00Z',researchVersion=ident,generatorModel=request['model'],generatorEffort=request['effort'])
        destination=Path(output)/f'{request["pdf"]%1000:03d}'/str(request['pdf'])/f'{request["page"]}.json'
        if destination.exists():
            previous=json.loads(destination.read_text(encoding='utf-8'))
            if previous['evidenceThrough']>value['evidenceThrough']: raise ValueError('Older evidence cannot replace published metadata')
        atomic_json(destination,value)
    return dict(version=ident,status=status)


def generation_queue(db,limit,directory):
    """Resume pending work in newest-window/click order; unchanged generated requests leave the queue."""
    result=[]
    candidates=db.execute('''SELECT p.pdf,p.page,MAX(w.end) AS recent,MAX(w.page_clicks) AS clicks
      FROM research_pages p JOIN research_windows w ON w.pdf=p.pdf AND w.page=p.page
      WHERE p.stage='ready_for_generation' GROUP BY p.pdf,p.page ORDER BY recent DESC,clicks DESC,p.pdf,p.page''').fetchall()
    for row in candidates:
        if not eligibility(db,row['pdf'],row['page'])['eligible']: continue
        value=bundle(db,row['pdf'],row['page'])
        status=db.execute('SELECT status FROM research_requests WHERE id=?',(value['requestId'],)).fetchone()['status']
        if status=='generated': continue
        destination=Path(directory)/f'{row["pdf"]}-{row["page"]}-{value["requestId"][:12]}.json'
        if not destination.exists(): atomic_json(destination,value)
        result.append(dict(sourcePdfId=row['pdf'],page=row['page'],requestId=value['requestId'],bundle=str(destination)))
        if len(result)>=limit: break
    return result


def research_status(db):
    tables=('research_inventory','research_inventory_ui_observations','research_discovered_pages','research_pages','research_windows','research_queries',
            'research_keywords','research_content','research_requests','research_metadata_versions')
    return dict(recordedAt=now(),collector=dict(model=COLLECTOR[0],effort=COLLECTOR[1]),
                generator=dict(model=GENERATOR[0],effort=GENERATOR[1]),
                counts={table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in tables},
                stages={row['stage']:row['total'] for row in db.execute('SELECT stage,COUNT(*) total FROM research_pages GROUP BY stage')},
                pagesWithDrafts=db.execute('SELECT COUNT(*) FROM (SELECT pdf,page FROM research_metadata_versions GROUP BY pdf,page)').fetchone()[0],
                savedWindows=[dict(row) for row in db.execute('''SELECT engine,start,end,COUNT(DISTINCT CAST(pdf AS TEXT)||'/'||page) pages
                  FROM research_windows GROUP BY engine,start,end ORDER BY end DESC,start DESC,engine''')],
                coverageClaim='Saved provider evidence only; full provider history and site-wide activation are incomplete.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'artifacts/search-metadata/research.sqlite3')
    commands=parser.add_subparsers(dest='command',required=True)
    imp=commands.add_parser('import');imp.add_argument('manifests',type=Path,nargs='+');imp.add_argument('--run',default='seo-20261105')
    keywords=commands.add_parser('keyword-only');keywords.add_argument('manifest',type=Path)
    context=commands.add_parser('contexts');context.add_argument('file',type=Path)
    completion=commands.add_parser('source-completion');completion.add_argument('--converted',type=Path,required=True)
    completion.add_argument('--legacy',type=Path,required=True);completion.add_argument('--period')
    export=commands.add_parser('bundle');export.add_argument('--pdf',type=int,required=True);export.add_argument('--page',type=int,required=True)
    export.add_argument('--output',type=Path,required=True);export.add_argument('--allow-partial',action='store_true')
    generated=commands.add_parser('generation');generated.add_argument('file',type=Path);generated.add_argument('--activate-directory',type=Path)
    queued=commands.add_parser('queue');queued.add_argument('--limit',type=int,default=25);queued.add_argument('--directory',type=Path,required=True)
    inventory=commands.add_parser('inventory');inventory.add_argument('file',type=Path);inventory.add_argument('--start',required=True);inventory.add_argument('--end',required=True)
    inventory.add_argument('--engine',choices=('google','bing'),default='google');inventory.add_argument('--proof',type=Path)
    inventory_ui=commands.add_parser('inventory-ui');inventory_ui.add_argument('file',type=Path)
    commands.add_parser('resolve-ui-urls')
    pending=commands.add_parser('research-queue');pending.add_argument('--limit',type=int,default=25)
    contexts_pending=commands.add_parser('context-queue');contexts_pending.add_argument('--limit',type=int,default=25);contexts_pending.add_argument('--retry-unavailable',action='store_true')
    status=commands.add_parser('status');status.add_argument('--output',type=Path)
    args=parser.parse_args();args.db.parent.mkdir(parents=True,exist_ok=True)
    with connect(args.db) as db:
        init(db)
        if args.command=='import':
            start_run(db,args.run);print(packed({'imported':[import_page(db,p,args.run) for p in args.manifests]}))
        elif args.command=='keyword-only': print(packed(import_keyword_evidence(db,args.manifest)))
        elif args.command=='contexts':
            db.commit()  # Complete schema initialization before the retryable file transaction.
            print(packed({'contexts':import_context_file(db,args.file)}))
        elif args.command=='source-completion':
            from source_completion import finalize_export
            db.commit()
            print(packed(finalize_export(db,args.converted,args.legacy,args.period)))
        elif args.command=='bundle':
            value=bundle(db,args.pdf,args.page,args.allow_partial);atomic_json(args.output,value);print(packed({'requestId':value['requestId'],'partial':value['partialResearch']}))
        elif args.command=='generation': print(packed(import_generation(db,args.file,args.activate_directory)))
        elif args.command=='queue':
            if not 1<=args.limit<=1000: raise ValueError('Queue limit must be 1..1000')
            print(packed(generation_queue(db,args.limit,args.directory)))
        elif args.command=='inventory': print(packed(import_inventory(db,args.file,args.start,args.end,args.engine,args.proof)))
        elif args.command=='inventory-ui': print(packed(import_inventory_ui(db,args.file)))
        elif args.command=='resolve-ui-urls': print(packed(resolve_ui_urls(db)))
        elif args.command=='research-queue':
            if not 1<=args.limit<=1000: raise ValueError('Queue limit must be 1..1000')
            print(packed(research_queue(db,args.limit)))
        elif args.command=='context-queue':
            if not 1<=args.limit<=1000: raise ValueError('Queue limit must be 1..1000')
            print(packed(context_queue(db,args.limit,args.retry_unavailable)))
        else:
            value=research_status(db)
            if args.output: atomic_json(args.output,value)
            print(packed(value))


if __name__=='__main__':
    try: main()
    except (ValueError,sqlite3.IntegrityError) as error: raise SystemExit(str(error))
