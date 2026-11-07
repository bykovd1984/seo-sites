"""Resumable, budget-bounded Semrush requests and content-bound Terra reviews.

Planning, status and review use local data only. Collection requires explicit
approval and a cumulative API-unit ceiling; uncertain requests are never retried.
"""
import argparse
import base64
import csv
import datetime as dt
import io
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

from generate import PageText, atomic_json, plain
from history import connect
from ranking_policy import eligibility
from research import (ROOT, COLLECTOR, artifact, init as research_init, key, metric,
                      now, packed, private_address_query, refresh_stage)

METRICS_URL = 'https://api.semrush.com/apis/v4/keywords/v1/metrics'
RELATED_URL = 'https://api.semrush.com/'
COUNTRIES = frozenset('''AF AL DZ AO AR AM AU AT AZ BS BH BD BY BE BZ BO BA BW BR BN BG KH CM CA CV CL CO CR HR CY CZ CD DK DO EC EG SV EE ET FI FR GE DE GH GR GT GY HT HN HK HU IS IN ID IE IL IT JM JP JO KZ KW LV LB LY LT LU MG MY MT MU MX MD MN ME MA MZ NA NP NL NZ NI NG NO OM PK PA PY PE PH PL PT QA RO RU SA SN RS SG SK SI ZA KR ES LK SE CH TW TH TT TN TR UA AE UK US UY VE VN ZM ZW'''.split())


