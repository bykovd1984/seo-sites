"""Source-bound multi-page Codex calls with durable reservations and per-page validation."""
import argparse
import copy
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from archive_catalog import init_catalog,period_status
from codex_drafts import SCHEMA,INSTRUCTIONS,emit,expand_response,search_history
from generate import atomic_json
from history import connect
from model_stage import page_bundle,SourceTextUnavailable
from outcomes import page_outcome
from research import ROOT,GENERATOR,artifact,import_generation,key,now,packed
from semrush_workflow import init


def init_groups(db):
    init(db);init_catalog(db)
    db.executescript('''CREATE TABLE IF NOT EXISTS research_codex_groups(
      id TEXT PRIMARY KEY,period_id TEXT NOT NULL,directory TEXT NOT NULL,manifest TEXT NOT NULL,
      state TEXT NOT NULL,usage TEXT,created TEXT NOT NULL,updated TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS research_codex_group_members(
      group_id TEXT NOT NULL,request_id TEXT NOT NULL,state TEXT NOT NULL,error TEXT,version_id TEXT,
      PRIMARY KEY(group_id,request_id));''')


def case_evidence(source):
    data={name:source.get(name) for name in ('requestId','sourcePdfId','page','url','pageText','evidenceThrough','researchCoverage')}
    data['catalog']={name:source['context'].get(name) for name in ('brand','models','headings')}
    data['queryColumns']=['query','firstSeen','lastSeen','lastStart','lastEnd','clicks','impressions','position','selectable','notReportedInLatestWindow']
    data['searchHistory']=[]
    for group in search_history(source):
        rows=[]
        for q in group['queries']:
            last=q['lastReported']
            rows.append([q['query'],q['firstSeen'],q['lastSeen'],last['start'],last['end'],last['clicks'],last['impressions'],last['position'],q['selectable'],q['notReportedInLatestWindow']])
        data['searchHistory'].append(dict(engine=group['engine'],url=group['url'],latestWindow=group['latestWindow'],rows=rows))
    data['originalWindowCount']=len(source['searchWindows'])
    data['filters']=dict(nonGlobalAddressQueryObservationsExcluded=sum(w.get('privateAddressQueriesExcluded',0) for w in source['searchWindows']))
    data['previousKeywords']=source.get('semrush',[])
    data['candidates']=[dict(number=i+1,**candidate) for i,candidate in enumerate(source.get('semrushCandidates',[]))]
    return data


def update_outcome(db,period,pdf,page):
    result=page_outcome(db,pdf,page)
    row=db.execute('SELECT detail FROM research_archive_pages WHERE period_id=? AND pdf=? AND page=?',(period,pdf,page)).fetchone()
    detail=json.loads(row['detail']);detail['processing']=result
    db.execute('UPDATE research_archive_pages SET state=?,reason=?,detail=?,updated=? WHERE period_id=? AND pdf=? AND page=?',
        (result['state'],result['reason'] or 'metadata_draft_saved',packed(detail),now(),period,pdf,page))


def prior_single_receipt(request_id):
    base=ROOT/'artifacts/search-metadata/full-history'
    return any(p.resolve().is_relative_to(ROOT/'artifacts') for p in base.glob('codex-drafts*/'+request_id+'/invocation.json'))


def select_sources(db,period,size,max_chars):
    if not 1<=size<=25 or not 10000<=max_chars<=1500000:raise ValueError('Invalid group bounds')
    period_status(db,period)
    rows=db.execute('''SELECT p.pdf,p.page FROM research_archive_pages p JOIN research_pages r
      ON r.pdf=p.pdf AND r.page=p.page WHERE p.period_id=? AND p.eligible=1 AND p.history_imported=1
      AND p.state='pending' AND r.content_id IS NOT NULL ORDER BY p.last_seen DESC,p.priority_clicks DESC,p.pdf,p.page''',(period,)).fetchall()
    sources=[];held={};characters=0
    for row in rows:
        with db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            try:source=page_bundle(db,row['pdf'],row['page'])
            except SourceTextUnavailable:
                update_outcome(db,period,row['pdf'],row['page']);held['source_text_unavailable']=held.get('source_text_unavailable',0)+1;continue
            except ValueError as exc:
                held[str(exc)]=held.get(str(exc),0)+1;continue
            state=db.execute('SELECT status FROM research_requests WHERE id=?',(source['requestId'],)).fetchone()[0]
            if state!='pending':
                if state!='generated':held[state]=held.get(state,0)+1
                continue
            if prior_single_receipt(source['requestId']):
                held['saved_single_response_requires_reconciliation']=held.get('saved_single_response_requires_reconciliation',0)+1;continue
            length=len(packed(case_evidence(source)))
            if sources and characters+length>max_chars:break
            if length>max_chars:
                held['prompt_requires_segmentation']=held.get('prompt_requires_segmentation',0)+1;continue
            sources.append(source);characters+=length
        if len(sources)>=size:break
    return sources,held


