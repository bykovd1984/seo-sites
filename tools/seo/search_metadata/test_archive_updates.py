import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archive_catalog import file_hash, prepare_period, snapshot_history
from archive_updates import stage_history_update
from history import bind_scope, checkpoint, connect, ingest, ingest_page_metrics
from research import ROOT, init


class ArchiveUpdateTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'artifacts/search-metadata-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.site = 'https://manualsdump.com/'
        self.url = self.site + 'en/manuals/model/1/1'
        self.history = connect(self.root / 'history.sqlite3')
        self.delta = connect(self.root / 'delta.sqlite3')
        self.addCleanup(self.history.close)
        self.addCleanup(self.delta.close)
        for db in (self.history, self.delta):
            bind_scope(db, 'google', self.site)
            bind_scope(db, 'bing', self.site)
        self.metric(self.history, '2026-01-01', 11)
        self.query(self.history, '2026-01-01', 'old relevant phrase', 2)
        self.query(self.history, '2026-01-01', 'still useful old phrase', 1)
        checkpoint(self.history, 'google:web:' + self.site + ':2026-01-01', {'done': True})
        self.history.commit()
        self.parent, self.parent_sha = snapshot_history(self.root / 'history.sqlite3', self.root / 'base')
        self.output = self.root / 'update'

    def metric(self, db, day, position=12, payload=None):
        ingest_page_metrics(db, 'google', self.site, day, day, self.url, 3, 50, position, payload or {'fixture': 1})

    def query(self, db, day, phrase, clicks):
        ingest(db, [dict(engine='google', start=day, end=day, url=self.url, query=phrase,
                         clicks=clicks, impressions=20, position=12)], 'gsc-api-web-final')

    def delta_input(self):
        self.delta.commit()
        self.delta.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        path = self.root / 'delta.sqlite3'
        return path, file_hash(path)

    def run_update(self, **overrides):
        path, sha = self.delta_input()
        kwargs = dict(parent_path=self.parent, parent_sha256=self.parent_sha,
                      delta_path=path, delta_sha256=sha, directory=self.output,
                      start='2026-01-01', end='2026-11-07', site=self.site)
        kwargs.update(overrides)
        return stage_history_update(**kwargs)

    def add_tail(self):
        self.metric(self.delta, '2026-11-05', 3)
        self.query(self.delta, '2026-11-05', 'fresh phrase', 1)
        self.query(self.delta, '2026-01-01', 'old relevant phrase', 7)
        for day in ('2026-01-01', '2026-11-05'):
            checkpoint(self.delta, 'google:web:' + self.site + ':' + day, {'done': True})

    def test_full_history_retained_and_semantic_changes_applied_without_touching_inputs(self):
        self.add_tail()
        result = self.run_update()
        with contextlib.closing(sqlite3.connect(result['snapshot'])) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM api_page_metrics').fetchone()[0], 2)
            queries = dict(db.execute('SELECT query,clicks FROM observations'))
            self.assertEqual(queries, {'old relevant phrase': 7, 'still useful old phrase': 1, 'fresh phrase': 1})
            self.assertEqual(db.execute('SELECT min(start),max(end) FROM observations').fetchone(), ('2026-01-01', '2026-11-05'))
        self.assertEqual(file_hash(self.parent), self.parent_sha)
        self.assertEqual(result['changedPages'], [{'sourcePdfId': 1, 'page': 1}])
        self.assertEqual(result['statistics']['changedQueryRows'], 1)
        self.assertFalse(result['activeResearchDatabaseChanged'])
        self.assertEqual((result['modelCallsMade'], result['providerRequestsMade']), (0, 0))

    def test_payload_only_metric_change_and_identical_query_do_not_mark_page_changed(self):
        self.metric(self.delta, '2026-01-01', 11, {'new_capture_proof': True})
        self.query(self.delta, '2026-01-01', 'old relevant phrase', 2)
        checkpoint(self.delta, 'google:web:' + self.site + ':2026-01-01', {'done': True})
        result = self.run_update()
        self.assertEqual(result['changedPages'], [])
        self.assertEqual((result['statistics']['unchangedPageMetrics'], result['statistics']['unchangedQueryRows']), (1, 1))
        with contextlib.closing(sqlite3.connect(result['snapshot'])) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM api_page_metrics').fetchone()[0], 1)

    def test_bing_labels_and_earlier_queries_survive_without_fabricated_daily_checkpoints(self):
        ingest(self.history, [dict(engine='bing', start='2026-07-25', end='2026-07-25',
               url=self.url, query='earlier bing phrase', clicks=1, impressions=10, position=15)], 'bing-api-page-query')
        self.history.commit()
        self.parent, self.parent_sha = snapshot_history(self.root / 'history.sqlite3', self.root / 'base')
        ingest(self.delta, [dict(engine='bing', start='2026-10-30', end='2026-10-30',
               url=self.url, query='latest retained phrase', clicks=2, impressions=10, position=14)], 'bing-api-page-query')
        result = self.run_update()
        with contextlib.closing(sqlite3.connect(result['snapshot'])) as db:
            self.assertEqual(db.execute("SELECT start,end,query FROM observations WHERE engine='bing' ORDER BY start").fetchall(),
                             [('2026-07-25', '2026-07-25', 'earlier bing phrase'),
                              ('2026-10-30', '2026-10-30', 'latest retained phrase')])
            self.assertEqual(db.execute("SELECT count(*) FROM checkpoints WHERE key LIKE 'bing:%'").fetchone()[0], 0)

    def test_repeated_preparation_reuses_verified_artifact(self):
        self.add_tail()
        first = self.run_update()
        second = self.run_update()
        self.assertFalse(first['reused'])
        self.assertTrue(second['reused'])
        self.assertEqual(first['snapshotSha256'], second['snapshotSha256'])
        self.assertEqual(len(list(self.output.glob('*.sqlite3'))), 1)

    def test_incomplete_google_query_capture_is_rejected_without_publishing_snapshot(self):
        self.metric(self.delta, '2026-11-05')
        with self.assertRaisesRegex(ValueError, 'complete saved query checkpoint'):
            self.run_update()
        self.assertFalse(list(self.output.glob('*.sqlite3')))
        self.assertEqual(file_hash(self.parent), self.parent_sha)

    def test_wrong_property_out_of_period_and_wrong_page_identity_are_rejected(self):
        self.add_tail()
        with self.subTest('property'), self.assertRaisesRegex(ValueError, 'property binding'):
            self.run_update(site='https://another.example/')
        with self.subTest('date'), self.assertRaisesRegex(ValueError, 'outside the selected'):
            self.run_update(end='2026-11-04')
        self.delta.execute('UPDATE api_page_metrics SET pdf=999')
        with self.subTest('identity'), self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.run_update()

    def test_invalid_metrics_roll_back_temporary_clone_and_keep_original_frozen(self):
        self.add_tail()
        self.delta.execute('UPDATE observations SET clicks=-1')
        with self.assertRaisesRegex(ValueError, 'Invalid search metrics'):
            self.run_update()
        self.assertEqual(file_hash(self.parent), self.parent_sha)
        self.assertFalse(list(self.output.glob('*.sqlite3')))

    def test_mutated_input_or_published_snapshot_is_never_reused(self):
        self.add_tail()
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.run_update(parent_sha256='0' * 64)
        result = self.run_update()
        path = Path(result['snapshot'])
        data = path.read_bytes()
        path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.run_update()

    def test_changed_page_manifest_is_verified_before_reuse(self):
        self.add_tail()
        result = self.run_update()
        path = Path(result['manifest'])
        value = json.loads(path.read_text())
        value['changedPages'] = []
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'manifest integrity'):
            self.run_update()

    def test_uncheckpointed_wal_is_not_covered_by_a_main_file_hash(self):
        self.add_tail()
        Path(str(self.parent) + '-wal').write_bytes(b'not-checkpointed')
        with self.assertRaisesRegex(ValueError, 'WAL'):
            self.run_update()

    def test_cli_stages_snapshot_without_opening_active_database_for_writes(self):
        import app
        self.add_tail()
        delta, delta_sha = self.delta_input()
        db = connect(self.root / 'research.sqlite3')
        try:
            init(db)
            period = prepare_period(db, self.parent, self.root / 'catalog', '2026-01-01', '2026-11-07')
            db.commit()
            before = db.execute('SELECT count(*) FROM research_archive_pages').fetchone()[0]
            output = io.StringIO()
            argv = ['app', '--db', str(self.root / 'research.sqlite3'), 'archive', 'stage-update',
                    '--period', period['periodId'], '--history', str(delta), '--expected-delta-sha256', delta_sha,
                    '--directory', str(self.output)]
            with patch('sys.argv', argv), patch.object(app, 'connect') as writes, contextlib.redirect_stdout(output):
                app.main()
            writes.assert_not_called()
            self.assertFalse(json.loads(output.getvalue())['activeResearchDatabaseChanged'])
            self.assertEqual(db.execute('SELECT count(*) FROM research_archive_pages').fetchone()[0], before)
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