def init(db):
    research_init(db)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS semrush_jobs (
      id TEXT PRIMARY KEY, request TEXT NOT NULL, max_units INTEGER NOT NULL,
      reserved_units INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
      created TEXT NOT NULL, updated TEXT NOT NULL, artifact_id TEXT, result TEXT, error TEXT);
    CREATE TABLE IF NOT EXISTS semrush_links (
      job_id TEXT NOT NULL,pdf INTEGER NOT NULL,page INTEGER NOT NULL,content_sha256 TEXT NOT NULL,
      seed TEXT NOT NULL,recent TEXT NOT NULL,clicks INTEGER NOT NULL,
      PRIMARY KEY(job_id,pdf,page,content_sha256,seed));
    CREATE TABLE IF NOT EXISTS semrush_reviews (
      id TEXT PRIMARY KEY,job_id TEXT NOT NULL,pdf INTEGER NOT NULL,page INTEGER NOT NULL,
      content_sha256 TEXT NOT NULL,keyword TEXT NOT NULL,decision TEXT NOT NULL,
      artifact_id TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS semrush_seed_sources (
      job_id TEXT NOT NULL,pdf INTEGER NOT NULL,page INTEGER NOT NULL,content_sha256 TEXT NOT NULL,
      seed TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,
      PRIMARY KEY(job_id,pdf,page,content_sha256,seed));
    ''')


def context(db,pdf,page):
    row=db.execute('''SELECT c.raw_sha256,c.context_zlib FROM research_pages p
        JOIN research_content c ON c.id=p.content_id WHERE p.pdf=? AND p.page=?''',(pdf,page)).fetchone()
    if not row: raise ValueError('Exact page context is required')
    value=json.loads(zlib.decompress(row['context_zlib']))
    raw=base64.b64decode(value.pop('rawHtmlBase64'))
    parser=PageText()
    parser.feed(raw.decode('utf-8' if value.get('type')=='legacy_seo_example' else 'utf-8-sig'))
    return row['raw_sha256'],plain(' '.join(parser.text))


def selected_queries(db,pdf,page,start=None,end=None):
    """Keep URL aliases separate and never sum overlapping observation windows."""
    used={}; totals={}
    for window in db.execute('''SELECT * FROM research_windows WHERE pdf=? AND page=?
            AND (? IS NULL OR start>=?) AND (? IS NULL OR end<=?)
            ORDER BY end DESC,start DESC,rowid DESC''',(pdf,page,start,start,end,end)):
        payload=json.loads(window['payload'])
        url=payload['verified']['url']
        intervals=used.setdefault((window['engine'],url),[])
        if any(window['start']<=end and window['end']>=start for start,end in intervals): continue
        intervals.append((window['start'],window['end']))
        for row in db.execute('SELECT * FROM research_queries WHERE window_id=?',(window['id'],)):
            query=row['query']
            if private_address_query(query) or not 1<=len(query)<=255: continue
            total=totals.setdefault(query,dict(query=query,clicks=0,impressions=0,recent=window['end'],
                                               kind='reported_query',windowIds=[]))
            total['clicks']+=row['clicks'];total['impressions']+=row['impressions']
            total['windowIds'].append(window['id'])
    return sorted(totals.values(),key=lambda r:(r['recent'],r['clicks'],r['impressions'],r['query']),reverse=True)


def add_job(db,request,pdf,page,sha,seed,recent,clicks):
    ident=key(request)
    units=0 if request['method']=='toolspd_keywordmagic' else 20 if request['method']=='metrics_v4' else 40*request['limit']
    db.execute('''INSERT OR IGNORE INTO semrush_jobs(id,request,max_units,status,created,updated)
        VALUES (?,?,?,'planned',?,?)''',(ident,packed(request),units,now(),now()))
    return db.execute('INSERT OR IGNORE INTO semrush_links VALUES (?,?,?,?,?,?,?)',
                      (ident,pdf,page,sha,seed,recent,clicks)).rowcount


def content_seeds(db,pdf,page,recent):
    """Create labelled lookup seeds from actual source headings and catalog data."""
    row=db.execute('''SELECT c.* FROM research_pages p JOIN research_content c ON c.id=p.content_id
        WHERE p.pdf=? AND p.page=?''',(pdf,page)).fetchone()
    if not row: return []
    value=json.loads(zlib.decompress(row['context_zlib']))
    parser=PageText();parser.feed(base64.b64decode(value['rawHtmlBase64']).decode(
        'utf-8' if value.get('type')=='legacy_seo_example' else 'utf-8-sig'))
    brand=value.get('brand','');models=value.get('models',[])
    if not isinstance(brand,str) or not isinstance(models,list): return []
    catalog=plain(' '.join([brand]+[s for s in models[:1] if isinstance(s,str)]))
    headings=[plain(h) for h in parser.headings if 5<=len(plain(h))<=140]
    phrases=[plain(catalog+' '+h) for h in headings] if headings else [catalog]
    result=[]
    for phrase in dict.fromkeys(phrases):
        if not 3<=len(phrase)<=255 or private_address_query(phrase): continue
        result.append(dict(query=phrase,clicks=0,impressions=0,recent=recent,kind='content_derived',
                           contentSha256=row['raw_sha256'],sourceArtifact=row['source_artifact'],
                           limitation='A lookup seed from source content/catalog, not an observed search query.'))
    return result


def plan(db,country,month,page_limit=10,seeds=2,related_limit=0,start=None,end=None,transport='api'):
    if transport not in ('api','toolspd'): raise ValueError('Unknown Semrush transport')
    country=country.upper()
    if country not in COUNTRIES: raise ValueError('Country must be a documented Semrush database code (for example US or UK)')
    try: snapshot=dt.date.fromisoformat(month+'-01')
    except ValueError: raise ValueError('Month must be YYYY-MM') from None
    if not dt.date(2012,1,1)<=snapshot<=dt.date.today(): raise ValueError('Invalid Semrush snapshot month')
    if not 1<=page_limit<=1000 or not 1<=seeds<=20 or not 0<=related_limit<=100:
        raise ValueError('Invalid page, seed or related-row limit')
    pages=links=0;job_ids=set()
    rows=db.execute('''SELECT p.pdf,p.page,MAX(w.end) recent FROM research_pages p
        JOIN research_windows w ON w.pdf=p.pdf AND w.page=p.page
        WHERE p.content_id IS NOT NULL AND p.stage!='identity_review'
        AND (? IS NULL OR w.start>=?) AND (? IS NULL OR w.end<=?)
        GROUP BY p.pdf,p.page ORDER BY recent DESC,MAX(w.page_clicks) DESC,p.pdf,p.page''',(start,start,end,end)).fetchall()
    for row in rows:
        if not eligibility(db,row['pdf'],row['page'])['eligible']: continue
        queries=selected_queries(db,row['pdf'],row['page'],start,end)
        include_impressions = transport == 'toolspd'
        page_traffic=db.execute('''SELECT 1 FROM research_windows WHERE pdf=? AND page=?
            AND (page_clicks>0 OR (? AND page_impressions>0))
            AND (? IS NULL OR start>=?) AND (? IS NULL OR end<=?) LIMIT 1''',
            (row['pdf'],row['page'],include_impressions,start,start,end,end)).fetchone()
        query_traffic = any(q['clicks'] > 0 or (include_impressions and q['impressions'] > 0) for q in queries)
        if not query_traffic and not page_traffic: continue
        if not queries: queries=content_seeds(db,row['pdf'],row['page'],row['recent'])
        sha,_=context(db,row['pdf'],row['page']); inserted=0
        for query in queries[:seeds]:
            common=dict(keyword=query['query'],country=country)
            requests=[dict(method='metrics_v4',month=month,**common)]
            # v3 is optional and explicitly identified; its endpoint has no monthly snapshot parameter.
            if related_limit: requests.append(dict(method='related_v3',limit=related_limit,**common))
            if transport=='toolspd':
                requests=[dict(method='toolspd_keywordmagic',month=month,limit=100,**common)]
            for request in requests:
                inserted+=add_job(db,request,row['pdf'],row['page'],sha,query['query'],query['recent'],query['clicks'])
                db.execute('INSERT OR IGNORE INTO semrush_seed_sources VALUES (?,?,?,?,?,?,?)',
                    (key(request),row['pdf'],row['page'],sha,query['query'],query['kind'],packed(query)))
                job_ids.add(key(request))
                if transport=='toolspd': replace_unspent_api_jobs(db,request)
        if inserted: pages+=1;links+=inserted
        if pages>=page_limit: break
    return dict(pagesPlanned=pages,newLinks=links,jobIds=sorted(job_ids),**status(db))


def replace_unspent_api_jobs(db,request):
    """Preserve old plans, explicitly replacing them with a labelled UI lookup."""
    target=key(request)
    for job in db.execute("SELECT id,request FROM semrush_jobs WHERE status='planned' AND reserved_units=0").fetchall():
        old=json.loads(job['request'])
        if old.get('method') not in ('metrics_v4','related_v3'): continue
        if (old.get('keyword'),old.get('country'),old.get('month',request['month']))!=(request['keyword'],request['country'],request['month']): continue
        db.execute('INSERT OR IGNORE INTO semrush_links SELECT ?,pdf,page,content_sha256,seed,recent,clicks FROM semrush_links WHERE job_id=?',(target,job['id']))
        db.execute('INSERT OR IGNORE INTO semrush_seed_sources SELECT ?,pdf,page,content_sha256,seed,kind,payload FROM semrush_seed_sources WHERE job_id=?',(target,job['id']))
        db.execute("UPDATE semrush_jobs SET status='superseded',updated=?,error=? WHERE id=?",(now(),'Replaced by ToolsPD UI lookup '+target,job['id']))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def fetch(request,api_key):
    """One attempt only. Never log an exception containing a credential URL."""
    if request['method']=='metrics_v4':
        endpoint=METRICS_URL
        fields={name:request[name] for name in ('keyword','country','month')}
        headers={'Authorization':'Apikey '+api_key}
    else:
        endpoint=RELATED_URL
        fields=dict(type='phrase_related',key=api_key,phrase=request['keyword'],
                    database=request['country'].lower(),display_limit=request['limit'],
                    export_columns='Ph,Nq,Kd,Co',export_decode=1,export_escape=1)
        headers={}
    url=endpoint+'?'+urllib.parse.urlencode(fields)
    try:
        opener=urllib.request.build_opener(NoRedirect())
        with opener.open(urllib.request.Request(url,headers=headers),timeout=45) as response:
            raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024: raise RuntimeError('Semrush response exceeds 4 MiB')
        return raw.decode('utf-8-sig').replace(api_key,'[REDACTED]')
    except urllib.error.HTTPError as exc:
        raise RuntimeError('Semrush HTTP '+str(exc.code)) from None
    except (OSError,UnicodeError):
        raise RuntimeError('Semrush connection or response decoding failed') from None


def parse(request,body):
    if request['method']=='metrics_v4':
        result=json.loads(body);meta=result.get('meta',{});data=result.get('data')
        if (meta.get('success') is not True or meta.get('country')!=request['country'] or
            meta.get('keyword')!=request['keyword'] or meta.get('month')!=request['month'] or not isinstance(data,dict)):
            raise ValueError('Semrush response context or success mismatch')
        volume=metric(data.get('search_volume'),True);kd=metric(data.get('keyword_difficulty'))
        if kd is not None and kd>100: raise ValueError('Invalid organic keyword difficulty')
        return [dict(keyword=request['keyword'],volume=volume,kd=kd,
                     advertiserCompetition=data.get('competitive_density'),status='reported',snapshot=meta['month'])]
    if body.strip()=='ERROR 50 :: NOTHING FOUND':
        return [dict(keyword=request['keyword'],volume=None,kd=None,status='nothing found',snapshot=None)]
    if body.lstrip().startswith('ERROR'): raise ValueError('Semrush reported an API error')
    reader=csv.DictReader(io.StringIO(body),delimiter=';')
    fields=set(reader.fieldnames or [])
    kd_column='Keyword Difficulty Index' if 'Keyword Difficulty Index' in fields else 'Keyword Difficulty'
    if not {'Keyword','Search Volume',kd_column,'Competition'}<=fields:
        raise ValueError('Unexpected Semrush related-keyword columns')
    rows=[]
    for row in reader:
        keyword=row['Keyword'].strip();kd=metric(row[kd_column])
        if not 1<=len(keyword)<=255 or kd is not None and kd>100: raise ValueError('Invalid Semrush keyword row')
        rows.append(dict(keyword=keyword,volume=metric(row['Search Volume'],True),kd=kd,
                         advertiserCompetition=row['Competition'],status='reported',snapshot=None))
    if not rows or len(rows)>request['limit']: raise ValueError('Unexpected Semrush related-keyword row count')
    return rows


def status(db):
    return dict(jobs={r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) n FROM semrush_jobs GROUP BY status')},
                reservedUnits=db.execute('SELECT COALESCE(SUM(reserved_units),0) FROM semrush_jobs').fetchone()[0],
                plannedMaximumUnits=db.execute("SELECT COALESCE(SUM(max_units),0) FROM semrush_jobs WHERE status='planned'").fetchone()[0],
                reviews=db.execute('SELECT COUNT(*) FROM semrush_reviews').fetchone()[0])


def collect(db,directory,api_key,approved=False,max_units=0,limit=10,transport=fetch,allowed_job_ids=None):
    if not approved: raise ValueError('Explicit API-key-use approval is required')
    if not api_key: raise ValueError('SEMRUSH_API_KEY is not configured')
    if max_units<1 or not 1<=limit<=1000: raise ValueError('A positive cumulative API-unit ceiling and batch limit are required')
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'artifacts'): raise ValueError('Evidence must be inside workspace artifacts')
    directory.mkdir(parents=True,exist_ok=True)
    if db.in_transaction: raise ValueError('Commit planning before collection')
    completed=0
    for _ in range(limit):
        # Reserve and commit before a network call. Other workers and crashes cannot
        # reuse this budget. An uncertain charge requires explicit reconciliation.
        db.execute('BEGIN IMMEDIATE')
        spent=status(db)['reservedUnits']
        jobs=db.execute('''SELECT j.* FROM semrush_jobs j WHERE j.status='planned'
            ORDER BY (SELECT MAX(recent) FROM semrush_links l WHERE l.job_id=j.id) DESC,
                     (SELECT MAX(clicks) FROM semrush_links l WHERE l.job_id=j.id) DESC,j.created,j.id''').fetchall()
        job=next((j for j in jobs if json.loads(j['request'])['method'] in ('metrics_v4','related_v3')
                  and (allowed_job_ids is None or j['id'] in allowed_job_ids) and eligible_links(db,j['id'])),None)
        if not job or spent+job['max_units']>max_units:
            db.commit();break
        db.execute("UPDATE semrush_jobs SET status='reserved',reserved_units=max_units,updated=? WHERE id=?",(now(),job['id']))
        db.commit()
        request=json.loads(job['request'])
        try:
            body=transport(request,api_key).replace(api_key,'[REDACTED]')
            path=directory/(job['id']+'.json')
            atomic_json(path,dict(request=request,observedAt=now(),body=body))
            with db:
                proof=artifact(db,path,'semrush_api',METRICS_URL if request['method']=='metrics_v4' else RELATED_URL)
                db.execute('UPDATE semrush_jobs SET artifact_id=? WHERE id=?',(proof,job['id']))
            result=parse(request,body)
            with db:
                db.execute("UPDATE semrush_jobs SET status='done',result=?,updated=? WHERE id=?",(packed(result),now(),job['id']))
            completed+=1
        except Exception as exc:
            # Do not expose server text or potentially credential-bearing exceptions.
            with db:
                db.execute("UPDATE semrush_jobs SET status='uncertain',error=?,updated=? WHERE id=?",(type(exc).__name__,now(),job['id']))
            break
    return dict(completedRequests=completed,**status(db))


def eligible_links(db,job_id):
    return any(eligibility(db,r['pdf'],r['page'])['eligible'] for r in db.execute('''
        SELECT l.pdf,l.page FROM semrush_links l
        JOIN research_pages p ON p.pdf=l.pdf AND p.page=l.page
        JOIN research_content c ON c.id=p.content_id
        WHERE l.job_id=? AND p.stage!='identity_review' AND c.raw_sha256=l.content_sha256''',(job_id,)))


def candidates(db,limit=100):
    if not 1<=limit<=10000: raise ValueError('Candidate limit must be 1..10000')
    result=[]
    for link in db.execute('''SELECT l.*,j.request,j.result,j.artifact_id FROM semrush_links l
        JOIN semrush_jobs j ON j.id=l.job_id WHERE j.status='done' ORDER BY l.recent DESC,l.clicks DESC,l.pdf,l.page'''):
        sha,text=context(db,link['pdf'],link['page'])
        if sha!=link['content_sha256']: continue
        if not eligibility(db,link['pdf'],link['page'])['eligible']: continue
        if db.execute('SELECT stage FROM research_pages WHERE pdf=? AND page=?',(link['pdf'],link['page'])).fetchone()[0]=='identity_review': continue
        for item in json.loads(link['result']):
            ident=key((link['job_id'],link['pdf'],link['page'],sha,item['keyword']))
            if db.execute('SELECT 1 FROM semrush_reviews WHERE id=?',(ident,)).fetchone(): continue
            value=dict(reviewId=ident,jobId=link['job_id'],sourcePdfId=link['pdf'],page=link['page'],
                       contentSha256=sha,seed=link['seed'],request=json.loads(link['request']),
                       sourceArtifact=link['artifact_id'],candidate=item,pageText=text)
            if not any(r['reviewId']==ident for r in result): result.append(value)
            if len(result)>=limit: return result
    return result


def review(db,path):
    value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if (value.get('model'),value.get('effort'))!=COLLECTOR: raise ValueError('Expected Terra High review')
    observations=value.get('reviews',[])
    if not 1<=len(observations)<=1000: raise ValueError('Expected 1..1000 keyword reviews')
    # Validate against fresh, exact content and actual completed requests.
    approved=[]
    for item in observations:
        pdf,page=item['sourcePdfId'],item['page'];sha,text=context(db,pdf,page)
        if item.get('contentSha256')!=sha: raise ValueError('Review source context changed')
        job=db.execute("SELECT * FROM semrush_jobs WHERE id=? AND status='done'",(item['jobId'],)).fetchone()
        if not job: raise ValueError('Unknown completed Semrush request')
        link=db.execute('SELECT * FROM semrush_links WHERE job_id=? AND pdf=? AND page=? AND content_sha256=?',
                        (job['id'],pdf,page,sha)).fetchone()
        if not link: raise ValueError('Semrush request is not linked to this page context')
        candidate=next((r for r in json.loads(job['result']) if r['keyword']==item['keyword']),None)
        if not candidate: raise ValueError('Keyword absent from Semrush response')
        decision=item.get('decision')
        if decision not in ('keep','reject','no_results') or not str(item.get('reason','')).strip(): raise ValueError('Review needs decision and reason')
        normalize=lambda s:re.sub(r'\s+',' ',unicodedata.normalize('NFKC',s)).casefold().strip()
        excerpts=item.get('contentEvidence',[])
        if decision=='keep' and (not excerpts or any(not isinstance(s,str) or len(normalize(s))<5 or normalize(s) not in normalize(text) for s in excerpts)):
            raise ValueError('Retained keyword needs verbatim page content evidence')
        if (decision=='no_results')!=(candidate['status']=='nothing found'):
            if decision!='reject': raise ValueError('No-results decision does not match provider evidence')
        ident=key((job['id'],pdf,page,sha,item['keyword']))
        approved.append((ident,item,job,link,candidate))
    proof=artifact(db,path,'terra_semrush_review')
    inserted=0
    for ident,item,job,link,candidate in approved:
        added=db.execute('INSERT OR IGNORE INTO semrush_reviews VALUES (?,?,?,?,?,?,?,?,?)',
            (ident,job['id'],item['sourcePdfId'],item['page'],item['contentSha256'],item['keyword'],item['decision'],proof,packed(item))).rowcount
        inserted+=added
        if added and item['decision']!='reject':
            request=json.loads(job['request'])
            payload=dict(item,apiArtifact=job['artifact_id'],reviewArtifact=proof,providerMetrics=candidate)
            db.execute('INSERT OR IGNORE INTO research_keywords VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident,item['sourcePdfId'],item['page'],link['seed'],item['keyword'],request['country'].lower(),
                 candidate['volume'],candidate['kd'],METRICS_URL if request['method']=='metrics_v4' else RELATED_URL,
                 job['updated'],'nothing found' if item['decision']=='no_results' else 'observed',item['reason'],
                 job['artifact_id'],packed(payload),*COLLECTOR))
        refresh_stage(db,item['sourcePdfId'],item['page'])
    return dict(importedReviews=inserted)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'artifacts/search-metadata/research.sqlite3')
    sub=parser.add_subparsers(dest='command',required=True)
    plan_cmd=sub.add_parser('plan');plan_cmd.add_argument('--country',required=True)
    plan_cmd.add_argument('--month',default=dt.date.today().strftime('%Y-%m'))
    plan_cmd.add_argument('--pages',type=int,default=10);plan_cmd.add_argument('--seeds',type=int,default=2)
    plan_cmd.add_argument('--related-limit',type=int,default=0,help='Optional deprecated v3 expansion; 40 units per maximum returned row')
    collect_cmd=sub.add_parser('collect');collect_cmd.add_argument('--approved-api-use',action='store_true')
    collect_cmd.add_argument('--max-units',type=int,default=0);collect_cmd.add_argument('--limit',type=int,default=10)
    collect_cmd.add_argument('--directory',type=Path,default=ROOT/'artifacts/search-metadata/semrush-api')
    candidate_cmd=sub.add_parser('candidates');candidate_cmd.add_argument('--output',type=Path,required=True)
    candidate_cmd.add_argument('--limit',type=int,default=100)
    review_cmd=sub.add_parser('review');review_cmd.add_argument('file',type=Path)
    sub.add_parser('status')
    args=parser.parse_args();args.db.parent.mkdir(parents=True,exist_ok=True)
    with connect(args.db) as db:
        init(db);db.commit()
        if args.command=='plan': value=plan(db,args.country,args.month,args.pages,args.seeds,args.related_limit)
        elif args.command=='collect': value=collect(db,args.directory,os.getenv('SEMRUSH_API_KEY'),args.approved_api_use,args.max_units,args.limit)
        elif args.command=='candidates':
            result=candidates(db,args.limit);atomic_json(args.output,result);value=dict(candidates=len(result),output=str(args.output))
        elif args.command=='review': value=review(db,args.file)
        else: value=status(db)
        print(packed(value))


if __name__=='__main__':
    try: main()
    except (ValueError,RuntimeError) as exc: raise SystemExit(str(exc))
