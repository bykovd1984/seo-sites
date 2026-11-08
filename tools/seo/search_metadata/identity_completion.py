"""Explicit, source-bound skip reasons for existing catalogue identity quarantines.

No identity flag is cleared and no metadata is generated or activated here.
"""
import base64
import hashlib
import json
import re
import unicodedata
import zlib
from pathlib import Path

from generate import PageText, plain, safe
from ranking_policy import eligibility
from research import artifact, key, now, packed
from source_completion import archived, read_export


def normalized(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).casefold().strip()


def current_quarantines(db,pdf,page):
    rows=db.execute('''SELECT w.* FROM research_windows w WHERE pdf=? AND page=?
      AND w.rowid=(SELECT MAX(v.rowid) FROM research_windows v WHERE v.pdf=w.pdf AND v.page=w.page
      AND v.engine=w.engine AND v.start=w.start AND v.end=w.end) ORDER BY w.id''',(pdf,page))
    result=[]
    for row in rows:
        payload=json.loads(row['payload']);inspection=payload.get('contentInspection') or {}
        if not isinstance(inspection,dict):continue
        if not payload.get('identityReviewRequired') or payload.get('identityReviewReason')=='api_source_mapping_pending':continue
        if payload.get('verifiedSourcePdfId')!=pdf or not inspection.get('evidence') or not isinstance(inspection.get('source'),str) or normalized(inspection['source']) in ('','unavailable','unknown'):continue
        manifest_id=payload.get('manifestArtifact')
        manifest=json.loads(archived(db,manifest_id).decode('utf-8-sig'))
        if not isinstance(manifest,dict) or (manifest.get('sourcePdfId'),manifest.get('page'),manifest.get('identityReviewRequired'))!=(pdf,page,True):
            raise ValueError('Identity quarantine manifest changed')
        archived(db,row['raw_artifact'])
        result.append(dict(windowId=row['id'],manifestArtifact=manifest_id,rawArtifact=row['raw_artifact']))
    if not result:raise ValueError('An explicit verified-source identity quarantine is required; availability-only flags stay pending')
    return result


def context_evidence(db,pdf,binding,target_page):
    from draft_reviews import manual_context
    page=binding.get('page')
    if type(page)!=int or not 0<page<=65535:raise ValueError('Invalid identity source page')
    row=manual_context(db,pdf,page)
    if not row or (row['raw_sha256'],row['source_artifact'])!=(binding.get('contentSha256'),binding.get('sourceArtifact')):
        raise ValueError('Identity source binding changed')
    context=json.loads(zlib.decompress(row['context_zlib']))
    if context.get('readOnly') is not True or (context.get('sourcePdfId'),context.get('page'))!=(pdf,page):
        raise ValueError('Identity evidence lacks its exact read-only source binding')
    if type(context.get('pageCount'))!=int or not max(target_page,page)<=context['pageCount']<=65535:
        raise ValueError('Identity source page count is invalid')
    if context.get('type')=='seo_context':
        if type(context.get('manualId'))!=int or context['manualId']<=0:raise ValueError('Converted source mapping is missing')
    elif context.get('type')!='legacy_seo_example' or context.get('format') not in ('bcl_html','legacy_page'):
        raise ValueError('Unknown identity source format')
    saved=[json.loads(line) for line in archived(db,row['source_artifact']).decode('utf-8-sig').splitlines() if line.strip()]
    if context not in saved:raise ValueError('Archived source does not contain the bound context')
    encoding='utf-8' if context['type']=='legacy_seo_example' else 'utf-8-sig'
    raw=base64.b64decode(context['rawHtmlBase64'],validate=True).decode(encoding)
    if hashlib.sha256(raw.encode('utf-8')).hexdigest()!=row['raw_sha256']:raise ValueError('Identity source HTML changed')
    parser=PageText();parser.feed(raw);text=plain(' '.join(parser.text));quote=binding.get('quote','')
    if not safe(quote,1000) or len(normalized(quote))<5 or normalized(quote) not in normalized(text):
        raise ValueError('Identity quote is not in its exact source page')
    return context,dict(page=page,contentSha256=row['raw_sha256'],sourceArtifact=row['source_artifact'],quote=quote)


