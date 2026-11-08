import contextlib
import io
import json
import unittest
from unittest.mock import patch

import app
import test_codex_drafts
from research_hub.worker import worker_lock


class ReconciliationLockTests(unittest.TestCase):
    def setUp(self):
        fixture=test_codex_drafts.CodexDraftTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.db,self.root,self.period=fixture.db,fixture.root,fixture.period
        self.database=next(r['file'] for r in self.db.execute('PRAGMA database_list') if r['name']=='main')
        self.lock=self.root/'artifacts/search-metadata/codex-generation';self.lock.mkdir(parents=True)

    def test_busy_generation_rejects_both_refresh_commands_before_db_open(self):
        commands=[['archive','reconcile','--period',self.period],['outcomes','--start','2026-01-01','--end','2026-11-07']]
        with worker_lock(self.lock) as held:
            self.assertTrue(held)
            for command in commands:
                with self.subTest(command=command),patch.object(app,'ROOT',self.root),patch('sys.argv',['app','--db',self.database]+command),patch.object(app,'connect') as connect:
                    with self.assertRaisesRegex(ValueError,'reconcile between generation batches'):app.main()
                    connect.assert_not_called()

    def test_idle_reconciliation_completes_and_releases_the_slot(self):
        output=io.StringIO()
        with patch.object(app,'ROOT',self.root),patch('sys.argv',['app','--db',self.database,'archive','reconcile','--period',self.period]),contextlib.redirect_stdout(output):
            app.main()
        self.assertEqual(json.loads(output.getvalue())['assessedImportedPages'],1)
        with worker_lock(self.lock) as acquired:self.assertTrue(acquired)


if __name__=='__main__':unittest.main()
