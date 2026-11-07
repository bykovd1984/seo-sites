"""ToolsPD UI collector: isolated login, bounded requests, durable evidence, no private API calls."""
import datetime as dt
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import getpass
import time
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from generate import atomic_json
from history import connect
from research import ROOT, artifact, key, now, packed, private_address_query
from semrush_workflow import eligible_links, init, plan, status

DEFAULT_ORIGIN='https://sktiman.toolspd.com'
SCRIPT=Path(__file__).with_name('capture_semrush_ui.js').read_text(encoding='utf-8')
COUNTRY_LABELS={'US':('United States',),'UK':('United Kingdom',),'UA':('Ukraine',),'RU':('Russia',),
                'TR':('Turkey','Türkiye'),'DE':('Germany',),'FR':('France',),'IT':('Italy',),
                'ES':('Spain',),'PL':('Poland',),'IN':('India',),'CA':('Canada',),'AU':('Australia',)}


class ReportUnavailable(ValueError):
    def __init__(self,reason): super().__init__(reason);self.reason=reason


def normalize(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value)).replace('\u200b','')).strip().casefold()


def origin(value):
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or not parsed.hostname.endswith('.toolspd.com') or parsed.username or parsed.password or parsed.port is not None:
        raise ValueError('Use an HTTPS ToolsPD subdomain without credentials or port')
    if parsed.path not in ('','/') or parsed.query or parsed.fragment: raise ValueError('ToolsPD origin must not contain a path or query')
    return 'https://'+parsed.hostname


def url(request,base=DEFAULT_ORIGIN):
    return origin(base)+'/analytics/keywordmagic/?'+urlencode(dict(q=request['keyword'],db=request['country'].lower(),type='all',mode=1))


def number(value,maximum=None):
    text=normalize(value)
    if text in ('','n/a','na','-','—','none'): return None
    match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*([kmb]?)',text.replace(',','').replace(' ',''))
    if not match: raise ValueError('Invalid visible Semrush metric')
    result=float(match[1])*{'':1,'k':1000,'m':1000000,'b':1000000000}[match[2]]
    if not math.isfinite(result) or maximum is not None and result>maximum: raise ValueError('Semrush metric outside allowed range')
    return result


def parse_snapshot(request,value,base=DEFAULT_ORIGIN):
    if value.get('kind')!='toolspd_keywordmagic_ui' or value.get('schemaVersion')!=1: raise ValueError('Unexpected ToolsPD evidence schema')
    source=urlsplit(value.get('sourceUrl',''));params=parse_qs(source.query)
    if source.scheme+'://'+source.netloc!=origin(base) or source.path!='/analytics/keywordmagic/': raise ValueError('ToolsPD report source mismatch')
    if params.get('q')!=[request['keyword']] or params.get('db')!=[request['country'].lower()] or params.get('type')!=['all'] or params.get('mode',['1'])!=['1']:
        raise ValueError('ToolsPD report query or database mismatch')
    text=normalize(value.get('pageText',''))
    if any(s in text for s in ('captcha','verify you are human','unusual traffic','access denied')): raise ReportUnavailable('challenge')
    if any(s in text for s in ('daily limit reached','limit exceeded','something went wrong','a timeout occurred','error 524')): raise ReportUnavailable('provider_unavailable')
    if normalize(value.get('heading',''))!='keyword magic tool: '+normalize(request['keyword']): raise ReportUnavailable('report_not_ready_or_login_required')
    if not value.get('countryLabel'): raise ReportUnavailable('report_not_ready_or_login_required')
    if value.get('countryLabel') not in COUNTRY_LABELS.get(request['country'],()): raise ValueError('Visible Semrush country does not match the requested database')
    observed=dt.datetime.fromisoformat(value['observedAt'].replace('Z','+00:00'))
    if observed.tzinfo is None or observed>dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5): raise ValueError('Invalid report observation timestamp')
    if observed.strftime('%Y-%m')!=request['month']: raise ValueError('A current UI report cannot satisfy a different historical snapshot month')
    raw=value.get('rows');headers=value.get('headers')
    if not isinstance(raw,list) or not isinstance(headers,list) or len(raw)>request['limit']: raise ValueError('Invalid visible report row count')
    if not raw:
        # The current UI can render its empty-state outside the keyword table.
        # Accept its explicit standalone message only after all report-scope
        # and provider-error checks above. Missing rows alone remain unknown.
        empty_lines={normalize(line).replace('\u2019', "'").rstrip('.')
                     for line in value.get('pageText','').splitlines()}
        explicit_empty="we couldn't find any data related to your request" in empty_lines
        if not explicit_empty and 'nothing found' not in normalize(value.get('tableText','')):
            raise ReportUnavailable('report_not_ready_or_login_required')
        return [dict(keyword=request['keyword'],volume=None,kd=None,status='nothing found',snapshot=None,
                     scope='country',country=request['country'],limitation='Explicit UI no-results report; not proof of zero search demand.')]
    normalized=[normalize(h) for h in headers]
    if any(normalized.count(h)!=1 for h in ('keyword','volume','kd %')): raise ValueError('Visible keyword, volume and KD columns are required')
    result=[];seen=set()
    for row in raw:
        if not isinstance(row,list) or len(row)!=len(headers): raise ValueError('Report columns changed')
        values=dict(zip(normalized,row));keyword=str(values['keyword']).replace('\u200b','').strip()
        if not 1<=len(keyword)<=255 or any(ord(c)<32 for c in keyword) or private_address_query(keyword): continue
        if normalize(keyword) in seen: continue
        seen.add(normalize(keyword))
        result.append(dict(keyword=keyword,volume=number(values['volume']),kd=number(values['kd %'],100),
                           cpc=number(values['cpc (usd)']) if 'cpc (usd)' in values else None,
                           intent=values.get('intent'),updatedLabel=values.get('updated'),status='reported',snapshot=None,
                           scope='country',country=request['country'],limitation=value.get('coverage','Rendered UI subset only.')))
    if not result: raise ValueError('No admissible keyword observations')
    return result


