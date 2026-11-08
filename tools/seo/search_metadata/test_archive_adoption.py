import contextlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archive_adoption import adopt_history_update
from archive_catalog import (archive_queue, hydrate_pages, prepare_period,
                             processing_period, reconcile_period)
from archive_updates import stage_history_update
from history import bind_scope, checkpoint, connect, ingest, ingest_page_metrics
from model_stage import page_bundle, set_draft_policy
from ranking_policy import eligibility, record
from research import ROOT, import_generation, init, key
from research_hub.worker import worker_lock


class ArchiveAdoptionTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'artifacts/search-metadata-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = connect(self.root / 'research.sqlite3')
        self.history = connect(self.root / 'history.sqlite3')
        self.delta = connect(self.root / 'delta.sqlite3')
        for db in (self.db, self.history, self.delta):
            self.addCleanup(db.close)
        init(self.db)
        set_draft_policy(self.db, True)
        self.site = 'https://manualsdump.com/'
        for db in (self.history, self.delta):
            bind_scope(db, 'google', self.site)
        for pdf in (1, 2):
            for day in ('2026-02-01', '2026-11-04'):
                self.add(self.history, pdf, day, query=f'query {pdf} {day}')
        self.parent = self.index()
        hydrate_pages(self.db, self.parent['periodId'], self.root / 'original-batches', 100)
        self.db.commit()

    def url(self, pdf, amp=False):
        return self.site + ('amp/' if amp else '') + f'en/manuals/model/{pdf}/1'

    def add(self, db, pdf, day, position=12, query='phrase', metric=True, amp=False):
        url = self.url(pdf, amp)
        if metric:
            ingest_page_metrics(db, 'google', self.site, day, day, url, 2, 30, position, {'fixture': True})
        ingest(db, [dict(engine='google', start=day, end=day, url=url, query=query,
                        clicks=1, impressions=15, position=12)], 'gsc-api-web-final')
        checkpoint(db, 'google:web:' + self.site + ':' + day, {'done': True})

    def index(self):
        self.history.commit()
        return prepare_period(self.db, self.root / 'history.sqlite3', self.root / 'catalog',
                              '2026-01-01', '2026-11-07', self.site)

    def update(self, protected=True):
        self.add(self.delta, 2, '2026-11-05', position=3 if protected else 15, query='fresh second page')
        self.add(self.delta, 3, '2026-11-05', query='fresh new page')
        return self.freeze_delta()

    def freeze_delta(self):
        from archive_catalog import file_hash
        self.delta.commit()
        self.delta.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        path = self.root / 'delta.sqlite3'
        return stage_history_update(self.parent['snapshot'], self.parent['snapshotSha256'], path, file_hash(path),
                                    self.root / 'staged', '2026-01-01', '2026-11-07', self.site)

    def step(self, update, limit=100):
        return adopt_history_update(self.db, self.parent['periodId'], update['manifest'],
                                    self.root / 'delta.sqlite3', self.root / 'adopted', limit)

    def finish(self, update, limit=100):
        for _ in range(20):
            result = self.step(update, limit)
            if result['state'] == 'ready':
                return result
        self.fail('Bounded adoption did not finish')

    def test_inherits_only_unchanged_history_and_refreshes_protection_without_models(self):
        before = [tuple(row) for row in self.db.execute('SELECT * FROM research_windows WHERE pdf=1 ORDER BY id')]
        update = self.update()
        with patch('subprocess.run', side_effect=AssertionError('No model/provider may run')):
            result = self.finish(update, 1)
        new = result['new_period']
        self.assertEqual([tuple(row) for row in self.db.execute('SELECT * FROM research_windows WHERE pdf=1 ORDER BY id')], before)
        self.assertEqual(result['payload']['inheritedHistoryPages'], 1)
        self.assertFalse(eligibility(self.db, 2, 1)['eligible'])
        row = self.db.execute('SELECT state,reason FROM research_archive_pages WHERE period_id=? AND pdf=2', (new,)).fetchone()
        self.assertEqual(tuple(row), ('excluded', 'protected_top_positions'))
        self.assertEqual(self.db.execute('SELECT history_imported FROM research_archive_pages WHERE period_id=? AND pdf=3', (new,)).fetchone()[0], 1)
        self.assertEqual(result['modelCallsMade'], 0)
        with self.assertRaisesRegex(ValueError, 'non-superseded'):
            archive_queue(self.db, self.parent['periodId'])
        self.assertEqual(processing_period(self.db, new)['status'], 'indexed')
        self.assertTrue(self.step(update)['reused'])

    def test_changed_eligible_page_receives_full_earlier_history_not_only_delta(self):
        result = self.finish(self.update(protected=False))
        phrases = {row[0] for row in self.db.execute('''SELECT q.query FROM research_queries q JOIN research_windows w
            ON w.id=q.window_id WHERE w.pdf=2''')}
        self.assertTrue({'query 2 2026-02-01', 'query 2 2026-11-04', 'fresh second page'} <= phrases)
        self.assertEqual(self.db.execute('SELECT history_imported FROM research_archive_pages WHERE period_id=? AND pdf=2', (result['new_period'],)).fetchone()[0], 1)

    def test_cached_terminal_state_is_reassessed_against_actual_source(self):
        self.db.execute("UPDATE research_archive_pages SET state='validated_draft',reason='old_cached_claim' WHERE period_id=? AND pdf=1", (self.parent['periodId'],))
        self.db.commit()
        result = self.finish(self.update())
        row = self.db.execute('SELECT state,reason FROM research_archive_pages WHERE period_id=? AND pdf=1', (result['new_period'],)).fetchone()
        self.assertEqual(tuple(row), ('pending', 'Exact page context is required'))

    def test_interruption_blocks_dispatch_and_resumes_without_repeating_completed_checks(self):
        update = self.update()
        with patch('archive_adoption._sync_rankings', side_effect=RuntimeError('fixture interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'fixture interrupted'):
                self.step(update)
        with self.assertRaisesRegex(ValueError, 'Resume the pending archive adoption'):
            processing_period(self.db, self.parent['periodId'])
        result = self.finish(update, 1)
        self.assertEqual(result['payload']['inheritedHistoryPages'], 1)
        self.assertFalse(self.db.execute("SELECT 1 FROM research_settings WHERE name='archive_adoption_in_progress'").fetchone())

    def test_old_amp_top_position_is_materialized_and_stays_protected(self):
        self.add(self.history, 2, '2026-03-01', position=2, query='amp phrase', amp=True)
        self.parent = self.index()
        self.add(self.delta, 2, '2026-11-05', position=13, query='new regular phrase')
        result = self.finish(self.freeze_delta())
        self.assertFalse(eligibility(self.db, 2, 1)['eligible'])
        self.assertEqual(self.db.execute('SELECT state FROM research_archive_pages WHERE period_id=? AND pdf=2', (result['new_period'],)).fetchone()[0], 'excluded')

    def test_unchanged_api_baseline_does_not_overwrite_existing_csv_top_position(self):
        record(self.db, 'google', '2026-11-04', '2026-11-04', self.url(2), 2, 30, 'verified-csv-proof', 'page_inventory')
        self.db.commit()
        self.add(self.delta, 2, '2026-11-04', query='newly disclosed same-day query', metric=False)
        self.finish(self.freeze_delta())
        self.assertEqual(eligibility(self.db, 2, 1)['reason'], 'protected_top_positions')

    def test_query_only_new_scope_remains_unknown_and_excluded(self):
        self.add(self.delta, 5, '2026-11-05', query='query without a page average', metric=False)
        result = self.finish(self.freeze_delta())
        row = self.db.execute('SELECT state,reason,history_imported FROM research_archive_pages WHERE period_id=? AND pdf=5', (result['new_period'],)).fetchone()
        self.assertEqual(tuple(row), ('excluded', 'page_position_unknown', 0))

    def test_busy_generation_rejects_cli_adoption_before_database_is_opened(self):
        import app
        update = self.update()
        lock = self.root / 'artifacts/search-metadata/codex-generation'
        lock.mkdir(parents=True)
        argv = ['app', '--db', str(self.root / 'research.sqlite3'), 'archive', 'adopt-update',
                '--period', self.parent['periodId'], '--update-manifest', update['manifest'],
                '--history', str(self.root / 'delta.sqlite3'), '--directory', str(self.root / 'adopted')]
        with worker_lock(lock) as held, patch.object(app, 'ROOT', self.root), patch('sys.argv', argv), patch.object(app, 'connect') as connect_db:
            self.assertTrue(held)
            with self.assertRaisesRegex(ValueError, 'reconcile between generation batches'):
                app.main()
            connect_db.assert_not_called()

    def test_resigned_but_incomplete_affected_page_list_is_rejected_from_real_delta(self):
        update = self.update()
        path = Path(update['manifest'])
        data = json.loads(path.read_text())
        data['changedPages'] = []
        data['manifestSha256'] = key({k: v for k, v in data.items() if k != 'manifestSha256'})
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'actual history delta'):
            self.step(update)
        self.assertFalse(self.db.execute("SELECT 1 FROM research_settings WHERE name='archive_adoption_in_progress'").fetchone())

    def test_modified_merged_archive_cannot_drop_an_earlier_query(self):
        from archive_catalog import file_hash
        update = self.update()
        damaged = self.root / 'damaged.sqlite3'
        shutil.copyfile(update['snapshot'], damaged)
        with contextlib.closing(sqlite3.connect(damaged)) as db:
            with db:
                db.execute("DELETE FROM observations WHERE query='query 1 2026-02-01'")
        path = Path(update['manifest'])
        data = json.loads(path.read_text())
        data.update(snapshot=str(damaged), snapshotSha256=file_hash(damaged))
        data['manifestSha256'] = key({k: v for k, v in data.items() if k != 'manifestSha256'})
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unchangedBaseQueries'):
            self.step(update)

    def test_missing_bing_checkpoint_stays_pending_without_claiming_source_absence(self):
        bind_scope(self.history, 'bing', self.site)
        ingest_page_metrics(self.history, 'bing', self.site, '2026-10-30', '2026-10-30', self.url(2), 1, 10, 11, {'fixture': True})
        self.parent = self.index()
        result = self.finish(self.update(protected=False))
        row = self.db.execute('SELECT state,reason,history_imported FROM research_archive_pages WHERE period_id=? AND pdf=2', (result['new_period'],)).fetchone()
        self.assertEqual(tuple(row), ('pending', 'archive_query_checkpoint_incomplete', 0))
        self.assertTrue(any(item['state'] == 'held' for item in result['checks']))

    def test_all_dispatch_preparers_reject_an_interrupted_adoption(self):
        from archive_catalog import archive_context_queue
        from codex_groups import select_sources, claim_group
        from codex_drafts import prepare
        from draft_reviews import prepare_reviews
        from model_stage import queue
        update = self.update()
        with patch('archive_adoption._sync_rankings', side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):
                self.step(update)
        for action in (
                lambda: archive_context_queue(self.db, self.parent['periodId'], 10),
                lambda: select_sources(self.db, self.parent['periodId'], 16, 200000),
                lambda: claim_group(self.db, 'unused', {'periodId': self.parent['periodId']}, []),
                lambda: prepare(self.db, self.parent['periodId'], self.root / 'drafts', 10),
                lambda: prepare_reviews(self.db, self.parent['periodId'], self.root / 'reviews'),
                lambda: queue(self.db, self.root / 'model-queue')):
            with self.assertRaisesRegex(ValueError, 'Resume the pending archive adoption'):
                action()

    def test_checking_interruption_keeps_completed_page_checks_and_resumes(self):
        update = self.update()
        first = self.step(update, 1)
        self.assertEqual(first['state'], 'checking')
        done_before = self.db.execute("SELECT count(*) FROM research_archive_adoption_checks WHERE state='done'").fetchone()[0]
        with patch('outcomes.page_outcome', side_effect=RuntimeError('fixture assessment interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'assessment interrupted'):
                self.step(update, 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM research_archive_adoption_checks WHERE state='done'").fetchone()[0], done_before)
        self.assertEqual(self.finish(update, 1)['state'], 'ready')

    def test_explicit_hydration_cannot_bypass_normal_period_guards(self):
        with self.assertRaisesRegex(ValueError, 'active archive adoption'):
            hydrate_pages(self.db, self.parent['periodId'], self.root / 'bypass', 1, selected_pages=[(1, 1)])

    def test_latest_delta_metric_cannot_be_replaced_by_an_earlier_capture(self):
        from archive_catalog import file_hash
        self.add(self.delta, 2, '2026-11-05', position=3, query='fresh phrase')
        ingest_page_metrics(self.delta, 'google', self.site, '2026-11-05', '2026-11-05', self.url(2), 2, 30, 14, {'later': True})
        update = self.freeze_delta()
        damaged = self.root / 'reordered.sqlite3'
        shutil.copyfile(update['snapshot'], damaged)
        with contextlib.closing(sqlite3.connect(damaged)) as db:
            with db:
                rows = db.execute("SELECT rowid FROM api_page_metrics WHERE start='2026-11-05' ORDER BY rowid").fetchall()
                first, last = rows[0][0], rows[-1][0]
                db.execute('UPDATE api_page_metrics SET rowid=999999 WHERE rowid=?', (first,))
                db.execute('UPDATE api_page_metrics SET rowid=? WHERE rowid=?', (first, last))
                db.execute('UPDATE api_page_metrics SET rowid=? WHERE rowid=999999', (last,))
        path = Path(update['manifest'])
        data = json.loads(path.read_text())
        data.update(snapshot=str(damaged), snapshotSha256=file_hash(damaged))
        data['manifestSha256'] = key({k: v for k, v in data.items() if k != 'manifestSha256'})
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'delta page aggregate'):
            self.step(update)

    def test_verify_cli_is_read_only_even_while_generation_is_busy(self):
        import app
        import io
        update = self.update()
        lock = self.root / 'artifacts/search-metadata/codex-generation'
        lock.mkdir(parents=True)
        argv = ['app', '--db', str(self.root / 'research.sqlite3'), 'archive', 'verify-update',
                '--period', self.parent['periodId'], '--update-manifest', update['manifest'],
                '--history', str(self.root / 'delta.sqlite3')]
        output = io.StringIO()
        with worker_lock(lock) as held, patch.object(app, 'ROOT', self.root), patch('sys.argv', argv), patch.object(app, 'connect') as connect_db, contextlib.redirect_stdout(output):
            self.assertTrue(held)
            app.main()
            connect_db.assert_not_called()
        self.assertTrue(json.loads(output.getvalue())['verified'])
        self.assertFalse(self.db.execute("SELECT 1 FROM research_settings WHERE name='archive_adoption_in_progress'").fetchone())


class CachedDraftInheritanceTests(unittest.TestCase):
    def test_unchanged_generated_request_and_version_are_reused_exactly(self):
        import test_semrush_workflow
        fixture = test_semrush_workflow.SemrushTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root, db, site = fixture.root, fixture.db, 'https://manualsdump.com/'
        set_draft_policy(db, True)
        history = connect(root / 'history.sqlite3')
        delta = connect(root / 'delta.sqlite3')
        self.addCleanup(history.close)
        self.addCleanup(delta.close)
        for store in (history, delta):
            bind_scope(store, 'google', site)
        url = fixture.url
        ingest_page_metrics(history, 'google', site, '2026-11-04', '2026-11-04', url, 2, 50, 12, {'fixture': True})
        ingest(history, [dict(engine='google', start='2026-11-04', end='2026-11-04', url=url,
                            query='hp m1005 scanning', clicks=2, impressions=30, position=12)], 'gsc-api-web-final')
        checkpoint(history, 'google:web:' + site + ':2026-11-04', {'done': True})
        history.commit()
        parent = prepare_period(db, root / 'history.sqlite3', root / 'catalog', '2026-01-01', '2026-11-07')
        hydrate_pages(db, parent['periodId'], root / 'batches', 100)
        source = page_bundle(db, 286733, 69)
        path = root / 'response.json'
        path.write_text(json.dumps(dict(requestId=source['requestId'], model='gpt-6.1-sol', effort='medium',
            pageTitle='HP M1005 Scanning', h1Heading='HP M1005 Scanning', pageDescription='Scanning a document with HP M1005 at 300 dpi.',
            contentEvidence=['Scanning a document with HP M1005.'], selectedKeywords=['hp m1005 scanning'],
            requiresReview=False, rationale='Exact source and query', keywordDecisions=[])), encoding='utf-8')
        version = import_generation(db, path)['version']
        reconcile_period(db, parent['periodId'])
        other = site + 'en/manuals/model/3/1'
        ingest_page_metrics(delta, 'google', site, '2026-11-05', '2026-11-05', other, 1, 10, 12, {'fixture': True})
        ingest(delta, [dict(engine='google', start='2026-11-05', end='2026-11-05', url=other,
                          query='other manual phrase', clicks=1, impressions=10, position=12)], 'gsc-api-web-final')
        checkpoint(delta, 'google:web:' + site + ':2026-11-05', {'done': True})
        delta.commit()
        delta.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        from archive_catalog import file_hash
        update = stage_history_update(parent['snapshot'], parent['snapshotSha256'], root / 'delta.sqlite3', file_hash(root / 'delta.sqlite3'),
                                      root / 'staged', '2026-01-01', '2026-11-07')
        result = adopt_history_update(db, parent['periodId'], update['manifest'], root / 'delta.sqlite3', root / 'adopted', 100)
        self.assertEqual(result['state'], 'ready')
        self.assertEqual(page_bundle(db, 286733, 69)['requestId'], source['requestId'])
        processing = json.loads(db.execute('SELECT detail FROM research_archive_pages WHERE period_id=? AND pdf=286733', (result['new_period'],)).fetchone()[0])['processing']
        self.assertEqual(processing['versionId'], version)
        self.assertEqual(db.execute('SELECT count(*) FROM research_metadata_versions').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
