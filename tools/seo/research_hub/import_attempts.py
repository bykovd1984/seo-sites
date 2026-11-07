"""Reconcile real legacy ToolsPD attempts into the shared daily budget."""
import datetime as dt
import sqlite3
from pathlib import Path

from .store import digest


def import_legacy_attempts(store, database, day):
    day = str(dt.date.fromisoformat(day))
    if day > str(dt.datetime.now(dt.timezone.utc).date()):
        raise ValueError('Attempt history cannot be imported from a future date')
    source = Path(database).resolve()
    if not source.is_file() or source == (store.home / 'research.sqlite3').resolve():
        raise ValueError('Select the separate legacy ToolsPD research database')
    db = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in db.execute('''SELECT id,job_id,started,status
            FROM semrush_ui_attempts WHERE substr(started,1,10)=? ORDER BY started LIMIT 1001''', (day,))]
    finally:
        db.close()
    if len(rows) > 1000:
        raise ValueError('Attempt history exceeds the bounded daily import')
    for row in rows:
        stamp = dt.datetime.fromisoformat(row['started'])
        if stamp.utcoffset() != dt.timedelta(0) or str(stamp.date()) != day:
            raise ValueError('Expected a UTC attempt timestamp for the selected date')
        if any(not isinstance(row[key], str) or not 1 <= len(row[key]) <= 255 for key in ('id','job_id','status')):
            raise ValueError('Invalid legacy attempt identity')
    proof = store.artifact(dict(kind='legacy_toolspd_attempt_history', database=str(source), day=day, rows=rows))
    inserted = 0
    with store.db:
        for row in rows:
            ident = digest(('legacy_toolspd', str(source), row['id']))
            inserted += store.db.execute('INSERT OR IGNORE INTO attempts VALUES (?,?,?,?)',
                (ident, 'external:' + proof + ':' + row['job_id'], row['started'], row['status'])).rowcount
    total = store.db.execute('SELECT COUNT(*) FROM attempts WHERE substr(started,1,10)=?', (day,)).fetchone()[0]
    return dict(imported=inserted, alreadyImported=len(rows)-inserted, day=day, totalAttempts=total,
                sourceEvidence=proof, apiUnitsSpent=0,
                limitation='One-time reconciliation of actual recorded attempts; future collection must use the shared ledger.')
