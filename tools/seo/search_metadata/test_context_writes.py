import base64,json,sqlite3,threading,time,unittest
from unittest.mock import patch
from generate import atomic_json
from research import import_context_file
import test_semrush_workflow


class ContextWriteTests(unittest.TestCase):
    def setUp(self):
        fixture=test_semrush_workflow.SemrushTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.db,self.root=fixture.db,fixture.root
        self.path=self.root/'retry-context.jsonl'
        self.source=dict(type='seo_context',sourcePdfId=286733,page=69,brand='HP',models=['M1005'],readOnly=True,
            rawHtmlBase64=base64.b64encode(b'<p>Scanning a document with HP M1005. Resolution 300 dpi.</p>').decode())
        atomic_json(self.path,self.source)

    def test_real_busy_writer_retries_saved_context_without_duplicates(self):
        self.db.execute('PRAGMA busy_timeout=1')
        locked=threading.Event();errors=[]
        def writer():
            try:
                other=sqlite3.connect(self.root/'research.sqlite3')
                try:
                    other.execute('BEGIN IMMEDIATE');locked.set();time.sleep(.12);other.commit()
                finally:other.close()
            except Exception as exc:errors.append(exc);locked.set()
        thread=threading.Thread(target=writer);thread.start();self.addCleanup(thread.join,2)
        self.assertTrue(locked.wait(1));self.assertEqual(errors,[])
        before=self.db.execute('SELECT count(*) FROM research_content').fetchone()[0]
        self.assertEqual(import_context_file(self.db,self.path,retry_delay=.05),1)
        thread.join(1);self.assertFalse(thread.is_alive())
        self.assertEqual(import_context_file(self.db,self.path),1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_content').fetchone()[0],before)
        self.assertFalse(self.db.in_transaction)

    def test_invalid_file_rolls_back_and_is_not_retried(self):
        before=self.db.execute('SELECT count(*) FROM research_content').fetchone()[0]
        source=dict(self.source,rawHtmlBase64=base64.b64encode(b'<p>Changed source.</p>').decode())
        self.path.write_text(json.dumps(source)+'\n{invalid\n',encoding='utf-8')
        with patch('research.time.sleep') as sleep:
            with self.assertRaises(json.JSONDecodeError):import_context_file(self.db,self.path)
        sleep.assert_not_called()
        self.assertEqual(self.db.execute('SELECT count(*) FROM research_content').fetchone()[0],before)
        self.assertFalse(self.db.in_transaction)

    def test_non_lock_database_error_is_not_retried(self):
        with patch('research.import_contexts',side_effect=sqlite3.OperationalError('no such table: fixture_missing')) as importer,patch('research.time.sleep') as sleep:
            with self.assertRaisesRegex(sqlite3.OperationalError,'no such table'):import_context_file(self.db,self.path)
        self.assertEqual(importer.call_count,1);sleep.assert_not_called()

if __name__=='__main__':unittest.main()
