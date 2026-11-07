"""Serialize real report-dispatch times across clients sharing one profile."""
import datetime as dt
import math
import sqlite3
import time
from pathlib import Path


class ReportPacer:
    def __init__(self, profile, delay=15, sleeper=time.sleep, clock=None):
        if not isinstance(delay,(int,float)) or not math.isfinite(delay) or delay < 10:
            raise ValueError('Report dispatch delay must be at least ten seconds')
        self.delay, self.sleeper = delay, sleeper
        self.clock = clock or (lambda:dt.datetime.now(dt.timezone.utc))
        self.db = sqlite3.connect(Path(profile).parent/'toolspd-dispatches.sqlite3',timeout=30)
        self.db.execute('''CREATE TABLE IF NOT EXISTS dispatches(
            id INTEGER PRIMARY KEY,attempt TEXT NOT NULL,dispatched TEXT NOT NULL)''')

    def dispatch(self, attempt):
        while True:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                stamp=self.clock().astimezone(dt.timezone.utc)
                last=self.db.execute('SELECT dispatched FROM dispatches ORDER BY id DESC LIMIT 1').fetchone()
                wait=max(0,(dt.datetime.fromisoformat(last[0])+dt.timedelta(seconds=self.delay)-stamp).total_seconds()) if last else 0
                if wait:
                    self.db.rollback()
                else:
                    self.db.execute('INSERT INTO dispatches(attempt,dispatched) VALUES (?,?)',(attempt,stamp.isoformat()))
                    self.db.commit()
                    return stamp.isoformat()
            except BaseException:
                self.db.rollback()
                raise
            # Never hold the writer lock while waiting; recheck after wake-up.
            self.sleeper(min(wait,30))

    def close(self):
        self.db.close()
