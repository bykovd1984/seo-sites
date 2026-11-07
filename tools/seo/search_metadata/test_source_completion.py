import base64
import json
import unittest

import test_research
from outcomes import page_outcome
from research import import_page,import_contexts
from ranking_policy import record
from semrush_workflow import init
from source_completion import finalize_export,unavailable_outcome


class SourceCompletionTests(unittest.TestCase):
    def setUp(self):
        fixture=test_research.ResearchTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.db,self.root=fixture.db,fixture.root
        init(self.db);import_page(self.db,fixture.manifest(),'test');self.db.commit()
        self.converted=self.root/'converted-001.jsonl';self.legacy=self.root/'legacy-001.jsonl'

    def pair(self,reason='file_missing'):
        self.converted.write_text('',encoding='utf-8')
        self.legacy.write_text(json.dumps(dict(type='legacy_source_unavailable',sourcePdfId=286733,page=69,reason=reason))+'\n',encoding='utf-8')
        import_contexts(self.db,self.converted);import_contexts(self.db,self.legacy);self.db.commit()

    def source(self):
        p=self.root/'recovered.jsonl'
        p.write_text(json.dumps(dict(type='seo_context',sourcePdfId=286733,page=69,readOnly=True,brand='HP',models=['M1005'],
            rawHtmlBase64=base64.b64encode(b'<p>Scanning a document with HP M1005.</p>').decode())),encoding='utf-8')
        import_contexts(self.db,p);self.db.commit()

    def test_paired_failure_has_a_bound_skip_and_replay_is_idempotent(self):
        self.pair();result=finalize_export(self.db,self.converted,self.legacy)
        self.assertEqual(result['recordedPages'],1)
        self.assertEqual((result['providerRequestsMade'],result['modelCallsMade']),(0,0))
        value=page_outcome(self.db,286733,69)
        self.assertEqual((value['state'],value['reason']),('skipped','source_context_unavailable'))
        self.assertEqual(value['sourceEvidence']['failureReason'],'file_missing')
        self.assertIn('original PDF',value['sourceEvidence']['limitation'])
        self.db.commit()
        self.assertEqual(finalize_export(self.db,self.converted,self.legacy)['alreadyRecorded'],1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM research_events WHERE event='paired_source_unavailable'").fetchone()[0],1)

    def test_limits_and_oversized_sources_stay_pending(self):
        for reason in ('batch_byte_limit','file_too_large','unknown_error'):
            self.pair(reason);value=finalize_export(self.db,self.converted,self.legacy)
            self.assertEqual(value['recordedPages'],0);self.assertEqual(value['pendingReasons'],{reason:1})
            self.assertEqual(page_outcome(self.db,286733,69)['state'],'pending')

    def test_importing_real_context_reopens_an_old_skip(self):
        self.pair();finalize_export(self.db,self.converted,self.legacy);self.source()
        self.assertIsNone(unavailable_outcome(self.db,286733,69))
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'ready_for_generation')

    def test_existing_context_is_never_replaced_with_a_skip(self):
        self.pair();self.source();result=finalize_export(self.db,self.converted,self.legacy)
        self.assertEqual((result['recordedPages'],result['sourcePresent']),(0,1))

    def test_changed_attempt_or_tampered_archived_proof_reopens_pending(self):
        self.pair();finalize_export(self.db,self.converted,self.legacy)
        row=self.db.execute('SELECT payload FROM research_source_export_failures').fetchone();proof=json.loads(row[0])
        path=self.db.execute('SELECT path FROM research_artifacts WHERE id=?',(proof['legacyArtifact'],)).fetchone()[0]
        from pathlib import Path
        Path(path).write_text('{}',encoding='utf-8')
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'source_export_proof_invalid')
        other=self.root/'new-attempt.jsonl';other.write_text(json.dumps(dict(type='legacy_source_unavailable',sourcePdfId=286733,page=69,reason='batch_byte_limit')),encoding='utf-8')
        import_contexts(self.db,other);self.db.commit()
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'source_export_attempt_changed')

    def test_single_missing_mismatched_or_overlapping_export_is_not_proof(self):
        self.pair()
        with self.assertRaises(ValueError):finalize_export(self.db,self.root/'absent.jsonl',self.legacy)
        other=self.root/'other';other.mkdir();p=other/'legacy-001.jsonl';p.write_bytes(self.legacy.read_bytes())
        with self.assertRaisesRegex(ValueError,'matching files'):finalize_export(self.db,self.converted,p)
        self.converted.write_text(json.dumps(dict(type='seo_context',sourcePdfId=286733,page=69,readOnly=True)),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'also be a legacy failure'):finalize_export(self.db,self.converted,self.legacy)
        self.assertIsNone(unavailable_outcome(self.db,286733,69))

    def test_malformed_or_unguarded_source_records_are_rejected(self):
        self.pair()
        for value in ([1],dict(type='seo_context',sourcePdfId=True,page=2,readOnly=True),
                      dict(type='seo_context',sourcePdfId=123,page=2,readOnly=False)):
            self.converted.write_text(json.dumps(value),encoding='utf-8')
            with self.assertRaises(ValueError):finalize_export(self.db,self.converted,self.legacy)

    def test_uncommitted_caller_changes_are_not_implicitly_committed(self):
        self.pair();self.db.execute("UPDATE research_pages SET stage='content_pending'")
        with self.assertRaisesRegex(ValueError,'Commit context imports'):finalize_export(self.db,self.converted,self.legacy)
        self.assertTrue(self.db.in_transaction)

    def test_period_outcome_is_updated_and_reconciliation_reopens_recovered_source(self):
        from archive_catalog import init_catalog,reconcile_period
        init_catalog(self.db);period='source-completion-period'
        self.db.execute('INSERT INTO research_archive_periods VALUES (?,?,?,?,?,?,?,?,?)',
            (period,'fixture-snapshot','a'*64,'2026-01-01','2026-11-07','https://manualsdump.com/','fixture-proof','2026-11-07','indexed'))
        self.db.execute('INSERT INTO research_archive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (period,286733,69,'https://manualsdump.com/en/manuals/hp-m1005/286733/69','2026-11-04',2,1,'pending','Exact page context is required',1,'{}','2026-11-07'))
        self.db.commit();self.pair();value=finalize_export(self.db,self.converted,self.legacy,period)
        self.assertEqual(value['updatedOutcomes'],1)
        row=self.db.execute('SELECT state,reason,detail FROM research_archive_pages WHERE period_id=?',(period,)).fetchone()
        self.assertEqual((row['state'],row['reason']),('skipped','source_context_unavailable'))
        self.assertEqual(json.loads(row['detail'])['processing']['sourceEvidence']['failureReason'],'file_missing')
        self.source();reconcile_period(self.db,period)
        row=self.db.execute('SELECT state,reason FROM research_archive_pages WHERE period_id=?',(period,)).fetchone()
        self.assertEqual((row['state'],row['reason']),('pending','ready_for_generation'))

    def test_ranking_protection_still_precedes_a_source_skip(self):
        self.pair();finalize_export(self.db,self.converted,self.legacy)
        record(self.db,'google','2026-11-06','2026-11-06','https://manualsdump.com/en/manuals/hp-m1005/286733/69',3,50,'fixture','page_report');self.db.commit()
        value=page_outcome(self.db,286733,69)
        self.assertEqual((value['state'],value['reason']),('excluded','protected_top_positions'))


if __name__=='__main__':unittest.main()