def init_ui(db):
    init(db)
    db.executescript('''CREATE TABLE IF NOT EXISTS semrush_ui_attempts (
      id TEXT PRIMARY KEY,job_id TEXT NOT NULL,started TEXT NOT NULL,status TEXT NOT NULL,
      artifact_id TEXT,error TEXT);
      CREATE INDEX IF NOT EXISTS semrush_ui_attempts_day ON semrush_ui_attempts(started);''')


def pending(db,limit=10,base=DEFAULT_ORIGIN):
    if not 1<=limit<=100: raise ValueError('Batch limit must be 1..100')
    items=[]
    for job in db.execute("SELECT * FROM semrush_jobs WHERE status='planned' ORDER BY (SELECT MAX(recent) FROM semrush_links WHERE job_id=semrush_jobs.id) DESC,(SELECT MAX(clicks) FROM semrush_links WHERE job_id=semrush_jobs.id) DESC,id"):
        request=json.loads(job['request'])
        if request['method']!='toolspd_keywordmagic' or not eligible_links(db,job['id']): continue
        items.append(dict(jobId=job['id'],request=request,url=url(request,base)))
        if len(items)>=limit: break
    return items


def ingest_snapshot(db,job_id,path,base=DEFAULT_ORIGIN,attempt=None):
    job=db.execute('SELECT * FROM semrush_jobs WHERE id=?',(job_id,)).fetchone()
    if not job or json.loads(job['request'])['method']!='toolspd_keywordmagic': raise ValueError('Unknown ToolsPD UI job')
    if job['status']=='done': return dict(imported=False,jobId=job_id,reason='already_done')
    if not eligible_links(db,job_id): raise ValueError('Current page content or ranking protection no longer permits this lookup')
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT/'artifacts') or path.stat().st_size>2*1024*1024: raise ValueError('Evidence must be a bounded workspace artifact')
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    result=parse_snapshot(json.loads(job['request']),value,base)
    proof=artifact(db,path,'semrush_toolspd_ui',value['sourceUrl'])
    db.execute("UPDATE semrush_jobs SET status='done',artifact_id=?,result=?,updated=?,error=NULL WHERE id=?",
               (proof,packed(result),value['observedAt'],job_id))
    if attempt: db.execute("UPDATE semrush_ui_attempts SET status='done',artifact_id=? WHERE id=?",(proof,attempt))
    db.commit()
    return dict(imported=True,jobId=job_id,candidates=len(result),sourceArtifact=proof,coverage=value.get('coverage'))


def reserve(db,job_id,daily_limit,followup=False):
    if not 1<=daily_limit<=100: raise ValueError('Daily limit must be 1..100')
    db.execute('BEGIN IMMEDIATE')
    try:
        count=db.execute('SELECT COUNT(*) FROM semrush_ui_attempts WHERE substr(started,1,10)=?',(now()[:10],)).fetchone()[0]
        if count>=daily_limit: db.rollback();return None
        changed=db.execute("UPDATE semrush_jobs SET status='ui_reserved',updated=? WHERE id=? AND status=?",(now(),job_id,'ui_reserved' if followup else 'planned')).rowcount
        if not changed: db.rollback();return None
        ident=key((job_id,uuid.uuid4().hex));db.execute('INSERT INTO semrush_ui_attempts VALUES (?,?,?,\'reserved\',NULL,NULL)',(ident,job_id,now()))
        db.commit();return ident
    except Exception: db.rollback();raise


def retry(db,job_id):
    row=db.execute('SELECT request,status FROM semrush_jobs WHERE id=?',(job_id,)).fetchone()
    if not row or json.loads(row['request'])['method']!='toolspd_keywordmagic' or row['status'] not in ('ui_reserved','ui_blocked','login_required'):
        raise ValueError('Only an unfinished ToolsPD attempt can be explicitly retried')
    db.execute("UPDATE semrush_jobs SET status='planned',error=NULL,updated=? WHERE id=?",(now(),job_id));db.commit()
    return dict(requeued=job_id,limitation='Earlier attempts remain counted against the daily ceiling.')


def protect_profile(path,home=None):
    path=Path(path).resolve()
    if home is None:
        if not path.is_relative_to(ROOT/'artifacts'): raise ValueError('Browser profile must be in ignored workspace artifacts')
    elif path != Path(home).resolve()/'toolspd-profile':
        raise ValueError('Browser profile must belong to the configured shared data directory')
    path.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        result=subprocess.run(['icacls.exe',str(path),'/inheritance:r','/grant:r',getpass.getuser()+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],capture_output=True)
        if result.returncode: raise ValueError('Could not restrict the browser profile permissions')
    else: path.chmod(0o700)
    return path


def run_worker(db,profile,directory,limit=5,daily_limit=20,delay=15,base=DEFAULT_ORIGIN,channel='msedge',login=False):
    # Legacy reports used a separate request ledger and must not bypass the shared broker.
    raise ValueError('Direct ToolsPD browser collection/login is disabled. Use the shared seo-research MCP queue or its toolspd-login command.')
