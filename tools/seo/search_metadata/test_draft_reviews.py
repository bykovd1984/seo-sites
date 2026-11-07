import base64
import json
import unittest
from pathlib import Path

import test_codex_groups
from codex_groups import run_group,load_group,claim_group
from draft_reviews import init_reviews,prepare_reviews,finish_review,manual_evidence,prepare_review_repair
from generate import atomic_json
from model_stage import page_bundle
from outcomes import page_outcome
from research import import_contexts


class DraftReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_codex_groups.GroupDraftTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.db,self.root,self.period=self.fixture.db,self.fixture.root,self.fixture.period
        init_reviews(self.db)
        ident=self.fixture.group()
        def flag(raw):
            raw['results'][0].update(requiresReview=True,rationale='The catalog and source page applicability require review with the manual cover.')
        result=run_group(self.db,ident,'codex',self.fixture.executor(flag))
        self.request=result['pages'][0]['requestId'];self.previous=result['pages'][0]['version']

    def cover(self,page,text='HP LaserJet M1005 User Guide'):
        value=dict(type='seo_context',sourcePdfId=286733,page=page,pageCount=100,brand='HP',models=['M1005'],readOnly=True,
            rawHtmlBase64=base64.b64encode(('<p>'+text+'</p>').encode()).decode())
        path=self.root/('cover-'+str(page)+'.jsonl');atomic_json(path,value);import_contexts(self.db,path);self.db.commit()

    def ready(self):
        self.cover(1);self.cover(2,'HP M1005 contents and scanning chapter')
        prepared=prepare_reviews(self.db,self.period,self.root/'reviews',8)
        self.assertEqual(prepared['pages'],1);return prepared['preparedGroup']

    def unresolved(self,raw):
        raw['results'][0].update(requiresReview=True,rationale='The original target page and manual identity remain ambiguous after checking the saved cover pages.')

    def test_preparation_waits_for_manual_pages_without_changing_generated_request(self):
        result=prepare_reviews(self.db,self.period,self.root/'reviews',8)
        self.assertIsNone(result['preparedGroup']);self.assertIn('Supplemental source pages are still pending',result['held'])
        self.cover(1)
        self.assertIsNone(prepare_reviews(self.db,self.period,self.root/'reviews',8)['preparedGroup'])
        self.cover(2)
        self.assertIsNotNone(prepare_reviews(self.db,self.period,self.root/'reviews',8)['preparedGroup'])
        self.assertEqual(self.db.execute('SELECT status FROM research_requests WHERE id=?',(self.request,)).fetchone()[0],'generated')

    def test_second_pass_can_validate_a_revision_and_preserves_original(self):
        ident=self.ready();result=run_group(self.db,ident,'codex',self.fixture.executor())
        reviewed=finish_review(self.db,ident,result)
        self.assertEqual(reviewed['reviewOutcomes'][0]['state'],'validated_draft')
        self.assertEqual(page_outcome(self.db,286733,69)['state'],'validated_draft')
        self.assertEqual(self.db.execute('SELECT status FROM research_metadata_versions WHERE id=?',(self.previous,)).fetchone()[0],'needs_review')
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_review_skips').fetchone()[0],0)

    def test_unresolved_review_records_a_specific_source_bound_skip(self):
        ident=self.ready();result=run_group(self.db,ident,'codex',self.fixture.executor(self.unresolved))
        reviewed=finish_review(self.db,ident,result)
        self.assertEqual(reviewed['reviewOutcomes'][0]['state'],'skipped')
        outcome=page_outcome(self.db,286733,69)
        self.assertEqual((outcome['state'],outcome['reason']),('skipped','unresolved_after_source_review'))
        self.assertEqual(outcome['reviewEvidence']['previousVersionId'],self.previous)
        self.assertIn('checking the saved cover pages',outcome['reviewEvidence']['rationale'])
        self.assertEqual(len(outcome['reviewEvidence']['manualEvidence']),2)
        self.assertEqual(self.db.execute('SELECT state FROM research_archive_pages WHERE pdf=286733').fetchone()[0],'skipped')

    def test_a_skip_cannot_be_recorded_before_a_completed_model_review(self):
        ident=self.ready()
        fake=dict(state='processed',pages=[dict(requestId=self.request,status='needs_review',version=self.previous)])
        with self.assertRaisesRegex(ValueError,'not completed a model call'):finish_review(self.db,ident,fake)
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_review_skips').fetchone()[0],0)

    def test_source_change_before_dispatch_does_not_call_the_model(self):
        ident=self.ready();self.cover(1,'A corrected cover with additional identity evidence')
        with self.assertRaisesRegex(ValueError,'Supplemental source changed'):
            run_group(self.db,ident,'codex',lambda *a:self.fail('No stale review call'))
        self.assertEqual(self.db.execute('SELECT status FROM research_requests WHERE id=?',(self.request,)).fetchone()[0],'generated')

    def test_changed_cover_reactivates_a_previously_skipped_page(self):
        ident=self.ready();result=run_group(self.db,ident,'codex',self.fixture.executor(self.unresolved));finish_review(self.db,ident,result)
        self.cover(1,'Corrected HP M1005 cover')
        self.assertEqual(page_outcome(self.db,286733,69)['state'],'pending')
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'supplemental_source_changed')

    def test_approved_review_is_reactivated_if_its_cover_evidence_changes(self):
        ident=self.ready();result=run_group(self.db,ident,'codex',self.fixture.executor());finish_review(self.db,ident,result)
        self.cover(1,'New corrected identity information')
        outcome=page_outcome(self.db,286733,69)
        self.assertEqual((outcome['state'],outcome['reason']),('pending','supplemental_source_changed'))
        from codex_groups import update_outcome
        with self.db:update_outcome(self.db,self.period,286733,69)
        self.assertIsNotNone(prepare_reviews(self.db,self.period,self.root/'reviews',8)['preparedGroup'])

    def test_cover_change_during_the_call_prevents_import(self):
        ident=self.ready();execute=self.fixture.executor()
        def changed(folder,command,environment):
            result=execute(folder,command,environment);self.cover(1,'Changed while review was in progress');return result
        result=run_group(self.db,ident,'codex',changed)
        self.assertEqual(result['pages'][0]['status'],'held')
        self.assertIn('Supplemental source changed',result['pages'][0]['reason'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_metadata_versions WHERE request_id=?',(self.request,)).fetchone()[0],1)
        finish_review(self.db,ident,result)
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_review_skips').fetchone()[0],0)

    def test_cover_only_numeric_facts_cannot_be_borrowed_by_target_metadata(self):
        ident=self.ready()
        def unsupported(raw):raw['results'][0]['pageTitle']='HP M3600 scanning'
        result=run_group(self.db,ident,'codex',self.fixture.executor(unsupported))
        self.assertEqual(result['pages'][0]['status'],'held')
        self.assertIn('Unsupported numeric claim',result['pages'][0]['reason'])

    def test_review_repair_preserves_cover_provenance_and_rejects_normal_repair_route(self):
        ident=self.ready()
        def badquote(raw):raw['results'][0]['contentEvidence']=['A quote not found in the target page']
        result=run_group(self.db,ident,'codex',self.fixture.executor(badquote))
        self.assertEqual(result['pages'][0]['status'],'held')
        from codex_groups import repair_sources,repair_queue
        planned=repair_queue(self.db,self.period)
        self.assertEqual([(p['groupId'],p['kind']) for p in planned['repairs']],[(ident,'review')])
        with self.assertRaisesRegex(ValueError,'source-review repair'):repair_sources(self.db,ident)
        child=prepare_review_repair(self.db,ident,self.root/'reviews')
        manifest=load_group(self.db,child)[2]
        self.assertEqual(manifest['reviewVersions'][self.request],self.previous)
        self.assertEqual(len(manifest['reviewEvidence'][self.request]),2)
        fixed=run_group(self.db,child,'codex',self.fixture.executor())
        self.assertEqual(finish_review(self.db,child,fixed)['reviewOutcomes'][0]['state'],'validated_draft')

    def test_changed_target_reactivates_the_page_instead_of_reusing_a_skip(self):
        ident=self.ready();result=run_group(self.db,ident,'codex',self.fixture.executor(self.unresolved));finish_review(self.db,ident,result)
        value=dict(type='seo_context',sourcePdfId=286733,page=69,brand='HP',models=['M1005'],readOnly=True,
            rawHtmlBase64=base64.b64encode(b'<p>New scanning instructions for HP M1005.</p>').decode())
        path=self.root/'target-update.jsonl';atomic_json(path,value);import_contexts(self.db,path);self.db.commit()
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'ready_for_generation')

    def test_forged_member_version_cannot_record_a_skip(self):
        ident=self.ready();result=run_group(self.db,ident,'codex',self.fixture.executor(self.unresolved))
        result['pages'][0]['version']=self.previous
        with self.assertRaisesRegex(ValueError,'actual group member'):finish_review(self.db,ident,result)
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_review_skips').fetchone()[0],0)

    def test_definitive_source_unavailability_is_evidence_but_transient_limits_are_not(self):
        path=self.root/'unavailable.jsonl'
        for reason,expected in [('batch_byte_limit',False),('file_missing',True)]:
            records=[dict(type='legacy_source_unavailable',sourcePdfId=286733,page=p,reason=reason) for p in (1,2)]
            path.write_text('\n'.join(json.dumps(r) for r in records)+'\n',encoding='utf-8');import_contexts(self.db,path);self.db.commit()
            result=prepare_reviews(self.db,self.period,self.root/'reviews',8)
            self.assertEqual(bool(result['preparedGroup']),expected)

    def test_replay_imports_without_a_second_call_or_duplicate_skip(self):
        ident=self.ready();result=run_group(self.db,ident,'codex',self.fixture.executor(self.unresolved));finish_review(self.db,ident,result)
        again=run_group(self.db,ident,'codex',lambda *a:self.fail('No second review call'))
        finish_review(self.db,ident,again)
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_review_skips').fetchone()[0],1)

    def test_uncertain_review_reservation_never_becomes_a_skip(self):
        ident=self.ready();_,_,manifest,sources=load_group(self.db,ident);claim_group(self.db,ident,manifest,sources)
        result=run_group(self.db,ident,'codex',lambda *a:self.fail('Uncertain review call must not repeat'))
        finish_review(self.db,ident,result)
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_review_skips').fetchone()[0],0)
        self.assertEqual(page_outcome(self.db,286733,69)['state'],'pending')


if __name__=='__main__':unittest.main()
