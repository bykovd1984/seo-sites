"""Durable shared stop switch. Clearing it never enables collection or resumes jobs."""
import uuid

from .store import now

REASONS = ('owner_requested', 'owner_reported_parallel_access', 'concurrent_access_detected')


def status(store):
    row = store.db.execute("SELECT incident,reason,created FROM provider_safety WHERE provider='toolspd'").fetchone()
    return dict(paused=bool(row), **(dict(row) if row else {}))


def pause(store, reason):
    if reason not in REASONS:
        raise ValueError('Unknown provider pause reason')
    incident, stamp = uuid.uuid4().hex, now()
    with store.db:
        changed = store.db.execute('INSERT OR IGNORE INTO provider_safety VALUES (?,?,?,?)',
            ('toolspd', incident, reason, stamp)).rowcount
        if changed:
            store.db.execute('INSERT INTO provider_safety_events VALUES (?,?,?,?,?)',
                (uuid.uuid4().hex, incident, 'paused', reason, stamp))
    return status(store)


def require_available(store):
    if status(store)['paused']:
        from .collectors import ReportUnavailable
        raise ReportUnavailable('toolspd_safety_pause')


def clear(store, incident):
    # The caller also holds the machine-wide browser slot. An old acknowledgement
    # cannot clear a newer incident, and clearing never touches the attempt ledger.
    if not isinstance(incident, str) or len(incident) != 32 or any(c not in '0123456789abcdef' for c in incident):
        raise ValueError('Use the exact incident ID from provider_status')
    with store.db:
        changed = store.db.execute("DELETE FROM provider_safety WHERE provider='toolspd' AND incident=?", (incident,)).rowcount
        if not changed:
            raise ValueError('Provider incident changed or was already cleared; inspect provider_status')
        store.db.execute('INSERT INTO provider_safety_events VALUES (?,?,?,?,?)',
            (uuid.uuid4().hex, incident, 'cleared', 'owner_acknowledged_no_other_sessions', now()))
    return dict(paused=False, jobsResumed=False, collectionEnabledUnchanged=True)
