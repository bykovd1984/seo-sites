"""Review imported keywords and generate metadata in one Codex Sol step."""
import argparse
import json
import re
import unicodedata
from pathlib import Path

from generate import atomic_json
from history import connect
from ranking_policy import eligibility
from research import (ROOT, GENERATOR, bundle, import_generation, key, packed,
                      refresh_stage, now)
from semrush_workflow import init


class SourceTextUnavailable(ValueError):
    def __init__(self,proof):
        super().__init__('No extractable page text for source-grounded metadata')
        self.reason='source_text_unavailable'
        self.proof=proof


def draft_policy(db):
    row=db.execute("SELECT value FROM research_settings WHERE name='allow_missing_semrush'").fetchone()
    return bool(row and json.loads(row['value']) is True)


def set_draft_policy(db,allow_missing_semrush):
    if not isinstance(allow_missing_semrush,bool): raise ValueError('Draft policy must be boolean')
    db.execute('INSERT OR REPLACE INTO research_settings VALUES (?,?,?)',
               ('allow_missing_semrush',packed(allow_missing_semrush),now()))
    db.execute('INSERT INTO research_events(created,pdf,page,event,payload) VALUES (?,?,?,?,?)',
               (now(),None,None,'draft_policy_changed',packed(dict(allowMissingSemrush=allow_missing_semrush))))
    return dict(allowMissingSemrush=allow_missing_semrush,scope='Draft generation only; incomplete Semrush evidence cannot activate metadata')


def page_bundle(db,pdf,page,allow_missing_semrush=None):
    if allow_missing_semrush is None: allow_missing_semrush=draft_policy(db)
    if not isinstance(allow_missing_semrush,bool): raise ValueError('Draft policy must be boolean')
    refresh_stage(db,pdf,page)
    record=db.execute('''SELECT p.stage,c.raw_sha256,c.source_artifact FROM research_pages p
        LEFT JOIN research_content c ON c.id=p.content_id WHERE p.pdf=? AND p.page=?''',(pdf,page)).fetchone()
    if not record or not record['raw_sha256']: raise ValueError('Exact page context is required')
    if record['stage']=='identity_review': raise ValueError('Source identity requires review')
    rank=eligibility(db,pdf,page)
    if not rank['eligible']: raise ValueError('Ranking protection: '+rank['reason'])
    jobs=db.execute('''SELECT DISTINCT j.* FROM semrush_jobs j JOIN semrush_links l ON l.job_id=j.id
        WHERE l.pdf=? AND l.page=? AND l.content_sha256=? AND j.status!='superseded' ORDER BY j.id''',(pdf,page,record['raw_sha256'])).fetchall()
    incomplete=[j for j in jobs if j['status']!='done']
    missing=not jobs and record['stage']!='ready_for_generation'
    if incomplete and not allow_missing_semrush: raise ValueError('Semrush collection is not complete for this page context')
    if missing and not allow_missing_semrush: raise ValueError('Semrush evidence has not been imported')
    coverage=None
    if incomplete or missing:
        coverage=dict(semrush=dict(requiredForDraft=False,status='partial' if incomplete else 'not_imported',
            completedJobs=sum(j['status']=='done' for j in jobs),
            pendingJobs=[dict(jobId=j['id'],status=j['status']) for j in incomplete],
            limitation='Missing Semrush reports and metrics are unknown; enrichment is deferred.'))
    candidates=[]
    for job in jobs:
        if job['status']!='done': continue
        if not job['artifact_id'] or not job['result']: raise ValueError('Semrush request has no saved result proof')
        request=json.loads(job['request'])
        seed_sources=[dict(kind=r['kind'],seed=r['seed'],provenance=json.loads(r['payload'])) for r in db.execute('''
            SELECT * FROM semrush_seed_sources WHERE job_id=? AND pdf=? AND page=? AND content_sha256=? ORDER BY seed''',
            (job['id'],pdf,page,record['raw_sha256']))]
        for observation in json.loads(job['result']):
            candidates.append(dict(candidateId=key((job['id'],observation['keyword'])),jobId=job['id'],
                                   request=request,metrics=observation,observedAt=job['updated'],
                                   sourceArtifact=job['artifact_id'],seedSources=seed_sources))
    result=bundle(db,pdf,page,imported_candidates=candidates,draft_coverage=coverage)
    text=re.sub(r'\s+',' ',unicodedata.normalize('NFKC',result['pageText'])).casefold().strip()
    if len(text)<5:
        raise SourceTextUnavailable(dict(sourcePdfId=pdf,page=page,contentSha256=record['raw_sha256'],
            sourceArtifact=record['source_artifact'],extractedCharacters=len(text),minimumQuoteCharacters=5))
    return result


