"""Evidence-bound outcomes after converted and legacy source exports complete."""
import hashlib
import json
import re
from pathlib import Path

from research import ROOT,artifact,key,now,packed

TERMINAL_REASONS={'file_missing','not_in_test_catalog','missing_storage_or_page_out_of_range'}


def init_failures(db):
    db.execute('''CREATE TABLE IF NOT EXISTS research_source_export_failures(
      pdf INTEGER,page INTEGER,proof_id TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL,
      PRIMARY KEY(pdf,page))''')


def read_export(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT/'artifacts') or not path.is_file() or path.stat().st_size>100*1024**2:
        raise ValueError('Source proof must be a bounded workspace artifact')
    return path,path.read_bytes()


def records(data,converted):
    rows={}
    for line in data.decode('utf-8-sig').splitlines():
        if not line.strip():continue
        value=json.loads(line)
        if not isinstance(value,dict):raise ValueError('Paired source record must be an object')
        pdf,page=value.get('sourcePdfId'),value.get('page')
        if type(pdf)!=int or not 0<pdf<2**63 or type(page)!=int or not 0<page<=65535:
            raise ValueError('Invalid paired source identity')
        identity=(pdf,page)
        if identity in rows or len(rows)>=100:raise ValueError('Duplicate or excessive paired source rows')
        allowed=('seo_context',) if converted else ('legacy_seo_example','legacy_source_unavailable')
        if value.get('type') not in allowed:raise ValueError('Unexpected paired source record')
        if value['type']=='legacy_source_unavailable':
            if not isinstance(value.get('reason'),str):raise ValueError('Missing source failure reason')
        elif value.get('readOnly') is not True:
            raise ValueError('Source context lacks its read-only guard')
        rows[identity]=value
    return rows


def archived(db,ident):
    if not isinstance(ident,str) or not re.fullmatch('[0-9a-f]{64}',ident):raise ValueError('Invalid source artifact identity')
    row=db.execute('SELECT path FROM research_artifacts WHERE id=?',(ident,)).fetchone()
    if not row:raise ValueError('Source artifact is missing')
    path,data=read_export(row['path'])
    if hashlib.sha256(data).hexdigest()!=ident:raise ValueError('Source artifact changed')
    return data


def unavailable_outcome(db,pdf,page):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_source_export_failures'").fetchone():return None
    row=db.execute('SELECT * FROM research_source_export_failures WHERE pdf=? AND page=?',(pdf,page)).fetchone()
    if not row:return None
    if db.execute('SELECT 1 FROM research_content WHERE pdf=? AND page=? LIMIT 1',(pdf,page)).fetchone():return None
    try:
        proof=json.loads(row['payload'])
        if proof.get('schemaVersion')!=1 or proof.get('kind')!='paired_source_export_unavailable' or key(proof)!=row['proof_id'] or (proof['sourcePdfId'],proof['page'])!=(pdf,page) or proof['failureReason'] not in TERMINAL_REASONS:
            raise ValueError('Invalid paired source proof')
        attempt=db.execute('SELECT reason,source_artifact FROM research_context_attempts WHERE pdf=? AND page=?',(pdf,page)).fetchone()
        if not attempt or (attempt['reason'],attempt['source_artifact'])!=(proof['failureReason'],proof['legacyArtifact']):
            return dict(state='pending',reason='source_export_attempt_changed')
        converted=records(archived(db,proof['convertedArtifact']),True)
        legacy=records(archived(db,proof['legacyArtifact']),False)
        item=legacy.get((pdf,page))
        if (pdf,page) in converted or not item or item['type']!='legacy_source_unavailable' or item['reason']!=proof['failureReason']:
            raise ValueError('Source proof no longer supports this failure')
    except (ValueError,OSError,KeyError,TypeError):
        return dict(state='pending',reason='source_export_proof_invalid')
    return dict(state='skipped',reason='source_context_unavailable',sourceEvidence=dict(proof,proofId=row['proof_id']),
        followUp='No verified context was exported from the approved converted/legacy copies. Refresh the source catalog/files or obtain OCR, then import the exact page and reconcile again.')