def prepare_group(db,period,directory,sources,parent=None,attempt=0,feedback=None):
    if not sources:return None
    if len({s['requestId'] for s in sources})!=len(sources):raise ValueError('Duplicate source request in group')
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'artifacts'):raise ValueError('Group files must remain in workspace artifacts')
    schema=copy.deepcopy(SCHEMA)
    schema['properties'].update(requestId={'type':'string','enum':[s['requestId'] for s in sources]},sourcePdfId={'type':'integer'},page={'type':'integer'})
    schema['required']+=['requestId','sourcePdfId','page']
    response_schema=dict(type='object',properties={'results':dict(type='array',items=schema)},required=['results'],additionalProperties=False)
    instructions=INSTRUCTIONS+'''\nProcess every case independently. Return one results entry per exact requestId/sourcePdfId/page. Never borrow facts, model numbers, keywords or quotes from another case. searchHistory rows use queryColumns; all supplied queries are retained, filtered-observation counts are explicit, and original full windows are saved separately. Source quotes must be CONTIGUOUS spans of at least five characters, preserving interleaved languages and OCR punctuation. Copy numeric spellings exactly; metadata must be plain text without angle brackets or control characters. Title <=160, H1 <=180, description <=320 characters. Keep uncertain identity/applicability marked requiresReview.\n'''
    prompt=instructions+packed(dict(cases=[case_evidence(s) for s in sources],repairFeedback=feedback))
    payload=gzip.compress(packed(sources).encode('utf-8'),mtime=0)
    manifest=dict(schemaVersion=1,periodId=period,model=GENERATOR[0],effort=GENERATOR[1],
        requests=[dict(requestId=s['requestId'],sourcePdfId=s['sourcePdfId'],page=s['page'],bundleSha256=key(s)) for s in sources],
        inputsSha256=hashlib.sha256(payload).hexdigest(),promptSha256=hashlib.sha256(prompt.encode('utf-8')).hexdigest(),schemaSha256=key(response_schema),parentGroup=parent,attempt=attempt)
    ident=key(manifest);folder=directory/ident
    existing=db.execute('SELECT directory FROM research_codex_groups WHERE id=?',(ident,)).fetchone()
    if existing:folder=Path(existing['directory'])
    folder.mkdir(parents=True,exist_ok=True)
    for name,value in [('manifest.json',manifest),('response-schema.json',response_schema)]:
        path=folder/name
        if not path.exists():atomic_json(path,value)
        elif json.loads(path.read_text(encoding='utf-8'))!=value:raise ValueError('Immutable group input changed')
    for name,value in [('inputs.json.gz',payload),('prompt.txt',prompt.encode('utf-8'))]:
        path=folder/name
        if not path.exists():path.write_bytes(value)
        elif path.read_bytes()!=value:raise ValueError('Immutable group input changed')
    with db:
        db.execute('INSERT OR IGNORE INTO research_codex_groups VALUES (?,?,?,?,?,NULL,?,?)',
            (ident,period,str(folder),packed(manifest),'prepared',now(),now()))
    return ident


def load_group(db,ident):
    if not re.fullmatch(r'[0-9a-f]{64}',ident):raise ValueError('Invalid group ID')
    row=db.execute('SELECT * FROM research_codex_groups WHERE id=?',(ident,)).fetchone()
    if not row:raise ValueError('Unknown group')
    folder=Path(row['directory']).resolve()
    if not folder.is_relative_to(ROOT/'artifacts'):raise ValueError('Invalid group directory')
    manifest=json.loads(row['manifest'])
    if key(manifest)!=ident or json.loads((folder/'manifest.json').read_text(encoding='utf-8'))!=manifest:raise ValueError('Group manifest changed')
    for name,expected in [('inputs.json.gz',manifest['inputsSha256']),('prompt.txt',manifest['promptSha256'])]:
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=expected:raise ValueError('Group input changed')
    if key(json.loads((folder/'response-schema.json').read_text(encoding='utf-8')))!=manifest['schemaSha256']:raise ValueError('Group schema changed')
    sources=json.loads(gzip.decompress((folder/'inputs.json.gz').read_bytes()))
    if len(sources)!=len(manifest['requests']):raise ValueError('Group source coverage changed')
    for source,expected in zip(sources,manifest['requests']):
        if key(source)!=expected['bundleSha256'] or source['requestId']!=expected['requestId']:raise ValueError('Frozen group source changed')
    if (manifest['model'],manifest['effort'])!=GENERATOR:raise ValueError('Unexpected group generator')
    return row,folder,manifest,sources


