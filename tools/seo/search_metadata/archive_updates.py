"""Stage a frozen provider-history update without changing live model inputs."""
import datetime as dt
import json
import os
import shutil
import sqlite3
import tempfile
import unicodedata
from pathlib import Path

from archive_catalog import file_hash, open_snapshot, validate_binding
from generate import atomic_json
from history import bind_scope, checkpoint, ingest, ingest_page_metrics, page_key
from research import ROOT, key


def frozen_input(path, expected_hash):
    path = Path(path).resolve()
    if not path.is_file() or not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError('A frozen input file and its SHA-256 are required')
    wal = Path(str(path) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Checkpoint the history WAL before supplying a frozen input hash')
    if file_hash(path) != expected_hash:
        raise ValueError('Frozen update input no longer matches its SHA-256')
    return path


def stage_history_update(parent_path, parent_sha256, delta_path, delta_sha256,
                         directory, start, end, site='https://manualsdump.com/', minimum_free_bytes=0):
    """Copy the whole base archive, upsert real differences, and keep every old date.

    This is an offline preparation step. It does not index/adopt the new period,
    alter the research database, reconcile drafts, call a provider or run a model.
    """
    start, end = str(dt.date.fromisoformat(str(start))), str(dt.date.fromisoformat(str(end)))
    if start > end or end > str(dt.datetime.now(dt.timezone.utc).date()):
        raise ValueError('Invalid archive update period')
    parent_path = frozen_input(parent_path, parent_sha256)
    delta_path = frozen_input(delta_path, delta_sha256)
    directory = Path(directory).resolve()
    if not directory.is_relative_to(ROOT / 'artifacts'):
        raise ValueError('Updated archive outputs must remain in workspace artifacts')
    directory.mkdir(parents=True, exist_ok=True)
    seed = dict(schemaVersion=1, parentSha256=parent_sha256, deltaSha256=delta_sha256,
                site=site, start=start, end=end, policy='preserve_history_upsert_semantic_differences_v1')
    update_id = key(seed)
    manifest_path = directory / (update_id + '.json')
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding='utf-8'))
        if key({name: value for name, value in previous.items() if name != 'manifestSha256'}) != previous.get('manifestSha256'):
            raise ValueError('Archive update manifest integrity mismatch')
        if previous.get('inputs') != seed or previous.get('updateId') != update_id:
            raise ValueError('Archive update manifest changed')
        snapshot = Path(previous['snapshot']).resolve()
        if snapshot.parent != directory or snapshot.name != previous['snapshotSha256'] + '.sqlite3':
            raise ValueError('Invalid updated snapshot path')
        frozen_input(snapshot, previous['snapshotSha256'])
        return dict(previous, reused=True, manifest=str(manifest_path))
    required = max(minimum_free_bytes, parent_path.stat().st_size * 2 + delta_path.stat().st_size)
    if shutil.disk_usage(directory).free < required:
        raise ValueError('Insufficient free disk space for a frozen archive update')
    parent, delta = open_snapshot(parent_path), open_snapshot(delta_path)
    temporary = None
    target = None
    try:
        validate_binding(parent, site)
        delta_scopes = validate_binding(delta, site)
        metrics = [dict(row) for row in delta.execute('SELECT * FROM api_page_metrics ORDER BY engine,start,end,url,rowid LIMIT 100001')]
        queries = [dict(row) for row in delta.execute('SELECT * FROM observations ORDER BY engine,start,end,url,query LIMIT 100001')]
        if len(metrics) + len(queries) > 100000:
            raise ValueError('Use a bounded history delta of at most100000 rows')
        for row in metrics + queries:
            if not start <= row['start'] <= row['end'] <= end:
                raise ValueError('Delta rows fall outside the selected archive period')
            if page_key(row['url']) != (row['pdf'], row['page']):
                raise ValueError('Delta row page identity mismatch')
            if 'source' in row and row['source'] != {'google': 'gsc-api-web-final', 'bing': 'bing-api-page-query'}.get(row['engine']):
                raise ValueError('Unsupported query provenance in archive delta')
        google_days = {row['start'] for row in metrics + queries if row['engine'] == 'google'}
        checkpoints = {}
        for day in sorted(google_days):
            if any(row['engine'] == 'google' and row['start'] == day and row['end'] != day for row in metrics + queries):
                raise ValueError('Google API rows must retain their daily scope')
            name = 'google:web:' + site + ':' + day
            state = checkpoint(delta, name)
            if not state or state.get('done') is not True:
                raise ValueError('Google delta requires its complete saved query checkpoint')
            checkpoints[name] = state
        handle, temporary = tempfile.mkstemp(prefix=update_id + '-', suffix='.sqlite3', dir=directory)
        os.close(handle)
        temporary = Path(temporary)
        target = sqlite3.connect(temporary)
        target.row_factory = sqlite3.Row
        parent.backup(target)
        target.execute('PRAGMA journal_mode=DELETE')
        for engine in delta_scopes:
            bind_scope(target, engine, site)
        changed, stats = set(), dict(newPageMetrics=0, changedPageMetrics=0, unchangedPageMetrics=0,
                                     newQueryRows=0, changedQueryRows=0, unchangedQueryRows=0)
        with target:
            for row in metrics:
                identity = (row['engine'], site, row['start'], row['end'], row['url'])
                before = target.execute('''SELECT clicks,impressions,position FROM api_page_metrics
                    WHERE engine=? AND site=? AND start=? AND end=? AND url=? ORDER BY rowid DESC LIMIT 1''', identity).fetchone()
                values = (row['clicks'], row['impressions'], row['position'])
                if before and tuple(before) == values:
                    stats['unchangedPageMetrics'] += 1
                    continue
                ingest_page_metrics(target, *identity, *values, json.loads(row['payload']))
                stats['changedPageMetrics' if before else 'newPageMetrics'] += 1
                changed.add((row['pdf'], row['page']))
            for row in queries:
                row['query'] = unicodedata.normalize('NFKC', row['query']).strip()
                identity = tuple(row[name] for name in ('engine', 'start', 'end', 'url', 'query'))
                before = target.execute('''SELECT clicks,impressions,position FROM observations
                    WHERE engine=? AND start=? AND end=? AND url=? AND query=?''', identity).fetchone()
                if before and tuple(before) == (row['clicks'], row['impressions'], row['position']):
                    stats['unchangedQueryRows'] += 1
                    continue
                ingest(target, [row], row['source'])
                stats['changedQueryRows' if before else 'newQueryRows'] += 1
                changed.add((row['pdf'], row['page']))
            for name, state in checkpoints.items():
                checkpoint(target, name, state)
        validate_binding(target, site)
        if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Updated archive failed SQLite quick_check')
        target.close()
        target = None
        # Recheck both immutable inputs before publishing the new artifact.
        frozen_input(parent_path, parent_sha256)
        frozen_input(delta_path, delta_sha256)
        snapshot_sha256 = file_hash(temporary)
        snapshot = directory / (snapshot_sha256 + '.sqlite3')
        if snapshot.exists():
            frozen_input(snapshot, snapshot_sha256)
            temporary.unlink()
        else:
            os.replace(temporary, snapshot)
        manifest = dict(updateId=update_id, inputs=seed, snapshot=str(snapshot), snapshotSha256=snapshot_sha256,
                        changedPages=[dict(sourcePdfId=pdf, page=page) for pdf, page in sorted(changed)],
                        statistics=stats, createdAt=dt.datetime.now(dt.timezone.utc).isoformat(),
                        activeResearchDatabaseChanged=False, parentSnapshotChanged=False,
                        modelCallsMade=0, providerRequestsMade=0, activationAllowed=False,
                        nextStep='Adopt at a verified generation boundary, retaining unchanged history and reconciling affected eligibility/drafts.',
                        limitations=['Omitted queries are not deleted; all earlier saved observations are retained.',
                                     'Bing labels remain retained snapshots, not invented daily intervals.',
                                     'An offline updated snapshot is not an activated or fully processed period.'])
        manifest['manifestSha256'] = key(manifest)
        atomic_json(manifest_path, manifest)
        return dict(manifest, reused=False, manifest=str(manifest_path))
    finally:
        if target is not None:
            target.close()
        parent.close()
        delta.close()
        if temporary is not None and temporary.exists():
            temporary.unlink()
