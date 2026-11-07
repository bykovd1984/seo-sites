import os,subprocess,sys,unittest,uuid
from pathlib import Path
from toolspd_access import ToolsPDAccess,ToolsPDBusy


class ProviderAccessTests(unittest.TestCase):
    def setUp(self):
        self.name='Global\\SeoResearch.ToolsPD.Test.'+uuid.uuid4().hex

    def child(self):
        code='''import os,sys
from toolspd_access import ToolsPDAccess,ToolsPDBusy
try:
    slot=ToolsPDAccess(sys.argv[1]).acquire()
except ToolsPDBusy:
    print('busy',flush=True)
    raise SystemExit(0)
print('exclusive',flush=True)
os._exit(0)
'''
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parent))
        return subprocess.run([sys.executable,'-c',code,self.name],env=env,text=True,capture_output=True,timeout=20,check=True).stdout.strip()

    def test_second_client_is_denied_and_release_is_reusable(self):
        with ToolsPDAccess(self.name):
            with self.assertRaises(ToolsPDBusy): ToolsPDAccess(self.name).acquire()
            self.assertEqual(self.child(),'busy')
        with ToolsPDAccess(self.name): pass

    def test_process_crash_releases_the_slot(self):
        self.assertEqual(self.child(),'exclusive')
        with ToolsPDAccess(self.name): pass

    def test_exception_releases_the_slot(self):
        with self.assertRaises(RuntimeError):
            with ToolsPDAccess(self.name): raise RuntimeError('fixture')
        with ToolsPDAccess(self.name): pass

if __name__=='__main__':unittest.main()