def finalize_export(db,converted_path,legacy_path,period=None):
    if db.in_transaction:raise ValueError('Commit context imports before finalizing the paired export')
    converted_path,converted_data=read_export(converted_path)
    legacy_path,legacy_data=read_export(legacy_path)
    suffix=re.fullmatch(r'converted-(\d{3})\.jsonl',converted_path.name)
    if not suffix or converted_path.parent!=legacy_path.parent or legacy_path.name!='legacy-'+suffix[1]+'.jsonl':
        raise ValueError('Converted and legacy proofs must be matching files from one export run')
    converted,legacy=records(converted_data,True),records(legacy_data,False)
    if converted.keys() & legacy.keys():raise ValueError('A converted context cannot also be a legacy failure')
    if len(converted)+len(legacy)>100:raise ValueError('Paired export exceeds the bounded request count')
    if period:
        from archive_catalog import period_status
        period_status(db,period)
    init_failures(db)
    result=dict(recordedPages=0,alreadyRecorded=0,sourcePresent=0,pendingReasons={},updatedOutcomes=0,providerRequestsMade=0,modelCallsMade=0)
    with db:
        db.execute('BEGIN IMMEDIATE')
        converted_id=artifact(db,converted_path,'converted_source_completion')
        legacy_id=artifact(db,legacy_path,'legacy_source_completion')
        for (pdf,page),item in legacy.items():
            if item['type']!='legacy_source_unavailable':continue
            reason=item['reason']
            if reason not in TERMINAL_REASONS:
                result['pendingReasons'][reason]=result['pendingReasons'].get(reason,0)+1;continue
            if db.execute('SELECT 1 FROM research_content WHERE pdf=? AND page=? LIMIT 1',(pdf,page)).fetchone():
                result['sourcePresent']+=1;continue
            attempt=db.execute('SELECT reason,source_artifact FROM research_context_attempts WHERE pdf=? AND page=?',(pdf,page)).fetchone()
            if not attempt or (attempt['reason'],attempt['source_artifact'])!=(reason,legacy_id):
                result['pendingReasons']['source_export_attempt_changed']=result['pendingReasons'].get('source_export_attempt_changed',0)+1;continue
            proof=dict(schemaVersion=1,kind='paired_source_export_unavailable',sourcePdfId=pdf,page=page,
                convertedArtifact=converted_id,legacyArtifact=legacy_id,failureReason=reason,
                limitation='The converted export supplied no verified context; the legacy export reported this failure. This does not prove the original PDF is absent.')
            ident=key(proof)
            old=db.execute('SELECT proof_id FROM research_source_export_failures WHERE pdf=? AND page=?',(pdf,page)).fetchone()
            if old and old['proof_id']==ident:result['alreadyRecorded']+=1
            else:
                db.execute('INSERT OR REPLACE INTO research_source_export_failures VALUES (?,?,?,?,?)',(pdf,page,ident,packed(proof),now()))
                db.execute('INSERT INTO research_events(created,pdf,page,event,payload) VALUES (?,?,?,?,?)',(now(),pdf,page,'paired_source_unavailable',packed(proof)))
                result['recordedPages']+=1
            if period:
                archive=db.execute('SELECT detail FROM research_archive_pages WHERE period_id=? AND pdf=? AND page=?',(period,pdf,page)).fetchone()
                if archive:
                    from outcomes import page_outcome
                    outcome=page_outcome(db,pdf,page);detail=json.loads(archive['detail']);detail['processing']=outcome
                    db.execute('UPDATE research_archive_pages SET state=?,reason=?,detail=?,updated=? WHERE period_id=? AND pdf=? AND page=?',
                        (outcome['state'],outcome['reason'] or 'metadata_draft_saved',packed(detail),now(),period,pdf,page))
                    result['updatedOutcomes']+=1
    return result
