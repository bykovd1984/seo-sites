"""SQLite state, immutable compressed evidence, resumable jobs and model decisions."""
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import sqlite3
import time
import uuid
from pathlib import Path


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(packed(value).encode('utf-8')).hexdigest()


def date_range(start, end):
    first, last = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    if first > last or last > dt.datetime.now(dt.timezone.utc).date() or (last - first).days > 550:
        raise ValueError('Use a valid past date range of at most 551 days')
    return str(first), str(last)


def bounded_text(value, maximum=1000, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()) or '\x00' in value:
        raise ValueError('Invalid text value')
    return value.strip()


def finite(value, minimum=0, maximum=None, integer=False, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Invalid numeric metric')
    if value < minimum or maximum is not None and value > maximum or integer and value != int(value):
        raise ValueError('Metric outside allowed range')
    return int(value) if integer else value


def initialize_schema(db,schema):
    # Concurrent first-use MCP clients can race PRAGMA journal_mode even with
    # busy_timeout. The schema contains only idempotent CREATE IF NOT EXISTS.
    deadline=time.monotonic()+30
    while True:
        try:
            db.executescript(schema)
            return
        except sqlite3.OperationalError as exc:
            if getattr(exc,'sqlite_errorcode',0) & 255 not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED) or time.monotonic()>=deadline:
                raise
            db.rollback()
            time.sleep(.05)


