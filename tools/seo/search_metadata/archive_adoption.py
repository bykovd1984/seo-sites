"""Resumable, generation-locked adoption of a verified frozen history update."""
import json
import shutil
import sqlite3
import unicodedata
from pathlib import Path

from archive_catalog import (hydrate_pages, init_catalog, open_snapshot,
                             period_status, prepare_period, validate_binding)
from archive_updates import frozen_input
from generate import atomic_json
from history import page_key
from ranking_policy import eligibility, record as record_ranking
from research import ROOT, artifact, key, now, packed


def init_adoptions(db):
    init_catalog(db)
    db.executescript('''
      CREATE TABLE IF NOT EXISTS research_archive_adoptions(
        id TEXT PRIMARY KEY,parent_period TEXT NOT NULL,new_period TEXT,
        manifest_artifact TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,updated TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS research_archive_adoption_checks(
        adoption_id TEXT NOT NULL,pdf INTEGER NOT NULL,page INTEGER NOT NULL,kind TEXT NOT NULL,
        state TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(adoption_id,pdf,page));
    ''')


def adoption_status(db, ident):
    row = db.execute('SELECT * FROM research_archive_adoptions WHERE id=?', (ident,)).fetchone()
    if not row:
        raise ValueError('Unknown archive adoption')
    result = dict(row)
    result['payload'] = json.loads(result['payload'])
    result['checks'] = [dict(r) for r in db.execute('''SELECT kind,state,count(*) pages
        FROM research_archive_adoption_checks WHERE adoption_id=? GROUP BY kind,state''', (ident,))]
    result.update(modelCallsMade=0, providerRequestsMade=0, activationAllowed=False)
    return result


def _validate_update(db, parent_id, manifest_path, delta_path):
    manifest_path = Path(manifest_path).resolve()
    if not manifest_path.is_relative_to(ROOT / 'artifacts'):
        raise ValueError('Archive update manifest must remain in workspace artifacts')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if key({k: v for k, v in manifest.items() if k != 'manifestSha256'}) != manifest.get('manifestSha256'):
        raise ValueError('Archive update manifest integrity mismatch')
    seed = manifest['inputs']
    if key(seed) != manifest['updateId'] or seed['schemaVersion'] != 1:
        raise ValueError('Archive update identity mismatch')
    parent = db.execute('SELECT * FROM research_archive_periods WHERE id=?', (parent_id,)).fetchone()
    if not parent or any(parent[name] != seed[field] for name, field in (
            ('snapshot_sha256', 'parentSha256'), ('site', 'site'), ('start', 'start'), ('end', 'end'))):
        raise ValueError('Archive update does not match the selected parent period')
    frozen_input(parent['snapshot_path'], seed['parentSha256'])
    frozen_input(delta_path, seed['deltaSha256'])
    frozen_input(manifest['snapshot'], manifest['snapshotSha256'])
    return parent, manifest