def claim_group(db,ident,manifest,sources):
    with db:
        if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
        state=db.execute('SELECT state FROM research_codex_groups WHERE id=?',(ident,)).fetchone()[0]
        if state!='prepared':raise ValueError('Group was already reserved; do not repeat an uncertain model call')
        for source in sources:
            if page_bundle(db,source['sourcePdfId'],source['page'])['requestId']!=source['requestId']:raise ValueError('Group source or evidence changed before dispatch')
            expected='group_held' if manifest['parentGroup'] else 'pending'
            status=db.execute('SELECT status FROM research_requests WHERE id=?',(source['requestId'],)).fetchone()[0]
            if status!=expected:raise ValueError('A group member is already generated or reserved')
            db.execute("UPDATE research_requests SET status='group_reserved' WHERE id=?",(source['requestId'],))
            db.execute('INSERT INTO research_codex_group_members VALUES (?,?,?,NULL,NULL)',(ident,source['requestId'],'reserved'))
        db.execute("UPDATE research_codex_groups SET state='reserved',updated=? WHERE id=?",(now(),ident))


def hold_group(db,ident,reason):
    with db:
        db.execute("UPDATE research_codex_groups SET state='held',updated=? WHERE id=?",(now(),ident))
        members=db.execute("SELECT request_id FROM research_codex_group_members WHERE group_id=? AND state='reserved'",(ident,)).fetchall()
        for row in members:
            db.execute("UPDATE research_requests SET status='group_held' WHERE id=? AND status='group_reserved'",(row['request_id'],))
            db.execute("UPDATE research_codex_group_members SET state='held',error=? WHERE group_id=? AND request_id=?",(reason,ident,row['request_id']))
            member=db.execute('SELECT pdf,page FROM research_requests WHERE id=?',(row['request_id'],)).fetchone()
            period=db.execute('SELECT period_id FROM research_codex_groups WHERE id=?',(ident,)).fetchone()[0]
            update_outcome(db,period,member['pdf'],member['page'])
    return dict(groupId=ident,state='held',reason=reason,providerRequestsMade=0)


def invoke(folder,command,environment):
    with (folder/'events.jsonl').open('wb') as stdout,(folder/'stderr.log').open('wb') as stderr:
        return subprocess.run(command,input=(folder/'prompt.txt').read_bytes(),stdout=stdout,stderr=stderr,env=environment,timeout=900).returncode


