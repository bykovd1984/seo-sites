"""Detached, single-writer provider worker. An OS lock survives neither exit nor crash."""
import contextlib
import os
import subprocess
import sys
import time
import datetime as dt

from .service import Service
from .store import now


@contextlib.contextmanager
def worker_lock(home, wait_seconds=0):
    path = home / 'worker.lock'
    stream = path.open('a+b')
    stream.seek(0, 2)
    if stream.tell() == 0:
        stream.write(b'0'); stream.flush()
    deadline, acquired = time.monotonic()+wait_seconds, False
    try:
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(.2)
        yield acquired
    finally:
        if acquired:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def start_worker(home):
    # MCP clients own (and may kill) their entire subprocess tree. A Windows
    # collector is started independently at sign-in, never by escaping that tree.
    service = Service(home)
    try:
        state = worker_status(service)
    finally:
        service.close()
    if state['available']:
        return state
    if os.name == 'nt':
        return dict(available=False, workerStarted=False, reason='Start the independent seo-research worker; queued work is durable.')
    environment = os.environ.copy()
    environment['PYTHONPATH'] = os.pathsep.join(filter(None, [
        os.path.dirname(os.path.dirname(__file__)), environment.get('PYTHONPATH')]))
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  close_fds=True, env=environment)
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    process = subprocess.Popen([sys.executable, '-m', 'research_hub', '--home', str(home), 'worker'], **kwargs)
    return dict(workerStarted=True, workerPid=process.pid)


def worker_status(service):
    row = service.store.db.execute('SELECT * FROM worker_state WHERE id=1').fetchone()
    with worker_lock(service.settings.home) as acquired:
        available = bool(row and not acquired)
    return dict(available=available, pid=row['pid'] if row else None, heartbeat=row['heartbeat'] if row else None)


def work(home, handlers=None, daemon=False):
    service = Service(home)
    try:
        with worker_lock(service.settings.home, wait_seconds=3) as locked:
            if not locked:
                return dict(existingWorker=True)
            if handlers is None:
                from .collectors import collect_google, collect_bing, collect_keywords
                handlers = dict(google=collect_google, bing=collect_bing, keywords=collect_keywords)
            # The global OS lock proves no earlier worker is still collecting.
            with service.store.db:
                service.store.db.execute("UPDATE jobs SET state='queued',error='worker_interrupted',updated=? WHERE state='running' AND kind='search'", (now(),))
                service.store.db.execute("UPDATE jobs SET state='blocked',error='interrupted_keyword_attempt_requires_resume',updated=? WHERE state='running' AND kind='keywords'", (now(),))
            completed, idle = 0, 0
            while True:
                with service.store.db:
                    service.store.db.execute('INSERT OR REPLACE INTO worker_state VALUES (1,?,?)',(os.getpid(),now()))
                row = service.store.db.execute("SELECT id,project FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
                if not row:
                    # Grace period lets concurrent enqueues reach this worker before it exits.
                    if not daemon and idle >= 4:
                        break
                    idle += 1; time.sleep(1 if daemon else .25); continue
                idle = 0
                job = service.store.job(row['project'], row['id'])
                service.store.update_job(job['id'], 'running', job['progress'], job['result'])
                try:
                    handler = handlers[job['request']['provider'] if job['kind']=='search' else 'keywords']
                    handler(service, job)
                except Exception as exc:
                    from .collectors import ReportUnavailable
                    # Never expose exception text that may contain credentials, URLs, or browser internals.
                    code = exc.reason if isinstance(exc, ReportUnavailable) else type(exc).__name__
                    latest = service.store.job(job['project'], job['id'])
                    service.store.update_job(job['id'], 'blocked' if isinstance(exc, (ReportUnavailable, ValueError)) else 'failed',
                                             latest['progress'], latest['result'], code)
                completed += 1
            return dict(processed=completed)
    finally:
        with service.store.db:
            service.store.db.execute('DELETE FROM worker_state WHERE pid=?',(os.getpid(),))
        service.close()