def _verify_semantic_update(parent_path, delta_path, merged_path, manifest):
    """Prove every retained/revised row and derive affected pages from the delta."""
    db = open_snapshot(merged_path)
    try:
        db.execute('ATTACH DATABASE ? AS original', (Path(parent_path).resolve().as_uri() + '?mode=ro&immutable=1',))
        db.execute('ATTACH DATABASE ? AS delta', (Path(delta_path).resolve().as_uri() + '?mode=ro&immutable=1',))
        validate_binding(db, manifest['inputs']['site'])
        delta = open_snapshot(delta_path)
        try:
            validate_binding(delta, manifest['inputs']['site'])
            changed, metric_scopes, count = set(), set(), 0
            for table in ('api_page_metrics', 'observations'):
                for row in delta.execute('SELECT * FROM ' + table):
                    count += 1
                    if count > 100000:
                        raise ValueError('Archive delta exceeds the bounded row limit')
                    if page_key(row['url']) != (row['pdf'], row['page']):
                        raise ValueError('Delta page identity mismatch')
                    if not manifest['inputs']['start'] <= row['start'] <= row['end'] <= manifest['inputs']['end']:
                        raise ValueError('Delta rows fall outside the selected period')
                    if table == 'observations' and row['source'] != {'google': 'gsc-api-web-final', 'bing': 'bing-api-page-query'}[row['engine']]:
                        raise ValueError('Delta query provenance differs from the provider')
                    names = ('engine', 'site', 'start', 'end', 'url') if table == 'api_page_metrics' else ('engine', 'start', 'end', 'url', 'query')
                    if table == 'observations' and row['query'] != unicodedata.normalize('NFKC', row['query']).strip():
                        raise ValueError('Delta query is not normalized')
                    args = tuple(row[name] for name in names)
                    before = db.execute('SELECT clicks,impressions,position FROM original.' + table + ' WHERE ' +
                                        ' AND '.join(name + '=?' for name in names) + ' ORDER BY rowid DESC LIMIT 1', args).fetchone()
                    if not before or tuple(before) != (row['clicks'], row['impressions'], row['position']):
                        changed.add((row['pdf'], row['page']))
                        if table == 'api_page_metrics':
                            metric_scopes.add((row['engine'], row['start'], row['end'], row['url']))
        finally:
            delta.close()
        declared = [(r['sourcePdfId'], r['page']) for r in manifest['changedPages']]
        if len(declared) != len(set(declared)) or set(declared) != changed:
            raise ValueError('Affected-page manifest differs from the actual history delta')
        query_key = 'n.engine=o.engine AND n.start=o.start AND n.end=o.end AND n.url=o.url AND n.query=o.query'
        query_values = 'n.pdf=o.pdf AND n.page=o.page AND n.clicks=o.clicks AND n.impressions=o.impressions AND n.position IS o.position AND n.source=o.source'
        metric_values = 'n.engine=o.engine AND n.site=o.site AND n.start=o.start AND n.end=o.end AND n.url=o.url AND n.pdf=o.pdf AND n.page=o.page AND n.clicks=o.clicks AND n.impressions=o.impressions AND n.position IS o.position AND n.payload=o.payload'
        checks = {
            'baseMetrics': 'SELECT count(*) FROM original.api_page_metrics o WHERE NOT EXISTS(SELECT 1 FROM main.api_page_metrics n WHERE n.id=o.id AND n.rowid=o.rowid AND ' + metric_values + ')',
            'unchangedBaseQueries': 'SELECT count(*) FROM original.observations o WHERE NOT EXISTS(SELECT 1 FROM delta.observations n WHERE ' + query_key + ') AND NOT EXISTS(SELECT 1 FROM main.observations n WHERE ' + query_key + ' AND ' + query_values + ')',
            'deltaQueries': 'SELECT count(*) FROM delta.observations o WHERE NOT EXISTS(SELECT 1 FROM main.observations n WHERE ' + query_key + ' AND ' + query_values + ')',
            'unexplainedMetrics': 'SELECT count(*) FROM main.api_page_metrics o WHERE NOT EXISTS(SELECT 1 FROM original.api_page_metrics n WHERE n.id=o.id) AND NOT EXISTS(SELECT 1 FROM delta.api_page_metrics n WHERE ' + metric_values + ')',
            'unexplainedQueries': 'SELECT count(*) FROM main.observations o WHERE NOT EXISTS(SELECT 1 FROM original.observations n WHERE ' + query_key + ') AND NOT EXISTS(SELECT 1 FROM delta.observations n WHERE ' + query_key + ' AND ' + query_values + ')',
        }
        for name, sql in checks.items():
            if db.execute(sql).fetchone()[0]:
                raise ValueError('Updated archive failed semantic verification: ' + name)
        # Every latest page aggregate in the delta must be represented semantically;
        # payload-only recaptures need not create a duplicate metric ID.
        missing = db.execute('''WITH latest AS (SELECT *,ROW_NUMBER() OVER(
            PARTITION BY engine,site,start,end,url ORDER BY rowid DESC) n FROM delta.api_page_metrics)
            SELECT count(*) FROM latest o WHERE o.n=1 AND NOT EXISTS(SELECT 1 FROM main.api_page_metrics n
            WHERE n.engine=o.engine AND n.site=o.site AND n.start=o.start AND n.end=o.end AND n.url=o.url
            AND n.rowid=(SELECT max(v.rowid) FROM main.api_page_metrics v WHERE v.engine=o.engine AND v.site=o.site
                AND v.start=o.start AND v.end=o.end AND v.url=o.url)
            AND n.clicks=o.clicks AND n.impressions=o.impressions AND n.position IS o.position)''').fetchone()[0]
        if missing:
            raise ValueError('Updated archive omits a delta page aggregate')
        return sorted(changed), sorted(metric_scopes)
    finally:
        db.close()