def run_group(db,ident,executable,execute=invoke):
    row,folder,manifest,sources=load_group(db,ident)
    receipt_path=folder/'invocation.json';receipt=json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else None
    if receipt is None:
        if row['state']!='prepared':return hold_group(db,ident,'uncertain_group_call_requires_reconciliation')
        claim_group(db,ident,manifest,sources)
        command=[executable,'exec','--ignore-user-config','--ephemeral','--sandbox','read-only','--cd',str(folder),'--model',GENERATOR[0],
            '-c','model_reasoning_effort="'+GENERATOR[1]+'"','-c','project_doc_max_bytes=0','-c','memories.use_memories=false',
            '--output-schema',str(folder/'response-schema.json'),'--output-last-message',str(folder/'model-output.json'),'--json','--color','never','-']
        receipt=dict(groupId=ident,model=GENERATOR[0],effort=GENERATOR[1],auth='ChatGPT',command=command,
            status='running',startedAt=now(),manifestSha256=ident)
        atomic_json(receipt_path,receipt)
        environment=dict(os.environ);environment.pop('OPENAI_API_KEY',None)
        try:
            code=execute(folder,command,environment)
            receipt.update(exitCode=code,status='completed' if code==0 and (folder/'model-output.json').is_file() else 'model_failed',finishedAt=now())
            if (folder/'model-output.json').exists():receipt['responseSha256']=hashlib.sha256((folder/'model-output.json').read_bytes()).hexdigest()
            if (folder/'events.jsonl').exists():receipt['eventsSha256']=hashlib.sha256((folder/'events.jsonl').read_bytes()).hexdigest()
        except (subprocess.TimeoutExpired,OSError):receipt.update(status='uncertain_call',finishedAt=now())
        atomic_json(receipt_path,receipt)
    if receipt.get('status')!='completed':return hold_group(db,ident,'uncertain_or_failed_group_call')
    if (receipt.get('groupId'),receipt.get('model'),receipt.get('effort'),receipt.get('auth'),receipt.get('manifestSha256'))!=(ident,*GENERATOR,'ChatGPT',ident):raise ValueError('Group receipt provenance mismatch')
    load_group(db,ident)  # Verify immutable inputs again after the model call.
    if hashlib.sha256((folder/'model-output.json').read_bytes()).hexdigest()!=receipt['responseSha256']:raise ValueError('Group output changed after receipt')
    if hashlib.sha256((folder/'events.jsonl').read_bytes()).hexdigest()!=receipt.get('eventsSha256'):raise ValueError('Group events changed after receipt')
    try:events=[json.loads(line) for line in (folder/'events.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    except (ValueError,UnicodeError):return hold_group(db,ident,'invalid_group_events')
    completed=[e for e in events if isinstance(e,dict) and e.get('type')=='turn.completed']
    if len(completed)!=1 or not isinstance(completed[0].get('usage'),dict):return hold_group(db,ident,'group_turn_not_complete')
    # Count the real call once, including a completed but invalid response.
    with db:
        proof={name:artifact(db,folder/file,'codex_group_'+name) for name,file in [('receipt','invocation.json'),('output','model-output.json'),('events','events.jsonl'),('prompt','prompt.txt'),('inputs','inputs.json.gz'),('manifest','manifest.json')]}
        changed=db.execute('UPDATE research_codex_groups SET usage=?,state=?,updated=? WHERE id=? AND usage IS NULL',
            (packed(completed[0]['usage']),'completed',now(),ident)).rowcount
        if changed:db.execute('INSERT INTO research_events(created,pdf,page,event,payload) VALUES (?,?,?,?,?)',
            (now(),None,None,'codex_group_completed',packed(dict(groupId=ident,model=GENERATOR[0],effort=GENERATOR[1],usage=completed[0]['usage'],pages=len(sources),proof=proof))))
    if any(not isinstance(e,dict) or e.get('item',{}).get('type') not in (None,'agent_message','reasoning') for e in events):return hold_group(db,ident,'unexpected_model_tool_use')
    try:
        raw=json.loads((folder/'model-output.json').read_text(encoding='utf-8-sig'))['results']
        if not isinstance(raw,list) or any(not isinstance(item,dict) or not isinstance(item.get('requestId'),str) for item in raw):raise ValueError('Invalid result rows')
    except (ValueError,KeyError,TypeError,UnicodeError):return hold_group(db,ident,'invalid_group_response')
    ids=[r['requestId'] for r in raw];expected={s['requestId']:s for s in sources}
    if len(ids)!=len(set(ids)) or set(ids)!=set(expected):return hold_group(db,ident,'group_response_identity_coverage_mismatch')
    results=[]
    for item in raw:
        source=expected[item['requestId']];request_id=source['requestId']
        member=db.execute('SELECT * FROM research_codex_group_members WHERE group_id=? AND request_id=?',(ident,request_id)).fetchone()
        if member['version_id']:
            results.append(dict(requestId=request_id,status=member['state'],version=member['version_id'],reused=True));continue
        try:
            if type(item.get('sourcePdfId'))!=int or type(item.get('page'))!=int or (item['sourcePdfId'],item['page'])!=(source['sourcePdfId'],source['page']):raise ValueError('Group page identity mismatch')
            response=expand_response(source,{k:v for k,v in item.items() if k not in ('requestId','sourcePdfId','page')})
            response['generationGroupId']=ident
            member_dir=folder/'members'/request_id;member_dir.mkdir(parents=True,exist_ok=True)
            path=member_dir/'response.json';atomic_json(path,response)
            with db:
                if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
                if page_bundle(db,source['sourcePdfId'],source['page'])['requestId']!=request_id:raise ValueError('Group source or evidence changed before import')
                current=db.execute('SELECT status FROM research_requests WHERE id=?',(request_id,)).fetchone()[0]
                if current not in ('group_reserved','group_held'):raise ValueError('Member request was generated outside this group')
                result=import_generation(db,path)
                db.execute('UPDATE research_codex_group_members SET state=?,error=NULL,version_id=? WHERE group_id=? AND request_id=?',(result['status'],result['version'],ident,request_id))
                db.execute('INSERT INTO research_events(created,pdf,page,event,payload) VALUES (?,?,?,?,?)',
                    (now(),source['sourcePdfId'],source['page'],'codex_group_page_imported',packed(dict(groupId=ident,requestId=request_id,versionId=result['version']))))
                update_outcome(db,manifest['periodId'],source['sourcePdfId'],source['page'])
            results.append(dict(requestId=request_id,sourcePdfId=source['sourcePdfId'],page=source['page'],**result,title=response['pageTitle']))
        except (ValueError,KeyError,TypeError) as exc:
            db.rollback();reason=str(exc) if isinstance(exc,ValueError) else 'Invalid group member response'
            with db:
                db.execute("UPDATE research_requests SET status='group_held' WHERE id=? AND status='group_reserved'",(request_id,))
                db.execute("UPDATE research_codex_group_members SET state='held',error=? WHERE group_id=? AND request_id=?",(reason,ident,request_id))
                update_outcome(db,manifest['periodId'],source['sourcePdfId'],source['page'])
            results.append(dict(requestId=request_id,status='held',reason=reason))
    result=dict(groupId=ident,state='processed',pages=results,usage=completed[0]['usage'],usageScope='one actual group call; never per page',providerRequestsMade=0,productionChanged=False)
    atomic_json(folder/'results.json',result)
    with db:db.execute("UPDATE research_codex_groups SET state='processed',updated=? WHERE id=?",(now(),ident))
    return result


def repair_sources(db,parent):
    row,folder,manifest,sources=load_group(db,parent)
    receipt=json.loads((folder/'invocation.json').read_text(encoding='utf-8'))
    if receipt.get('status')!='completed' or row['usage'] is None:raise ValueError('Uncertain groups cannot be automatically repaired')
    if hashlib.sha256((folder/'model-output.json').read_bytes()).hexdigest()!=receipt['responseSha256']:raise ValueError('Parent group output changed')
    if manifest['attempt']>=3:raise ValueError('Group repair limit reached')
    if hashlib.sha256((folder/'events.jsonl').read_bytes()).hexdigest()!=receipt.get('eventsSha256'):raise ValueError('Parent group events changed')
    held={r['request_id']:r['error'] for r in db.execute("SELECT request_id,error FROM research_codex_group_members WHERE group_id=? AND state='held'",(parent,))}
    selected=[s for s in sources if s['requestId'] in held]
    if not selected:raise ValueError('No held members remain in this group')
    return manifest['periodId'],selected,manifest['attempt']+1,dict(errors=held,previousResponse=json.loads((folder/'model-output.json').read_text(encoding='utf-8-sig')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'artifacts/search-metadata/research.sqlite3')
    parser.add_argument('--period');parser.add_argument('--directory',type=Path,default=ROOT/'artifacts/search-metadata/full-history/codex-groups')
    parser.add_argument('--pages-per-call',type=int,default=8);parser.add_argument('--limit',type=int,default=8)
    parser.add_argument('--max-prompt-chars',type=int,default=200000);parser.add_argument('--run',action='store_true')
    parser.add_argument('--resume-group');parser.add_argument('--repair-group')
    args=parser.parse_args()
    if not 1<=args.limit<=1000:raise ValueError('Group batch limit must be 1..1000')
    if sum(bool(v) for v in (args.period,args.resume_group,args.repair_group))!=1:raise ValueError('Select one period, resume group or repair group')
    from research_hub.worker import worker_lock
    lock=ROOT/'artifacts/search-metadata/codex-generation';lock.mkdir(parents=True,exist_ok=True)
    with worker_lock(lock) as acquired:
        if not acquired:raise ValueError('Another ManualsDump Codex batch is active')
        with connect(args.db) as db:
            init_groups(db);done=0;executable=None
            if args.run:
                executable=shutil.which('codex')
                if not executable:raise ValueError('Codex CLI is required')
                env=dict(os.environ);env.pop('OPENAI_API_KEY',None)
                auth=subprocess.run([executable,'login','status'],capture_output=True,env=env,timeout=30)
                if auth.returncode or b'ChatGPT' not in auth.stdout+auth.stderr:raise ValueError('Codex must use ChatGPT sign-in')
            while done<args.limit:
                if args.resume_group:ident=args.resume_group
                elif args.repair_group:
                    period,sources,attempt,feedback=repair_sources(db,args.repair_group)
                    ident=prepare_group(db,period,args.directory,sources,args.repair_group,attempt,feedback)
                else:
                    sources,held=select_sources(db,args.period,min(args.pages_per_call,args.limit-done),args.max_prompt_chars)
                    if not sources:emit(dict(prepared=0,held=held));break
                    ident=prepare_group(db,args.period,args.directory,sources)
                emit(dict(preparedGroup=ident))
                if not args.run:break
                result=run_group(db,ident,executable);emit(result)
                if result['state']!='processed':break
                done+=len(result['pages'])
                if args.resume_group or args.repair_group:break


if __name__=='__main__':main()
