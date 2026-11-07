import datetime as dt
import tempfile
import unittest
from pathlib import Path

from research import ROOT
from toolspd_pacing import ReportPacer


class DispatchPacingTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'artifacts/search-metadata-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.profile=Path(self.temp.name)/'toolspd-profile'
        self.stamp=dt.datetime(2026,11,7,tzinfo=dt.timezone.utc)
        self.waits=[]

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.stamp+=dt.timedelta(seconds=seconds)

    def pacer(self, sleeper=None):
        value=ReportPacer(self.profile,15,sleeper or self.sleep,lambda:self.stamp)
        self.addCleanup(value.close)
        return value

    def test_cold_login_and_cross_job_gaps_use_real_dispatch_times(self):
        first,second=self.pacer(),self.pacer()
        self.stamp+=dt.timedelta(seconds=20) # login happened after reservation
        first.dispatch('job-a-seed-1')
        self.stamp+=dt.timedelta(seconds=11)
        first.dispatch('job-a-seed-2')
        self.stamp+=dt.timedelta(seconds=4)
        second.dispatch('job-b-seed-1')
        stamps=[dt.datetime.fromisoformat(r[0]) for r in first.db.execute('SELECT dispatched FROM dispatches ORDER BY id')]
        self.assertEqual([(b-a).total_seconds() for a,b in zip(stamps,stamps[1:])],[15,15])
        self.assertEqual(self.waits,[4,11])

    def test_new_client_retains_the_previous_dispatch_boundary(self):
        first=self.pacer();first.dispatch('failed-request')
        second=self.pacer();self.stamp+=dt.timedelta(seconds=1)
        second.dispatch('retry-request')
        self.assertEqual(self.waits,[14])
        self.assertEqual(second.db.execute('SELECT COUNT(*) FROM dispatches').fetchone()[0],2)

    def test_interrupted_wait_never_holds_writer_lock_or_marks_a_dispatch(self):
        first=self.pacer();first.dispatch('first')
        def interrupted(seconds): raise RuntimeError('fixture interrupted sleep')
        second=self.pacer(interrupted)
        with self.assertRaisesRegex(RuntimeError,'interrupted sleep'):
            second.dispatch('not-dispatched')
        self.stamp+=dt.timedelta(seconds=15)
        first.dispatch('after-interruption')
        self.assertEqual(first.db.execute('SELECT COUNT(*) FROM dispatches').fetchone()[0],2)


if __name__=='__main__':unittest.main()