def _set_state(db, ident, state, payload):
    db.execute('UPDATE research_archive_adoptions SET state=?,payload=?,updated=? WHERE id=?',
               (state, packed(payload), now(), ident))


def verify_history_update(db, parent_id, manifest_path, delta_path):
    parent, manifest = _validate_update(db, parent_id, manifest_path, delta_path)
    changed, scopes = _verify_semantic_update(parent['snapshot_path'], delta_path, manifest['snapshot'], manifest)
    return dict(updateId=manifest['updateId'], manifestSha256=manifest['manifestSha256'],
                parentPeriod=parent_id, parentSnapshotSha256=parent['snapshot_sha256'],
                updateSnapshotSha256=manifest['snapshotSha256'], deltaSha256=manifest['inputs']['deltaSha256'],
                changedPages=[dict(sourcePdfId=pdf, page=page) for pdf, page in changed],
                changedMetricScopes=[list(scope) for scope in scopes], verified=True,
                activeResearchDatabaseChanged=False, providerRequestsMade=0, modelCallsMade=0)


def _inherit(db, parent_id, new_id, ident):
    changed = 'NOT EXISTS(SELECT 1 FROM adoption_changed c WHERE c.pdf=n.pdf AND c.page=n.page)'
    with db:
        inherited = db.execute('''UPDATE research_archive_pages AS n SET history_imported=1,
            state=(SELECT o.state FROM research_archive_pages o WHERE o.period_id=? AND o.pdf=n.pdf AND o.page=n.page),
            reason=(SELECT o.reason FROM research_archive_pages o WHERE o.period_id=? AND o.pdf=n.pdf AND o.page=n.page),
            detail=json_patch(n.detail,(SELECT json_object('historyInheritedFrom',?,
              'processing',json_extract(o.detail,'$.processing')) FROM research_archive_pages o
              WHERE o.period_id=? AND o.pdf=n.pdf AND o.page=n.page)),updated=?
            WHERE n.period_id=? AND n.eligible=1 AND ''' + changed + ''' AND EXISTS(
              SELECT 1 FROM research_archive_pages o WHERE o.period_id=? AND o.pdf=n.pdf AND o.page=n.page
              AND o.eligible=1 AND o.history_imported=1)''',
            (parent_id, parent_id, parent_id, parent_id, now(), new_id, parent_id)).rowcount
        db.execute('''INSERT OR IGNORE INTO research_archive_adoption_checks
            SELECT ?,n.pdf,n.page,'inherited','pending','{}' FROM research_archive_pages n
            WHERE n.period_id=? AND n.history_imported=1 AND n.state!='pending' ''', (ident, new_id))
        db.execute('''INSERT OR IGNORE INTO research_archive_adoption_checks
            SELECT ?,n.pdf,n.page,'changed','pending','{}' FROM research_archive_pages n JOIN adoption_changed c
            ON c.pdf=n.pdf AND c.page=n.page WHERE n.period_id=?''', (ident, new_id))
    return inherited


def _sync_rankings(db, ident, new_id, directory, metric_scopes):
    rows = []
    for page in db.execute('''SELECT n.pdf,n.page,n.detail FROM research_archive_pages n JOIN adoption_changed c
        ON c.pdf=n.pdf AND c.page=n.page WHERE n.period_id=? ORDER BY n.pdf,n.page''', (new_id,)):
        for observation in json.loads(page['detail'])['observations']:
            rows.append({**observation, 'sourcePdfId': page['pdf'], 'page': page['page']})
    payload = dict(kind='archive_update_page_rankings', adoptionId=ident, periodId=new_id, rows=rows,
                   limitation='Frozen latest page aggregates and explicit unknown scopes; old verified non-API evidence is retained.')
    path = Path(directory) / ('rankings-' + key(payload) + '.json')
    if not path.exists():
        atomic_json(path, payload)
    proof = artifact(db, path, 'archive_update_page_rankings')
    scopes, imported = set(map(tuple, metric_scopes)), 0
    with db:
        for row in rows:
            start, end = row['start'] or row['end'], row['end']
            scope = (row['engine'], start, end, row['url'])
            current = db.execute('''SELECT position,impressions FROM research_page_rankings
                WHERE engine=? AND start=? AND end=? AND url=? ORDER BY rowid DESC LIMIT 1''', scope).fetchone()
            # A frozen baseline must not overwrite a later reconciled CSV/report
            # at the same scope. Actual changed API captures may replace it.
            if current and (scope not in scopes or tuple(current) == (row['position'], row['impressions'])):
                continue
            if row['metric_id'] is None and db.execute('''SELECT 1 FROM research_page_rankings
                WHERE engine=? AND url=? AND position IS NOT NULL LIMIT 1''', (row['engine'], row['url'])).fetchone():
                continue
            record_ranking(db, row['engine'], start, end, row['url'], row['position'], row['impressions'],
                           proof, 'archive_update_page_metrics' if row['metric_id'] else 'archive_update_unknown_page_position')
            imported += 1
    return imported


