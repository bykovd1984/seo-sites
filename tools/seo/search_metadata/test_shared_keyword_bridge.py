import contextlib
import hashlib
import io
import json
import sqlite3
import sys
import unittest
from unittest.mock import patch

import test_toolspd as fixtures
import shared_keyword_bridge as bridge
from archive_catalog import init_catalog
from ranking_policy import record
from research import key, now, packed
from semrush_workflow import context
from model_stage import page_bundle
from toolspd import parse_snapshot, url


class SharedKeywordBridgeTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ToolsPdTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.db, self.root = fixture.db, fixture.root
        self.pdf, self.page, self.period = 286733, 69, 'a' * 64
        init_catalog(self.db)
        self.db.execute('INSERT INTO research_archive_periods VALUES (?,?,?,?,?,?,?,?,?)',
            (self.period, 'unused', 'b' * 64, '2009-01-01', '2026-11-07', 'https://manualsdump.com/', 'unused', now(), 'indexed'))
        self.db.execute('INSERT INTO research_settings VALUES (?,?,?)', ('archive_active_period', packed(self.period), now()))
        self.target_url = 'https://manualsdump.com/en/manuals/hp-m1005/286733/69'
        self.db.execute('INSERT INTO research_archive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (self.period, self.pdf, self.page, self.target_url, '2026-11-03', 3, 1, 'validated_draft', 'metadata_draft_saved', 1, '{}', now()))
        self.hub_path = self.root / 'hub.sqlite3'
        self.hub = sqlite3.connect(self.hub_path)
        self.hub.row_factory = sqlite3.Row
        self.addCleanup(self.hub.close)
        self.hub.executescript('''CREATE TABLE jobs(id,project,kind,state,request);
            CREATE TABLE subjects(id,project,payload);
            CREATE TABLE keyword_reports(id,artifact,request,result);
            CREATE TABLE keyword_links(project,subject,report,seed);''')
        sha, text = context(self.db, self.pdf, self.page)
        self.request = fixture.request
        self.raw = fixture.snapshot()
        self.hub_request = dict(subject='subject', keywords=[self.request['keyword']], country='US', language='en', limit=100, requestedMonth=self.request['month'])
        self.hub.execute('INSERT INTO jobs VALUES (?,?,?,?,?)', ('job', 'manualsdump', 'keywords', 'done', packed(self.hub_request)))
        self.hub.execute('INSERT INTO subjects VALUES (?,?,?)', ('subject', 'manualsdump', packed(dict(url=self.target_url, text=text))))
        self.plan = dict(schemaVersion=1, project='manualsdump', publicationAllowed=False, sourcePdfId=self.pdf,
            page=self.page, url=self.target_url, contentSha256=sha, sourceTextSha256=hashlib.sha256(text.encode()).hexdigest(),
            sharedJobId='job', subjectId='subject', reports=[], queryProvenance=dict(provider='google', date='2026-11-03', keyword=self.request['keyword'], role='reported_query'),
            contentSeedProvenance=dict(keyword=self.request['keyword'], verbatimSource='Scanning a document with HP M1005.', role='source_supported_heading_seed'))
        self.set_snapshot(self.raw)
        self.db.commit()
        self.hub.commit()

    def seal(self):
        self.plan['manifestSha256'] = key({k: v for k, v in self.plan.items() if k != 'manifestSha256'})
        self.plan_path = self.root / 'page-import-plan.json'
        self.plan_path.write_text(packed(self.plan), encoding='utf-8')

    def set_snapshot(self, raw):
        path = self.root / 'snapshot.json'
        path.write_text(packed(raw), encoding='utf-8')
        evidence = key(raw)
        parsed = parse_snapshot(self.request, raw)
        self.hub.execute('DELETE FROM keyword_reports')
        self.hub.execute('DELETE FROM keyword_links')
        self.hub.execute('INSERT INTO keyword_reports VALUES (?,?,?,?)', ('report', evidence, packed(dict(self.hub_request, **self.request)), packed(parsed)))
        self.hub.execute('INSERT INTO keyword_links VALUES (?,?,?,?)', ('manualsdump', 'subject', 'report', self.request['keyword']))
        self.plan['reports'] = [dict(seed=self.request['keyword'], request=self.request, hubReportId='report', hubEvidenceId=evidence,
            snapshotPath=str(path), snapshotSha256=hashlib.sha256(path.read_bytes()).hexdigest(), origin='https://sktiman.toolspd.com', candidates=len(parsed))]
        self.hub.commit()
        self.seal()

    def run_import(self):
        return bridge.import_plan(self.db, self.hub, self.period, self.plan)

    def done(self):
        return self.db.execute("SELECT count(*) FROM semrush_jobs WHERE status='done'").fetchone()[0]

    def second_report(self):
        seed = 'hp m1005 resolution'
        request = dict(self.request, keyword=seed)
        raw = dict(self.raw, sourceUrl=url(request), heading='Keyword Magic Tool: ' + seed,
            rows=[], tableText='Nothing found')
        path = self.root / 'second-snapshot.json'
        path.write_text(packed(raw), encoding='utf-8')
        self.hub_request['keywords'].append(seed)
        self.hub.execute('UPDATE jobs SET request=?', (packed(self.hub_request),))
        parsed = parse_snapshot(request, raw)
        self.hub.execute('INSERT INTO keyword_reports VALUES (?,?,?,?)', ('report2', key(raw), packed(dict(self.hub_request, **request)), packed(parsed)))
        self.hub.execute('INSERT INTO keyword_links VALUES (?,?,?,?)', ('manualsdump', 'subject', 'report2', seed))
        self.hub.commit()
        self.plan['contentSeedProvenance'] = dict(keyword=seed, verbatimSource='Resolution 300 dpi.', role='source_supported_heading_seed')
        self.plan['reports'].append(dict(seed=seed, request=request, hubReportId='report2', hubEvidenceId=key(raw),
            snapshotPath=str(path), snapshotSha256=hashlib.sha256(path.read_bytes()).hexdigest(), origin='https://sktiman.toolspd.com', candidates=len(parsed)))
        self.seal()
        return path

    def test_import_invalidates_old_draft_and_is_idempotent(self):
        self.assertEqual(self.run_import()['state'], 'imported')
        row = self.db.execute('SELECT result FROM semrush_jobs').fetchone()
        self.assertIsNone(json.loads(row['result'])[0]['kd'])
        self.assertEqual(self.db.execute('SELECT state FROM research_archive_pages').fetchone()[0], 'pending')
        self.assertEqual(self.run_import()['state'], 'already_imported')
        self.assertEqual(self.done(), 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM research_events WHERE event='shared_semrush_imported'").fetchone()[0], 1)

    def test_snapshot_corruption_is_rejected_before_writes(self):
        (self.root / 'snapshot.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.run_import()
        self.assertEqual(self.done(), 0)
        self.assertEqual(self.db.execute('SELECT state FROM research_archive_pages').fetchone()[0], 'validated_draft')

    def test_second_report_is_checked_before_first_report_commit(self):
        self.second_report().write_text('{}')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.run_import()
        self.assertEqual(self.done(), 0)
        self.assertEqual(self.db.execute('SELECT state FROM research_archive_pages').fetchone()[0], 'validated_draft')

    def test_every_candidate_reaches_sol_bundle_including_no_results(self):
        self.second_report()
        self.assertEqual(self.run_import()['reports'], 2)
        bundle = page_bundle(self.db, self.pdf, self.page)
        self.assertEqual(len(bundle['semrushCandidates']), 2)
        metrics = [c['metrics'] for c in bundle['semrushCandidates']]
        self.assertTrue(any(c['volume'] == 1200 and c['kd'] is None for c in metrics))
        self.assertTrue(any(c['status'] == 'nothing found' and c['volume'] is None for c in metrics))

    def test_initial_single_indexed_period_can_be_inferred(self):
        self.db.execute("DELETE FROM research_settings WHERE name='archive_active_period'")
        self.assertEqual(self.run_import()['state'], 'imported')

    def test_multiple_initial_periods_require_explicit_pointer(self):
        self.db.execute("DELETE FROM research_settings WHERE name='archive_active_period'")
        self.db.execute("INSERT INTO research_archive_periods SELECT ?,snapshot_path,snapshot_sha256,start,end,site,manifest_artifact,created,status FROM research_archive_periods", ('c' * 64,))
        with self.assertRaisesRegex(ValueError, 'current indexed'):
            self.run_import()

    def test_stale_content_is_held(self):
        self.plan['contentSha256'] = 'changed'
        self.seal()
        self.assertEqual(self.run_import()['reason'], 'source_content_changed')
        self.assertEqual(self.done(), 0)

    def test_protected_alias_prevents_import(self):
        record(self.db, 'bing', '2026-11-04', '2026-11-04', self.target_url.replace('/en/', '/amp/en/'), 3, 50, 'proof', 'test')
        self.assertEqual(self.run_import()['reason'], 'ranking_protection')
        self.assertEqual(self.done(), 0)

    def test_pending_adoption_and_wrong_active_period_stop(self):
        self.db.execute('INSERT INTO research_settings VALUES (?,?,?)', ('archive_adoption_in_progress', packed('update'), now()))
        with self.assertRaisesRegex(ValueError, 'adoption'):
            self.run_import()
        self.db.execute("DELETE FROM research_settings WHERE name='archive_adoption_in_progress'")
        self.db.execute("UPDATE research_settings SET value=? WHERE name='archive_active_period'", (packed('different'),))
        with self.assertRaisesRegex(ValueError, 'current indexed'):
            self.run_import()

    def test_missing_query_history_stays_held(self):
        self.plan['queryProvenance']['date'] = '2026-11-06'
        self.seal()
        self.assertEqual(self.run_import()['reason'], 'query_history_not_adopted')
        self.assertEqual(self.done(), 0)

    def test_shared_job_must_be_done(self):
        self.hub.execute("UPDATE jobs SET state='blocked'")
        with self.assertRaisesRegex(ValueError, 'not completed'):
            self.run_import()
        self.assertEqual(self.done(), 0)

    def test_scope_and_subject_must_match(self):
        self.hub.execute("UPDATE subjects SET payload=?", (packed(dict(url=self.target_url, text='wrong page')),))
        with self.assertRaisesRegex(ValueError, 'exact page text'):
            self.run_import()

    def test_explicit_no_results_keeps_metrics_unknown(self):
        self.set_snapshot(dict(self.raw, rows=[], headers=[], tableText='Nothing found'))
        self.assertEqual(self.run_import()['state'], 'imported')
        item = json.loads(self.db.execute('SELECT result FROM semrush_jobs').fetchone()[0])[0]
        self.assertEqual(item['status'], 'nothing found')
        self.assertIsNone(item['volume'])
        self.assertIsNone(item['kd'])

    def test_uncertain_existing_legacy_job_is_not_overwritten(self):
        self.db.execute("UPDATE semrush_jobs SET status='ui_reserved'")
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.run_import()
        self.assertEqual(self.done(), 0)

    def test_interrupted_local_import_resumes_without_provider_replay(self):
        original = bridge.ingest_snapshot
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('Interrupted after local report commit')
        with patch.object(bridge, 'ingest_snapshot', side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, 'Interrupted'):
                self.run_import()
        self.assertEqual(self.db.execute('SELECT state FROM research_archive_pages').fetchone()[0], 'pending')
        self.assertEqual(self.done(), 1)
        self.assertEqual(self.run_import()['state'], 'imported')
        self.assertEqual(self.done(), 1)

    def test_busy_cli_does_not_open_or_create_target_database(self):
        missing = self.root / 'never-created.sqlite3'
        argv = ['bridge', '--db', str(missing), '--period', self.period, '--plans', str(self.root)]
        with patch.object(sys, 'argv', argv), patch('research_hub.worker.worker_lock', return_value=contextlib.nullcontext(False)):
            with self.assertRaisesRegex(ValueError, 'Another generation'):
                bridge.main()
        self.assertFalse(missing.exists())

    def test_readonly_preflight_does_not_take_generation_lock(self):
        argv = ['bridge', '--db', str(self.root / 'research.sqlite3'), '--hub-db', str(self.hub_path), '--period', self.period, '--plans', str(self.root), '--dry-run']
        with patch.object(sys, 'argv', argv), patch('research_hub.worker.worker_lock') as lock, contextlib.redirect_stdout(io.StringIO()) as output:
            bridge.main()
        lock.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['results'][0]['state'], 'ready')
        self.assertEqual(self.done(), 0)


if __name__ == '__main__':
    unittest.main()
