"""Persistent search evidence. Provider/date/URL/query remain distinguishable."""
import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from urllib.parse import urlsplit


def page_key(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or parts.hostname not in ('manualsdump.com', 'www.manualsdump.com') or parts.port not in (None, 80, 443):
        raise ValueError('Page URL is outside ManualsDump')
    if parts.username or parts.password:
        raise ValueError('Page URL has credentials')
    match = re.fullmatch(r'/(?:amp/)?en/manuals/(?:[^/]+/)*?(\d+)/(\d+)/?', parts.path)
    if not match or not (0 < int(match[1]) < 2**63 and 0 < int(match[2]) <= 65535):
        raise ValueError('Not a manual page URL')
    return int(match[1]), int(match[2])


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS observations (
          engine TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, url TEXT NOT NULL,
          pdf INTEGER NOT NULL, page INTEGER NOT NULL, query TEXT NOT NULL,
          clicks INTEGER NOT NULL, impressions INTEGER NOT NULL, position REAL, source TEXT NOT NULL,
          PRIMARY KEY(engine,start,end,url,query));
        CREATE INDEX IF NOT EXISTS page_evidence ON observations(pdf,page,end DESC);
        CREATE TABLE IF NOT EXISTS checkpoints (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS provider_scopes (engine TEXT PRIMARY KEY,site TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS api_page_metrics (id TEXT PRIMARY KEY,engine TEXT NOT NULL,site TEXT NOT NULL,
          start TEXT NOT NULL,end TEXT NOT NULL,url TEXT NOT NULL,pdf INTEGER NOT NULL,page INTEGER NOT NULL,
          clicks INTEGER NOT NULL,impressions INTEGER NOT NULL,position REAL,payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS api_page_metrics_lookup
          ON api_page_metrics(engine,site,start,end,url);
        CREATE TABLE IF NOT EXISTS proposals (pdf INTEGER, page INTEGER, generated_at TEXT, status TEXT,
          payload TEXT NOT NULL, evidence_rowid INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(pdf,page));
    ''')
    if 'evidence_rowid' not in {r['name'] for r in db.execute('PRAGMA table_info(proposals)')}:
        db.execute('ALTER TABLE proposals ADD COLUMN evidence_rowid INTEGER NOT NULL DEFAULT 0')
    return db


def bind_scope(db, engine, site):
    """Prevent one observation store from silently mixing API properties."""
    with db:
        current=db.execute('SELECT site FROM provider_scopes WHERE engine=?',(engine,)).fetchone()
        source={'google':'gsc-api-web-final','bing':'bing-api-page-query'}.get(engine)
        if not source: raise ValueError('Unknown API provider')
        if not current and db.execute('SELECT 1 FROM observations WHERE source=? LIMIT 1',(source,)).fetchone():
            raise ValueError('Existing API history has no property binding; use a new history database')
        db.execute('INSERT OR IGNORE INTO provider_scopes VALUES (?,?)',(engine,site))
        row=db.execute('SELECT site FROM provider_scopes WHERE engine=?',(engine,)).fetchone()
        if row['site']!=site: raise ValueError('Use a separate history database for each API property')


def ingest_page_metrics(db,engine,site,start,end,url,clicks,impressions,position,payload):
    pdf,page=page_key(url)
    first,last=dt.date.fromisoformat(start),dt.date.fromisoformat(end)
    if first>last or last>dt.datetime.now(dt.timezone.utc).date(): raise ValueError('Invalid page metric dates')
    if engine not in ('google','bing'): raise ValueError('Unknown page metric provider')
    scope=db.execute('SELECT site FROM provider_scopes WHERE engine=?',(engine,)).fetchone()
    if not scope or scope['site']!=site: raise ValueError('Page metric property mismatch')
    clicks,impressions=float(clicks),float(impressions)
    if not all(math.isfinite(v) and v>=0 and v.is_integer() for v in (clicks,impressions)):
        raise ValueError('Invalid aggregate page metrics')
    position=float(position) if position is not None else None
    if position is not None and (not math.isfinite(position) or position<1): position=None
    values=(engine,site,start,end,url,pdf,page,int(clicks),int(impressions),position,
            json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    ident=digest(json.dumps(values,ensure_ascii=False))
    db.execute('INSERT OR IGNORE INTO api_page_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(ident,*values))


def ingest(db, rows, source):
    values = []
    for row in rows:
        engine = row['engine']
        if engine not in ('google', 'bing'): raise ValueError('Unknown search engine')
        start, end = dt.date.fromisoformat(row['start']), dt.date.fromisoformat(row['end'])
        if start > end or end > dt.datetime.now(dt.timezone.utc).date(): raise ValueError('Invalid evidence dates')
        pdf, page = page_key(row['url'])
        query = unicodedata.normalize('NFKC', row['query']).strip()
        if not query or len(query) > 1000 or any(ord(c) < 32 for c in query): raise ValueError('Invalid query')
        clicks, impressions = float(row['clicks']), float(row['impressions'])
        position = row.get('position')
        if not all(math.isfinite(v) and v >= 0 and v.is_integer() for v in (clicks, impressions)):
            raise ValueError('Invalid search metrics')
        if position is not None and (not math.isfinite(float(position)) or float(position) < 0): raise ValueError('Invalid position')
        values.append((engine, str(start), str(end), row['url'], pdf, page, query, int(clicks), int(impressions), position, source))
    db.executemany('''INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(engine,start,end,url,query) DO UPDATE SET clicks=excluded.clicks,
        impressions=excluded.impressions,position=excluded.position,source=excluded.source,
        rowid=(SELECT COALESCE(MAX(rowid),0)+1 FROM observations)
        WHERE observations.clicks != excluded.clicks OR observations.impressions != excluded.impressions
          OR observations.position IS NOT excluded.position''', values)
    return len(values)


def evidence(db, pdf, page):
    rows = db.execute('SELECT * FROM observations WHERE pdf=? AND page=? ORDER BY end DESC,start DESC,engine,url,query', (pdf, page))
    windows = {}
    for row in rows:
        windows.setdefault((row['engine'], row['start'], row['end']), []).append(dict(row))
    accepted, skipped, used = [], [], {'google': [], 'bing': []}
    # Never add overlapping daily API results and aggregate CSV windows together.
    for (engine, start, end), items in windows.items():
        if any(start <= b and end >= a for a, b in used[engine]):
            skipped.append(dict(engine=engine, start=start, end=end)); continue
        used[engine].append((start, end)); accepted.extend(items)
    return accepted, skipped


def queue(db, limit, recheck=False, include_impressions=False):
    return [dict(sourcePdfId=r['pdf'], page=r['page'], lastSeen=r['last_seen'], clicks=r['clicks']) for r in db.execute(
        '''SELECT o.pdf,o.page,MAX(o.end) last_seen,SUM(o.clicks) clicks FROM observations o
           LEFT JOIN proposals p ON p.pdf=o.pdf AND p.page=o.page
           GROUP BY o.pdf,o.page HAVING (SUM(o.clicks)>0 OR ?) AND (? OR COALESCE(p.evidence_rowid,0) != MAX(o.rowid))
           ORDER BY last_seen DESC,clicks DESC,o.pdf,o.page LIMIT ?''', (include_impressions,recheck,limit))]


def watermark(db, pdf, page):
    # New or changed observations receive a monotonic rowid; identical retries do not requeue completed pages.
    row = db.execute('SELECT MAX(rowid) FROM observations WHERE pdf=? AND page=?', (pdf,page)).fetchone()
    return row[0] or 0


def checkpoint(db, key, payload=None):
    if payload is None:
        row = db.execute('SELECT payload FROM checkpoints WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None
    db.execute('INSERT OR REPLACE INTO checkpoints VALUES (?,?)', (key, json.dumps(payload)))


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()