def validate_decision(db,decision):
    if type(decision.get('schemaVersion'))!=int or decision.get('schemaVersion')!=1 or decision.get('kind')!='catalog_source_identity_conflict':raise ValueError('Unknown identity decision')
    pdf,page=decision.get('sourcePdfId'),decision.get('page')
    if type(pdf)!=int or pdf<=0 or type(page)!=int or not 0<page<=65535:raise ValueError('Invalid identity decision page')
    for field in ('catalogBrand','sourceBrand','sourceModel'):
        if not safe(decision.get(field,''),100):raise ValueError('A bounded explicit identity label is required')
    if not safe(decision.get('rationale',''),2000) or len(decision['rationale'])<20:raise ValueError('A specific source-conflict rationale is required')
    catalog,brand,model=(normalized(decision[field]) for field in ('catalogBrand','sourceBrand','sourceModel'))
    if catalog==brand or catalog in ('_','unknown','none'):raise ValueError('The two explicit identity labels must differ')
    target,cover=decision.get('target',{}),decision.get('cover',{})
    if not isinstance(target,dict) or not isinstance(cover,dict) or target.get('page')!=page or cover.get('page') not in (1,2) or cover.get('page')==page:
        raise ValueError('Bind the exact target and a separate introductory page from the same manual')
    quarantines=current_quarantines(db,pdf,page)
    context,target_proof=context_evidence(db,pdf,target,page)
    _,cover_proof=context_evidence(db,pdf,cover,page)
    current=db.execute('SELECT content_id FROM research_pages WHERE pdf=? AND page=?',(pdf,page)).fetchone()
    active=db.execute('SELECT raw_sha256,source_artifact FROM research_content WHERE id=?',(current['content_id'],)).fetchone() if current else None
    if not active or (active['raw_sha256'],active['source_artifact'])!=(target_proof['contentSha256'],target_proof['sourceArtifact']):
        raise ValueError('Target is not the current preferred source context')
    models=context.get('models')
    if not isinstance(context.get('brand'),str) or not isinstance(models,list) or not all(isinstance(value,str) for value in models) or normalized(context['brand'])!=catalog or model not in [normalized(value) for value in models]:
        raise ValueError('The catalogue identity does not match the current guarded context')
    boundary=lambda label,text:bool(re.search(r'(?<!\w)'+re.escape(label)+r'(?!\w)',normalized(text)))
    if not boundary(brand,target_proof['quote']) or boundary(catalog,target_proof['quote']):
        raise ValueError('The target identity quote must support the conflicting label, not the catalogue brand')
    if not boundary(model,target_proof['quote']) or not boundary(model,cover_proof['quote']):
        raise ValueError('The target and cover must explicitly share the same catalogue model')
    return dict(quarantineWindows=quarantines,target=target_proof,cover=cover_proof)


def identity_outcome(db,pdf,page):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_identity_skips'").fetchone():return None
    row=db.execute('SELECT * FROM research_identity_skips WHERE pdf=? AND page=?',(pdf,page)).fetchone()
    if not row:return None
    try:
        proof=json.loads(row['payload']);decision=proof['decision']
        if key(proof)!=row['proof_id'] or (decision['sourcePdfId'],decision['page'])!=(pdf,page):raise ValueError('Identity proof changed')
        if json.loads(archived(db,proof['decisionArtifact']).decode('utf-8-sig'))!=decision:raise ValueError('Identity decision artifact changed')
        if validate_decision(db,decision)!=proof['sourceEvidence']:raise ValueError('Identity source evidence changed')
    except (ValueError,OSError,KeyError,TypeError):
        return dict(state='pending',reason='identity_conflict_proof_changed')
    return dict(state='skipped',reason='catalog_source_identity_conflict',identityEvidence=dict(proof,proofId=row['proof_id']),
        followUp='Correct or adjudicate the catalogue/source identity and import a fresh identity-resolution manifest, then reconcile. The original quarantine remains in force.')


def record_identity_skip(db,path,period=None):
    if db.in_transaction:raise ValueError('Commit earlier imports before recording an identity decision')
    path,data=read_export(path)
    if len(data)>1024**2:raise ValueError('Identity decision exceeds one MiB')
    decision=json.loads(data.decode('utf-8-sig'))
    if not isinstance(decision,dict):raise ValueError('Identity decision must be an object')
    if period:
        from archive_catalog import period_status
        period_status(db,period)
    db.execute('''CREATE TABLE IF NOT EXISTS research_identity_skips(
        pdf INTEGER,page INTEGER,proof_id TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL,
        PRIMARY KEY(pdf,page))''')
    with db:
        db.execute('BEGIN IMMEDIATE')
        evidence=validate_decision(db,decision);pdf,page=decision['sourcePdfId'],decision['page']
        if not eligibility(db,pdf,page)['eligible']:raise ValueError('Ranking protection prevents this source decision')
        proof=dict(schemaVersion=1,kind='explicit_source_identity_review',decision=decision,sourceEvidence=evidence,
            decisionArtifact=artifact(db,path,'source_identity_conflict_decision'),
            recordedBy='explicit_source_review',metadataGenerated=False,quarantineCleared=False)
        ident=key(proof);old=db.execute('SELECT proof_id FROM research_identity_skips WHERE pdf=? AND page=?',(pdf,page)).fetchone()
        changed=not old or old['proof_id']!=ident
        if changed:
            db.execute('INSERT OR REPLACE INTO research_identity_skips VALUES (?,?,?,?,?)',(pdf,page,ident,packed(proof),now()))
            db.execute('INSERT INTO research_events(created,pdf,page,event,payload) VALUES (?,?,?,?,?)',(now(),pdf,page,'source_identity_conflict_recorded',packed(proof)))
        if period:
            from codex_groups import update_outcome
            if not db.execute('SELECT 1 FROM research_archive_pages WHERE period_id=? AND pdf=? AND page=?',(period,pdf,page)).fetchone():raise ValueError('Decision page is outside this period')
            update_outcome(db,period,pdf,page)
    return dict(recorded=int(changed),alreadyRecorded=int(not changed),sourcePdfId=pdf,page=page,proofId=ident,
        modelCallsMade=0,providerRequestsMade=0,productionChanged=False,quarantineCleared=False)
