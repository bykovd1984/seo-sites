import base64
import copy
import json
import unittest
from pathlib import Path

import test_research as fixtures
from archive_catalog import init_catalog
from identity_completion import record_identity_skip,identity_outcome
from model_stage import set_draft_policy
from outcomes import page_outcome
from ranking_policy import record
from research import import_page,import_contexts
from semrush_workflow import init


class IdentityCompletionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ResearchTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.db,self.root=self.fixture.db,self.fixture.root
        init(self.db)
        self.manifest=self.fixture.manifest(identityReviewRequired=True,semrush=[],content=dict(
            source='guarded source fixture',type='KERR SCOTTY DB-102',evidence='Source identity differs from catalogue HP'))
        import_page(self.db,self.manifest,'test')
        self.context(69,'KERR SCOTTY Model DB-102 wood furnace specifications.')
        self.context(1,'SCOTTY WOOD FURNACE Model DB-102 owner manual.')
        set_draft_policy(self.db,True);self.db.commit()
        self.decision=dict(schemaVersion=1,kind='catalog_source_identity_conflict',sourcePdfId=286733,page=69,
            catalogBrand='HP',sourceBrand='KERR',sourceModel='DB-102',
            rationale='Guarded target and cover identify the same furnace model, while the catalogue brand differs.',
            target=self.binding(69,'KERR SCOTTY Model DB-102'),cover=self.binding(1,'SCOTTY WOOD FURNACE Model DB-102'))

    def context(self,page,text,foreign=False):
        pdf=999 if foreign else 286733
        item=dict(type='seo_context',sourcePdfId=pdf,page=page,readOnly=True,manualId=10,pageCount=100,
            brand='HP',models=['DB-102'],rawHtmlBase64=base64.b64encode(('<p>'+text+'</p>').encode()).decode())
        path=self.root/f'context-{pdf}-{page}-{len(text)}.jsonl';path.write_text(json.dumps(item)+'\n',encoding='utf-8')
        import_contexts(self.db,path);self.db.commit()

    def binding(self,page,quote,pdf=286733):
        row=self.db.execute('SELECT * FROM research_content WHERE pdf=? AND page=? ORDER BY rowid DESC LIMIT 1',(pdf,page)).fetchone()
        return dict(page=page,contentSha256=row['raw_sha256'],sourceArtifact=row['source_artifact'],quote=quote)

    def decision_file(self,value=None):
        path=self.root/'identity-decision.json';path.write_text(json.dumps(value or self.decision),encoding='utf-8');return path

    def test_quarantine_alone_stays_pending_then_bound_record_is_idempotent(self):
        self.assertEqual(page_outcome(self.db,286733,69)['state'],'pending')
        self.db.commit()
        result=record_identity_skip(self.db,self.decision_file())
        self.assertEqual((result['recorded'],result['modelCallsMade'],result['providerRequestsMade']),(1,0,0))
        outcome=page_outcome(self.db,286733,69)
        self.assertEqual((outcome['state'],outcome['reason']),('skipped','catalog_source_identity_conflict'))
        self.assertFalse(outcome['identityEvidence']['quarantineCleared'])
        self.assertEqual(self.db.execute('SELECT stage FROM research_pages WHERE pdf=286733 AND page=69').fetchone()[0],'identity_review')
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_metadata_versions').fetchone()[0],0)
        self.db.commit()
        self.assertEqual(record_identity_skip(self.db,self.decision_file())['alreadyRecorded'],1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM research_events WHERE event='source_identity_conflict_recorded'").fetchone()[0],1)

    def test_changed_target_source_reopens_pending(self):
        record_identity_skip(self.db,self.decision_file())
        self.context(69,'KERR SCOTTY Model DB-102 wood furnace revised specifications.')
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'identity_conflict_proof_changed')

    def test_changed_cover_source_reopens_pending(self):
        record_identity_skip(self.db,self.decision_file())
        self.context(1,'SCOTTY WOOD FURNACE Model DB-102 revised owner manual.')
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'identity_conflict_proof_changed')

    def test_quotes_identity_labels_and_foreign_source_bindings_are_rejected(self):
        self.context(1,'SCOTTY WOOD FURNACE Model DB-102 owner manual.',foreign=True)
        values=[]
        for field,value in [('sourceBrand','HP'),('sourceModel','OTHER'),('catalogBrand','OTHER')]:
            item=copy.deepcopy(self.decision);item[field]=value;values.append(item)
        item=copy.deepcopy(self.decision);item['target']['quote']='Unrelated identity text';values.append(item)
        item=copy.deepcopy(self.decision);item['cover']=self.binding(1,'SCOTTY WOOD FURNACE Model DB-102',pdf=999);values.append(item)
        item=copy.deepcopy(self.decision);item['target']['page']=68;values.append(item)
        for item in values:
            with self.subTest(item=item),self.assertRaises(ValueError):record_identity_skip(self.db,self.decision_file(item))
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_identity_skips').fetchone()[0],0)

    def test_availability_only_and_resolved_quarantines_cannot_be_skipped(self):
        value=json.loads(self.manifest.read_text());value.update(sourcePdfId=None,content=dict(source='unavailable',evidence='Source unavailable'))
        self.manifest.write_text(json.dumps(value));import_page(self.db,self.manifest,'test');self.db.commit()
        with self.assertRaisesRegex(ValueError,'availability-only'):record_identity_skip(self.db,self.decision_file())
        value.update(sourcePdfId=286733,identityReviewRequired=False);self.manifest.write_text(json.dumps(value));import_page(self.db,self.manifest,'test');self.db.commit()
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'ready_for_generation')
        with self.assertRaises(ValueError):record_identity_skip(self.db,self.decision_file())

    def test_corrupted_decision_proof_and_protected_ranking_do_not_stay_skipped(self):
        result=record_identity_skip(self.db,self.decision_file())
        payload=json.loads(self.db.execute('SELECT payload FROM research_identity_skips').fetchone()[0])
        path=Path(self.db.execute('SELECT path FROM research_artifacts WHERE id=?',(payload['decisionArtifact'],)).fetchone()[0]);path.write_text('{}')
        self.assertEqual(identity_outcome(self.db,286733,69)['reason'],'identity_conflict_proof_changed')
        record(self.db,'google','2026-11-04','2026-11-04',self.fixture.url,3,10,'proof','fixture');self.db.commit()
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'protected_top_positions')
        with self.assertRaisesRegex(ValueError,'Ranking protection'):record_identity_skip(self.db,self.decision_file())

    def test_explicit_resolution_ignores_the_old_skip_and_caller_transaction_is_preserved(self):
        record_identity_skip(self.db,self.decision_file())
        self.db.execute("UPDATE research_pages SET stage='identity_review'")
        with self.assertRaisesRegex(ValueError,'Commit earlier'):record_identity_skip(self.db,self.decision_file())
        self.assertTrue(self.db.in_transaction);self.db.rollback()
        value=json.loads(self.manifest.read_text());value['identityReviewRequired']=False;self.manifest.write_text(json.dumps(value));import_page(self.db,self.manifest,'test');self.db.commit()
        self.assertEqual(page_outcome(self.db,286733,69)['reason'],'ready_for_generation')

    def test_period_updates_the_current_outcome_without_changing_the_quarantine(self):
        init_catalog(self.db);period='identity-conflict-fixture'
        self.db.execute('INSERT INTO research_archive_periods VALUES (?,?,?,?,?,?,?,?,?)',
            (period,'snapshot','a'*64,'2026-01-01','2026-11-07','https://manualsdump.com/','proof','2026-11-07','indexed'))
        self.db.execute('INSERT INTO research_archive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (period,286733,69,self.fixture.url,'2026-11-04',3,1,'pending','Source identity requires review',1,'{}','2026-11-07'));self.db.commit()
        record_identity_skip(self.db,self.decision_file(),period)
        row=self.db.execute('SELECT state,reason,detail FROM research_archive_pages').fetchone()
        self.assertEqual((row['state'],row['reason']),('skipped','catalog_source_identity_conflict'))
        self.assertIn('identityEvidence',json.loads(row['detail'])['processing'])


if __name__=='__main__':unittest.main()