def validate_keyword_decisions(source,response):
    """Validate the complete model response before storing any decisions or draft."""
    expected={item['candidateId']:item for item in source.get('semrushCandidates',[])}
    rows=response.get('keywordDecisions')
    if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):
        raise ValueError('Expected keywordDecisions for every imported candidate')
    ids=[r.get('candidateId') for r in rows]
    if any(not isinstance(ident,str) for ident in ids): raise ValueError('Invalid keyword candidate ID')
    if len(ids)!=len(set(ids)) or set(ids)!=set(expected):
        raise ValueError('Keyword decisions must match the exact frozen candidates')
    normalize=lambda s:re.sub(r'\s+',' ',unicodedata.normalize('NFKC',s)).casefold().strip()
    text=normalize(source['pageText']);rejected=set();retained=set()
    for row in rows:
        item=expected[row['candidateId']];decision=row.get('decision');metrics=item['metrics']
        if decision not in ('keep','reject','no_results') or not isinstance(row.get('reason'),str) or not row['reason'].strip():
            raise ValueError('Keyword decision requires a supported action and reason')
        if decision=='no_results' and metrics['status']!='nothing found':
            raise ValueError('No-results decision is not supported by provider evidence')
        if decision=='keep':
            if metrics['status']=='nothing found': raise ValueError('A no-results report cannot be kept as a measured candidate')
            quotes=row.get('contentEvidence')
            if not isinstance(quotes,list) or not quotes or any(not isinstance(q,str) or len(normalize(q))<5 or normalize(q) not in text for q in quotes):
                raise ValueError('Retained candidate needs verbatim source content evidence')
            retained.add(normalize(metrics['keyword']))
        elif decision=='reject': rejected.add(normalize(metrics['keyword']))
    selected=response.get('selectedKeywords')
    if not isinstance(selected,list) or any(not isinstance(s,str) or not s.strip() for s in selected):
        raise ValueError('Expected selectedKeywords list')
    # A no-results report can still be a real observed query; missing demand is not zero.
    observed={normalize(q['query']) for w in source['searchWindows'] if w['selectedForGeneration'] for q in w['queries']}
    observed.update(normalize(q['query']) for report in source.get('historicalQueryEvidence',[])
                    for q in report['notReportedInLatest'])
    prior={normalize(k['keyword']) for k in source.get('semrush',[])}
    allowed=observed|prior|retained
    for keyword in selected:
        if normalize(keyword) in rejected or normalize(keyword) not in allowed:
            raise ValueError('Selected keyword is rejected or absent from the imported evidence')


def queue(db,directory,limit=25):
    if not 1<=limit<=1000: raise ValueError('Model queue limit must be 1..1000')
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'artifacts'): raise ValueError('Model bundles must be workspace artifacts')
    result=[];held={}
    for row in db.execute('''SELECT p.pdf,p.page,MAX(w.end) recent,MAX(w.page_clicks) clicks
        FROM research_pages p JOIN research_windows w ON w.pdf=p.pdf AND w.page=p.page
        GROUP BY p.pdf,p.page ORDER BY recent DESC,clicks DESC,p.pdf,p.page''').fetchall():
        try: value=page_bundle(db,row['pdf'],row['page'])
        except ValueError as exc:
            reason=str(exc);held[reason]=held.get(reason,0)+1;continue
        state=db.execute('SELECT status FROM research_requests WHERE id=?',(value['requestId'],)).fetchone()[0]
        if state!='pending':
            if state!='generated':held[state]=held.get(state,0)+1
            continue
        path=directory/f'{row["pdf"]}-{row["page"]}-{value["requestId"][:12]}.json'
        if not path.exists(): atomic_json(path,value)
        result.append(dict(sourcePdfId=row['pdf'],page=row['page'],requestId=value['requestId'],bundle=str(path),
                           importedCandidates=len(value['semrushCandidates'])))
        if len(result)>=limit: break
    return dict(model=GENERATOR[0],effort=GENERATOR[1],queued=result,held=held)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'artifacts/search-metadata/research.sqlite3')
    commands=parser.add_subparsers(dest='command',required=True)
    queued=commands.add_parser('queue');queued.add_argument('--limit',type=int,default=25)
    queued.add_argument('--directory',type=Path,default=ROOT/'artifacts/search-metadata/model-bundles')
    policy=commands.add_parser('draft-policy',help='Persist the owner-approved draft evidence policy')
    flags=policy.add_mutually_exclusive_group(required=True)
    flags.add_argument('--allow-missing-semrush',action='store_true')
    flags.add_argument('--require-semrush',action='store_true')
    generated=commands.add_parser('generation');generated.add_argument('file',type=Path)
    args=parser.parse_args()
    with connect(args.db) as db:
        init(db)
        if args.command=='draft-policy': value=set_draft_policy(db,args.allow_missing_semrush)
        else: value=queue(db,args.directory,args.limit) if args.command=='queue' else import_generation(db,args.file)
        print(packed(value))


if __name__=='__main__':
    try: main()
    except ValueError as exc: raise SystemExit(str(exc))