class Store:
    def __init__(self, home):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.home / 'research.sqlite3', timeout=30)
        self.db.row_factory = sqlite3.Row
        initialize_schema(self.db,'''
          PRAGMA journal_mode=WAL;
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS subjects(
            id TEXT PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL, identity TEXT NOT NULL,
            payload TEXT NOT NULL, content_hash TEXT NOT NULL, updated TEXT NOT NULL,
            UNIQUE(project,kind,identity));
          CREATE TABLE IF NOT EXISTS datasets(
            id TEXT PRIMARY KEY, project TEXT NOT NULL, provider TEXT NOT NULL, kind TEXT NOT NULL,
            scope TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, observed TEXT NOT NULL,
            payload TEXT NOT NULL, artifact TEXT NOT NULL, row_count INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS metrics(
            dataset TEXT NOT NULL REFERENCES datasets(id), row_key TEXT NOT NULL, url TEXT NOT NULL,
            query TEXT, country TEXT, device TEXT, clicks INTEGER NOT NULL, impressions INTEGER NOT NULL,
            position REAL, payload TEXT NOT NULL, PRIMARY KEY(dataset,row_key));
          CREATE INDEX IF NOT EXISTS metrics_url ON metrics(url,dataset);
          CREATE TABLE IF NOT EXISTS jobs(
            id TEXT PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL, request TEXT NOT NULL,
            state TEXT NOT NULL, progress TEXT NOT NULL, result TEXT NOT NULL, error TEXT,
            created TEXT NOT NULL, updated TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state,created);
          CREATE TABLE IF NOT EXISTS keyword_reports(
            id TEXT PRIMARY KEY, cache_key TEXT NOT NULL, observed TEXT NOT NULL, artifact TEXT NOT NULL,
            request TEXT NOT NULL, result TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS keyword_cache ON keyword_reports(cache_key,observed);
          CREATE TABLE IF NOT EXISTS keyword_links(
            project TEXT NOT NULL, subject TEXT NOT NULL REFERENCES subjects(id), report TEXT NOT NULL REFERENCES keyword_reports(id),
            seed TEXT NOT NULL, PRIMARY KEY(project,subject,report,seed));
          CREATE TABLE IF NOT EXISTS attempts(
            id TEXT PRIMARY KEY, job TEXT NOT NULL, started TEXT NOT NULL, status TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS bundles(
            id TEXT PRIMARY KEY, project TEXT NOT NULL, subject TEXT NOT NULL, artifact TEXT NOT NULL, created TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS decisions(
            id TEXT PRIMARY KEY, project TEXT NOT NULL, bundle TEXT NOT NULL REFERENCES bundles(id),
            payload TEXT NOT NULL, created TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS worker_state(id INTEGER PRIMARY KEY CHECK(id=1),pid INTEGER NOT NULL,heartbeat TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS provider_safety(
            provider TEXT PRIMARY KEY, incident TEXT NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS provider_safety_events(
            id TEXT PRIMARY KEY, incident TEXT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def artifact(self, value):
        ident = digest(value)
        path = self.home / 'evidence' / ident[:2] / (ident + '.json.gz')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
            temporary.write_bytes(gzip.compress(packed(value).encode('utf-8'), mtime=0))
            os.replace(temporary, path)
        return ident

    def read_artifact(self, ident):
        if not isinstance(ident, str) or len(ident) != 64 or any(c not in '0123456789abcdef' for c in ident):
            raise ValueError('Invalid evidence identifier')
        path = self.home / 'evidence' / ident[:2] / (ident + '.json.gz')
        return json.loads(gzip.decompress(path.read_bytes()))

    def subject(self, project, subject):
        row = self.db.execute('SELECT * FROM subjects WHERE project=? AND id=?', (project, subject)).fetchone()
        if not row:
            raise ValueError('Subject does not belong to this project')
        return json.loads(row['payload'])

    def save_subject(self, project, kind, identity, payload):
        ident = digest((project, kind, identity))
        payload = dict(payload, id=ident, project=project, kind=kind)
        content_hash = digest(payload)
        with self.db:
            self.db.execute('''INSERT INTO subjects VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                payload=excluded.payload,content_hash=excluded.content_hash,updated=excluded.updated
                WHERE subjects.content_hash!=excluded.content_hash''',
                (ident, project, kind, identity, packed(payload), content_hash, now()))
        return dict(id=ident, contentHash=content_hash)

    def save_dataset(self, project, payload, rows):
        artifact = self.artifact(payload)
        ident = digest((project, artifact))
        normalized = []
        for item in rows:
            row = dict(item)
            for name in ('clicks', 'impressions'):
                row[name] = finite(row[name], integer=True)
            row['position'] = finite(row.get('position'), minimum=1, optional=True)
            rowkey = digest((row['url'], row.get('query'), row.get('country'), row.get('device')))
            normalized.append((ident, rowkey, row['url'], row.get('query'), row.get('country'), row.get('device'),
                               row['clicks'], row['impressions'], row['position'], packed(row)))
        if len({r[1] for r in normalized}) != len(normalized):
            raise ValueError('Duplicate row dimensions in a single dataset')
        with self.db:
            added = self.db.execute('INSERT OR IGNORE INTO datasets VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (ident, project, payload['provider'], payload['kind'], packed(payload['scope']), payload['start'],
                 payload['end'], payload['observedAt'], packed({k: v for k, v in payload.items() if k != 'rows'}), artifact, len(rows))).rowcount
            if added:
                self.db.executemany('INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?,?,?)', normalized)
        return dict(datasetId=ident, rows=len(rows), imported=bool(added))

    def enqueue(self, project, kind, request):
        ident = digest((project, kind, request))
        timestamp = now()
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                (ident, project, kind, packed(request), 'queued', '{}', '{}', None, timestamp, timestamp))
        return self.job(project, ident)

    def job(self, project, ident):
        row = self.db.execute('SELECT * FROM jobs WHERE project=? AND id=?', (project, ident)).fetchone()
        if not row:
            raise ValueError('Job does not belong to this project')
        result = dict(row)
        for name in ('request', 'progress', 'result'):
            result[name] = json.loads(result[name])
        return result

    def update_job(self, ident, state, progress, result=None, error=None):
        with self.db:
            self.db.execute('UPDATE jobs SET state=?,progress=?,result=?,error=?,updated=? WHERE id=?',
                            (state, packed(progress), packed(result or {}), error, now(), ident))
