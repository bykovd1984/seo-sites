"""Index a complete frozen provider archive without one file per daily row."""
import datetime as dt
import hashlib
import itertools
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

from generate import atomic_json
from ranking_policy import MINIMUM_POSITION
from research import ROOT, artifact, key, now, packed, refresh_stage


def init_catalog(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS research_archive_periods(
        id TEXT PRIMARY KEY,snapshot_path TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
        start TEXT NOT NULL,end TEXT NOT NULL,site TEXT NOT NULL,manifest_artifact TEXT NOT NULL,
        created TEXT NOT NULL,status TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS research_archive_pages(
        period_id TEXT NOT NULL,pdf INTEGER NOT NULL,page INTEGER NOT NULL,url TEXT NOT NULL,
        last_seen TEXT NOT NULL,priority_clicks INTEGER NOT NULL,eligible INTEGER NOT NULL,
        state TEXT NOT NULL,reason TEXT NOT NULL,history_imported INTEGER NOT NULL DEFAULT 0,
        detail TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(period_id,pdf,page));
      CREATE INDEX IF NOT EXISTS research_archive_queue ON research_archive_pages(
        period_id,eligible,history_imported,last_seen DESC,priority_clicks DESC,pdf,page);
    ''')


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def snapshot_history(source_path, directory):
    source_path, directory = Path(source_path).resolve(), Path(directory).resolve()
    if not source_path.is_file():
        raise ValueError('Provider history database does not exist')
    if not directory.is_relative_to(ROOT/'artifacts'):
        raise ValueError('Archive snapshots must remain in workspace artifacts')
    directory.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, suffix='.sqlite3')
    os.close(handle)
    temporary = Path(temporary)
    source = sqlite3.connect(source_path.as_uri()+'?mode=ro', uri=True)
    target = sqlite3.connect(temporary)
    try:
        source.backup(target)
        # A frozen snapshot must not depend on a separate WAL sidecar.
        target.execute('PRAGMA journal_mode=DELETE')
    finally:
        target.close()
        source.close()
    try:
        digest = file_hash(temporary)
        path = directory/(digest+'.sqlite3')
        if path.exists():
            if file_hash(path) != digest:
                raise ValueError('An existing archive snapshot no longer matches its hash')
            temporary.unlink()
        else:
            os.replace(temporary, path)
        return path, digest
    finally:
        if temporary.exists():
            temporary.unlink()


def open_snapshot(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
    db.row_factory = sqlite3.Row
    return db


def validate_binding(source, site):
    scopes = dict(source.execute('SELECT engine,site FROM provider_scopes'))
    engines = {r[0] for r in source.execute('SELECT DISTINCT engine FROM api_page_metrics UNION SELECT DISTINCT engine FROM observations')}
    if not engines or engines-{'google','bing'} or any(scopes.get(engine) != site for engine in engines):
        raise ValueError('Archive lacks an exact dedicated provider/property binding')
    if source.execute('SELECT 1 FROM api_page_metrics WHERE site!=? LIMIT 1', (site,)).fetchone():
        raise ValueError('Archive page metrics mix provider properties')
    return scopes


def period_status(db, period_id):
    row = db.execute('SELECT * FROM research_archive_periods WHERE id=?', (period_id,)).fetchone()
    if not row:
        raise ValueError('Unknown archive period')
    states = [dict(r) for r in db.execute('''SELECT state,reason,COUNT(*) pages FROM research_archive_pages
        WHERE period_id=? GROUP BY state,reason ORDER BY state,reason''', (period_id,))]
    totals = db.execute('''SELECT COUNT(*) pages,COALESCE(SUM(eligible),0) candidates,
        COALESCE(SUM(history_imported),0) imported FROM research_archive_pages WHERE period_id=?''', (period_id,)).fetchone()
    return dict(periodId=period_id, start=row['start'], end=row['end'], status=row['status'],
                discoveredPages=totals['pages'], candidates=totals['candidates'], historyImportedPages=totals['imported'],
                snapshot=row['snapshot_path'], snapshotSha256=row['snapshot_sha256'], states=states,
                limitation='Latest available page observations within the period; historical observations are not current ranks. Pending pages still require processing.')


def prepare_period(db, history_path, directory, start, end, site='https://manualsdump.com/', progress=None):
    start, end = str(dt.date.fromisoformat(str(start))), str(dt.date.fromisoformat(str(end)))
    if start > end or end > str(dt.datetime.now(dt.timezone.utc).date()):
        raise ValueError('Invalid archive period')
    directory = Path(directory).resolve()
    init_catalog(db)
    snapshot, digest = snapshot_history(history_path, directory/'snapshots')
    ident = key(('archive_period_v1', digest, start, end, site))
    source = open_snapshot(snapshot)
    try:
        scopes = validate_binding(source, site)
        prior = db.execute('SELECT status FROM research_archive_periods WHERE id=?', (ident,)).fetchone()
        if prior and prior['status'] == 'indexed':
            return period_status(db, ident)
        manifest = dict(kind='frozen_api_history', schemaVersion=1, snapshot=str(snapshot), sha256=digest,
            bytes=snapshot.stat().st_size, start=start, end=end, providerScopes=scopes,
            limitations=['Disclosed provider observations only; anonymized Google queries are unavailable.',
                         'Bing retains labelled snapshots, not arbitrary historical daily reports.'])
        path = directory/(ident+'.json')
        if not path.exists():
            atomic_json(path, manifest)
        proof = artifact(db, path, 'frozen_api_history', site)
        db.execute('INSERT OR IGNORE INTO research_archive_periods VALUES (?,?,?,?,?,?,?,?,?)',
                   (ident,str(snapshot),digest,start,end,site,proof,now(),'indexing'))
        db.commit()
        rows = source.execute('''WITH latest AS (
              SELECT *,ROW_NUMBER() OVER(PARTITION BY engine,url ORDER BY end DESC,start DESC,rowid DESC) n
              FROM api_page_metrics WHERE site=? AND start>=? AND end<=?), queries AS (
              SELECT engine,url,pdf,page,MAX(end) query_last_seen,COUNT(*) query_rows
              FROM observations WHERE start>=? AND end<=? AND source IN ('gsc-api-web-final','bing-api-page-query')
              GROUP BY engine,url,pdf,page)
            SELECT m.pdf,m.page,m.url,m.engine,m.start,m.end,m.clicks,m.impressions,m.position,m.id metric_id,
              q.query_last_seen,COALESCE(q.query_rows,0) query_rows FROM latest m LEFT JOIN queries q
              ON q.engine=m.engine AND q.url=m.url WHERE m.n=1
            UNION ALL SELECT q.pdf,q.page,q.url,q.engine,NULL,q.query_last_seen,0,NULL,NULL,NULL,
              q.query_last_seen,q.query_rows FROM queries q WHERE NOT EXISTS(
                SELECT 1 FROM latest m WHERE m.n=1 AND m.engine=q.engine AND m.url=q.url)
            ORDER BY pdf,page,engine,url''', (site,start,end,start,end))
        count = 0
        for (pdf,page), group in itertools.groupby(rows, key=lambda r:(r['pdf'],r['page'])):
            observations = [dict(r) for r in group]
            valid = lambda r:r['position'] is not None and r['position']>=1 and r['impressions'] is not None and r['impressions']>0
            protected = any(valid(r) and r['position']<MINIMUM_POSITION for r in observations)
            missing = any(not valid(r) for r in observations)
            eligible = not protected and not missing
            reason = 'protected_top_positions' if protected else 'page_position_unknown' if missing else 'history_import_pending'
            # Prefer a regular HTTPS URL, retaining every alias as separate evidence.
            chosen = max(observations, key=lambda r:(r['end'], '/amp/' not in r['url'],r['url'].startswith('https:'),r['url']))
            last_seen = max(max(r['end'],r['query_last_seen'] or '') for r in observations)
            db.execute('INSERT OR IGNORE INTO research_archive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident,pdf,page,chosen['url'],last_seen,max(r['clicks'] for r in observations),int(eligible),
                 'pending' if eligible else 'excluded',reason,0,packed(dict(observations=observations)),now()))
            count += 1
            if count % 1000 == 0:
                db.commit()
                if progress:
                    progress(count)
        db.execute("UPDATE research_archive_periods SET status='indexed' WHERE id=?", (ident,))
        db.commit()
    finally:
        source.close()
    return period_status(db, ident)


def archive_queue(db, period_id, limit=100):
    if not 1 <= limit <= 1000:
        raise ValueError('Archive queue limit must be 1..1000')
    status = period_status(db, period_id)
    if status['status'] != 'indexed':
        raise ValueError('Finish indexing the archive period before processing pages')
    rows = db.execute('''SELECT pdf,page,url,last_seen,priority_clicks,reason FROM research_archive_pages
        WHERE period_id=? AND eligible=1 AND state='pending' AND history_imported=0
        ORDER BY last_seen DESC,priority_clicks DESC,pdf,page LIMIT ?''', (period_id,limit))
    return dict(periodId=period_id, pages=[dict(r) for r in rows], model='gpt-6.1-sol', effort='medium')


def hydrate_pages(db, period_id, directory, limit=50):
    """Import whole page histories in a compressed batch, preserving all dates."""
    import gzip
    from import_api_history import store_window
    from ranking_policy import record as record_ranking

    directory = Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'artifacts'):
        raise ValueError('Page-history evidence must remain in workspace artifacts')
    period = db.execute('SELECT * FROM research_archive_periods WHERE id=?', (period_id,)).fetchone()
    queue = archive_queue(db, period_id, limit)['pages']
    if not queue:
        return dict(periodId=period_id, importedPages=0, importedWindows=0, held=[])
    if file_hash(period['snapshot_path']) != period['snapshot_sha256']:
        raise ValueError('Frozen history snapshot no longer matches its recorded hash')
    source = open_snapshot(period['snapshot_path'])
    items, held = [], []
    try:
        validate_binding(source, period['site'])
        # One scan of the aggregate archive per bounded batch, rather than one
        # full scan of a million daily observations for every selected page.
        source.execute('CREATE TEMP TABLE selected_pages(pdf INTEGER,page INTEGER,PRIMARY KEY(pdf,page))')
        source.executemany('INSERT INTO selected_pages VALUES (?,?)', [(p['pdf'],p['page']) for p in queue])
        source.execute('''CREATE TEMP TABLE selected_metrics AS SELECT m.rowid storage_ordinal,m.*
            FROM api_page_metrics m JOIN selected_pages p ON p.pdf=m.pdf AND p.page=m.page
            WHERE m.site=? AND m.start>=? AND m.end<=?''', (period['site'],period['start'],period['end']))
        source.execute('CREATE INDEX temp.selected_metrics_page ON selected_metrics(pdf,page)')
        checkpoints = dict(source.execute('SELECT key,payload FROM checkpoints'))
        size = 0
        for page in queue:
            identity = (page['pdf'],page['page'])
            metrics = [dict(r) for r in source.execute('SELECT * FROM selected_metrics WHERE pdf=? AND page=? ORDER BY storage_ordinal', identity)]
            for metric in metrics:
                metric.pop('storage_ordinal')
            queries = [dict(r) for r in source.execute('''SELECT engine,start,end,url,query,clicks,impressions,position,source
                FROM observations WHERE pdf=? AND page=? AND start>=? AND end<=?
                AND source IN ('gsc-api-web-final','bing-api-page-query') ORDER BY engine,start,end,url,source,query''',
                (*identity,period['start'],period['end']))]
            states, complete = {}, True
            checked = set()
            for row in metrics + queries:
                checkpoint_identity = (row['engine'],row['start'] if row['engine']=='google' else row['url'])
                if checkpoint_identity in checked: continue
                checked.add(checkpoint_identity)
                if row['engine'] == 'google':
                    name = 'google:web:'+period['site']+':'+row['start']
                    state = json.loads(checkpoints[name]) if name in checkpoints else None
                    if not state or not state.get('done'):
                        complete = False
                    states[name] = state
                else:
                    prefix = 'bing:v2:'+period['site']+':'+row['url']+':'
                    matches = [name for name in checkpoints if name.startswith(prefix)
                        and name.rsplit(':',3)[-2] <= period['start'] and name.rsplit(':',3)[-1] >= period['end']]
                    if not matches:
                        complete = False
                    else:
                        name = max(matches, key=lambda k:k.rsplit(':',3)[-3])
                        states[name] = json.loads(checkpoints[name])
            if not complete:
                held.append(dict(sourcePdfId=identity[0],page=identity[1],reason='archive_query_checkpoint_incomplete'))
                continue
            item = dict(sourcePdfId=identity[0],page=identity[1],metrics=metrics,queries=queries,checkpoints=states)
            size += len(packed(item).encode('utf-8'))
            if size > 48*1024**2:
                if not items:
                    raise ValueError('A page history exceeds the compact batch bound; use a segmented page import')
                break
            items.append(item)
    finally:
        source.close()
    if not items:
        return dict(periodId=period_id, importedPages=0, importedWindows=0, held=held)
    payload = dict(kind='saved_api_page_batch',schemaVersion=1,periodId=period_id,
        snapshotSha256=period['snapshot_sha256'],site=period['site'],pages=items,
        limitation='Complete archived rows for selected pages within this period; provider omissions remain unknown.')
    ident = key(payload)
    directory.mkdir(parents=True,exist_ok=True)
    path = directory/(ident+'.json.gz')
    if not path.exists():
        handle, temporary = tempfile.mkstemp(dir=directory, suffix='.tmp')
        try:
            with os.fdopen(handle,'wb') as stream:
                stream.write(gzip.compress(packed(payload).encode('utf-8'),mtime=0))
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    proof = artifact(db,path,'saved_api_page_batch',period['site'])
    db.commit()
    imported_windows = 0
    for item in items:
        pdf,page = item['sourcePdfId'],item['page']
        with db:
            latest_metrics = {}
            for metric in item['metrics']:
                inventory_id = key(('archive_page_metric',period['snapshot_sha256'],metric['id']))
                db.execute('INSERT OR IGNORE INTO research_inventory VALUES (?,?,?,?,?,?,?)',
                    (inventory_id,metric['engine'],metric['start'],metric['end'],proof,1,'Frozen API page aggregate; complete source row is in the compressed batch.'))
                db.execute('INSERT OR IGNORE INTO research_discovered_pages VALUES (?,?,?,?,?,?)',
                    (inventory_id,pdf,page,metric['url'],metric['clicks'],metric['impressions']))
                record_ranking(db,metric['engine'],metric['start'],metric['end'],metric['url'],metric['position'],metric['impressions'],proof,'api_page_metrics')
                latest_metrics[(metric['engine'],metric['start'],metric['end'],metric['url'])] = metric
            groups = itertools.groupby(item['queries'],key=lambda r:(r['engine'],r['start'],r['end'],r['url'],r['source']))
            seen = set()
            for (engine,start,end,url,provenance), group in groups:
                rows = [{k:r[k] for k in ('query','clicks','impressions','position')} for r in group]
                identity = (engine,start,end,url);seen.add(identity)
                state = item['checkpoints']['google:web:'+period['site']+':'+start] if engine=='google' else {'coverage':'retained snapshot; historical completeness unknown'}
                imported_windows += store_window(db,directory,engine,period['site'],start,end,url,provenance,state,rows,
                    latest_metrics.get(identity),raw_artifact=proof,commit=False,refresh=False)
            for identity, metric in latest_metrics.items():
                if identity in seen: continue
                engine,start,end,url = identity
                state = item['checkpoints']['google:web:'+period['site']+':'+start] if engine=='google' else {'coverage':'retained snapshot; historical completeness unknown'}
                provenance = 'gsc-api-no-disclosed-query-rows' if engine=='google' else 'bing-api-no-disclosed-query-rows'
                imported_windows += store_window(db,directory,engine,period['site'],start,end,url,provenance,state,[],metric,
                    raw_artifact=proof,commit=False,refresh=False)
            refresh_stage(db,pdf,page)
            stage = db.execute('SELECT stage FROM research_pages WHERE pdf=? AND page=?',(pdf,page)).fetchone()
            changed=db.execute('''UPDATE research_archive_pages SET history_imported=1,reason=?,updated=?
                WHERE period_id=? AND pdf=? AND page=?''',(stage['stage'] if stage else 'content_pending',now(),period_id,pdf,page)).rowcount
            if changed != 1: raise ValueError('Imported page does not match its archive queue identity')
    return dict(periodId=period_id, importedPages=len(items), importedWindows=imported_windows, held=held,
                batchArtifact=proof,compressedBytes=path.stat().st_size,providerRequestsMade=0)


def archive_context_queue(db,period_id,limit=100,retry_unavailable=False):
    if not 1 <= limit <= 1000:
        raise ValueError('Archive context queue limit must be 1..1000')
    period_status(db,period_id)
    rows = db.execute('''SELECT p.pdf,p.page FROM research_archive_pages p
        LEFT JOIN research_pages r ON r.pdf=p.pdf AND r.page=p.page
        LEFT JOIN research_context_attempts a ON a.pdf=p.pdf AND a.page=p.page
        WHERE p.period_id=? AND p.eligible=1 AND p.state='pending' AND p.history_imported=1 AND r.content_id IS NULL
        AND (? OR a.pdf IS NULL OR a.reason='batch_byte_limit')
        ORDER BY p.last_seen DESC,p.priority_clicks DESC,p.pdf,p.page LIMIT ?''',(period_id,retry_unavailable,limit))
    return dict(periodId=period_id,pages=[dict(sourcePdfId=r['pdf'],page=r['page']) for r in rows])


def reconcile_period(db,period_id):
    """Assess imported pages against the exact current generation request."""
    from outcomes import page_outcome
    period_status(db,period_id)
    rows=db.execute('''SELECT pdf,page,detail FROM research_archive_pages
        WHERE period_id=? AND eligible=1 AND history_imported=1
        ORDER BY last_seen DESC,priority_clicks DESC,pdf,page''',(period_id,)).fetchall()
    for row in rows:
        # Release the writer between pages so concurrent source imports can proceed.
        # A failed assessment rolls back only its page; completed progress survives.
        with db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            outcome=page_outcome(db,row['pdf'],row['page'])
            current=db.execute('SELECT detail FROM research_archive_pages WHERE period_id=? AND pdf=? AND page=?',
                (period_id,row['pdf'],row['page'])).fetchone()
            detail=json.loads(current['detail']);detail['processing']=outcome
            db.execute('''UPDATE research_archive_pages SET state=?,reason=?,detail=?,updated=?
                WHERE period_id=? AND pdf=? AND page=?''',(outcome['state'],outcome['reason'] or 'metadata_draft_saved',
                packed(detail),now(),period_id,row['pdf'],row['page']))
        time.sleep(0)
    return dict(period_status(db,period_id),assessedImportedPages=len(rows))