def adopt_history_update(db, parent_id, manifest_path, delta_path, directory, limit=100, minimum_free_bytes=0):
    """Call only while holding the shared generation lock; each call is bounded."""
    if not 1 <= limit <= 1000:
        raise ValueError('Adoption batch limit must be 1..1000')
    init_adoptions(db)
    parent, manifest = _validate_update(db, parent_id, manifest_path, delta_path)
    ident = manifest['updateId']
    row = db.execute('SELECT * FROM research_archive_adoptions WHERE id=?', (ident,)).fetchone()
    if row and row['state'] == 'ready':
        return dict(adoption_status(db, ident), reused=True)
    active = db.execute("SELECT value FROM research_settings WHERE name='archive_adoption_in_progress'").fetchone()
    if active and json.loads(active[0]) != ident:
        raise ValueError('Resume the existing archive adoption before another update')
    directory = Path(directory).resolve()
    if not directory.is_relative_to(ROOT / 'artifacts'):
        raise ValueError('Adoption outputs must remain in workspace artifacts')
    directory.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(directory).free < max(minimum_free_bytes, Path(parent['snapshot_path']).stat().st_size * 2):
        raise ValueError('Insufficient free disk space for archive adoption')
    if not row:
        if parent['status'] != 'indexed':
            raise ValueError('Select the current indexed parent period')
        changed, scopes = _verify_semantic_update(parent['snapshot_path'], delta_path, manifest['snapshot'], manifest)
        proof = artifact(db, manifest_path, 'archive_update_manifest', parent['site'])
        payload = dict(changedPages=[list(pair) for pair in changed], changedMetricScopes=[list(pair) for pair in scopes],
                       semanticUpdateVerified=True, manifestSha256=manifest['manifestSha256'],
                       parentSnapshotSha256=parent['snapshot_sha256'], updateSnapshotSha256=manifest['snapshotSha256'],
                       outputDirectory=str(directory))
        with db:
            db.execute('INSERT INTO research_archive_adoptions VALUES (?,?,NULL,?,?,?,?)',
                       (ident, parent_id, proof, 'indexing', packed(payload), now()))
            db.execute('INSERT OR REPLACE INTO research_settings VALUES (?,?,?)',
                       ('archive_adoption_in_progress', packed(ident), now()))
        row = db.execute('SELECT * FROM research_archive_adoptions WHERE id=?', (ident,)).fetchone()
    payload = json.loads(row['payload'])
    if row['parent_period'] != parent_id or payload['manifestSha256'] != manifest['manifestSha256'] or payload['outputDirectory'] != str(directory):
        raise ValueError('Resume the adoption with its original parent, manifest and directory')
    db.execute('CREATE TEMP TABLE IF NOT EXISTS adoption_changed(pdf INTEGER,page INTEGER,PRIMARY KEY(pdf,page))')
    db.execute('DELETE FROM adoption_changed')
    db.executemany('INSERT INTO adoption_changed VALUES (?,?)', payload['changedPages'])
    db.commit()
    if row['state'] == 'indexing':
        result = prepare_period(db, manifest['snapshot'], directory, parent['start'], parent['end'], parent['site'])
        new_id = result['periodId']
        if new_id == parent_id:
            raise ValueError('An adoption must produce a distinct frozen period')
        with db:
            db.execute("UPDATE research_archive_periods SET status='adopting' WHERE id=?", (new_id,))
            db.execute('UPDATE research_archive_adoptions SET new_period=? WHERE id=?', (new_id, ident))
            _set_state(db, ident, 'inheritance', payload)
        row = db.execute('SELECT * FROM research_archive_adoptions WHERE id=?', (ident,)).fetchone()
    new_id = row['new_period']
    if row['state'] == 'inheritance':
        payload['inheritedHistoryPages'] = _inherit(db, parent_id, new_id, ident)
        payload['rankingRowsImported'] = _sync_rankings(db, ident, new_id, directory, payload['changedMetricScopes'])
        with db:
            _set_state(db, ident, 'checking', payload)
    # Complete changed-page windows before assessing their new generation hashes.
    # Only changed eligible pages are hydrated; inherited full histories stay intact.
    candidates = db.execute('''SELECT n.pdf,n.page FROM research_archive_pages n JOIN adoption_changed c
        ON c.pdf=n.pdf AND c.page=n.page WHERE n.period_id=? AND n.eligible=1 AND n.history_imported=0
        ORDER BY n.last_seen DESC,n.priority_clicks DESC,n.pdf,n.page''', (new_id,)).fetchall()
    needed = [(r['pdf'], r['page']) for r in candidates if eligibility(db, r['pdf'], r['page'])['eligible']
              and not db.execute('''SELECT 1 FROM research_archive_adoption_checks WHERE adoption_id=?
                  AND pdf=? AND page=? AND state='held' ''', (ident, r['pdf'], r['page'])).fetchone()]
    if needed:
        result = hydrate_pages(db, new_id, directory / 'updated-page-batches', min(limit, len(needed)), selected_pages=needed[:limit])
        for held in result['held']:
            with db:
                db.execute('''UPDATE research_archive_adoption_checks SET state='held',payload=?
                    WHERE adoption_id=? AND pdf=? AND page=?''', (packed(held), ident, held['sourcePdfId'], held['page']))
                db.execute('''UPDATE research_archive_pages SET reason=?,updated=? WHERE period_id=? AND pdf=? AND page=?''',
                           (held['reason'], now(), new_id, held['sourcePdfId'], held['page']))
        remaining = [pair for pair in needed if not db.execute('''SELECT 1 FROM research_archive_pages
            WHERE period_id=? AND pdf=? AND page=? AND history_imported=1''', (new_id, *pair)).fetchone()
            and not db.execute('''SELECT 1 FROM research_archive_adoption_checks WHERE adoption_id=? AND pdf=? AND page=? AND state='held' ''', (ident, *pair)).fetchone()]
        if remaining:
            return dict(adoption_status(db, ident), reused=False)
    from outcomes import page_outcome
    checks = db.execute('''SELECT pdf,page FROM research_archive_adoption_checks WHERE adoption_id=? AND state='pending'
        ORDER BY kind,pdf,page LIMIT ?''', (ident, limit)).fetchall()
    for check in checks:
        with db:
            if not db.in_transaction:
                db.execute('BEGIN IMMEDIATE')
            outcome = page_outcome(db, check['pdf'], check['page'])
            current = db.execute('''SELECT detail FROM research_archive_pages WHERE period_id=? AND pdf=? AND page=?''',
                                 (new_id, check['pdf'], check['page'])).fetchone()
            detail = json.loads(current['detail'])
            detail['processing'] = outcome
            db.execute('''UPDATE research_archive_pages SET state=?,reason=?,detail=?,updated=?
                WHERE period_id=? AND pdf=? AND page=?''', (outcome['state'], outcome['reason'] or 'metadata_draft_saved',
                packed(detail), now(), new_id, check['pdf'], check['page']))
            db.execute('''UPDATE research_archive_adoption_checks SET state='done',payload=?
                WHERE adoption_id=? AND pdf=? AND page=?''', (packed(outcome), ident, check['pdf'], check['page']))
    pending = db.execute("SELECT count(*) FROM research_archive_adoption_checks WHERE adoption_id=? AND state='pending'", (ident,)).fetchone()[0]
    if not pending:
        with db:
            db.execute("UPDATE research_archive_periods SET status='indexed' WHERE id=?", (new_id,))
            db.execute("UPDATE research_archive_periods SET status='superseded' WHERE id=?", (parent_id,))
            db.execute("DELETE FROM research_settings WHERE name='archive_adoption_in_progress'")
            db.execute('INSERT OR REPLACE INTO research_settings VALUES (?,?,?)', ('archive_active_period', packed(new_id), now()))
            _set_state(db, ident, 'ready', payload)
    return dict(adoption_status(db, ident), reused=False)
