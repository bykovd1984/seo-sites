"""Real SDK client/server subprocess test; no provider credentials or network calls."""
import asyncio
import json
import site
import sys
import tempfile
import unittest
import subprocess
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SEO = ROOT/'tools/seo'
site.addsitedir(str(ROOT/'artifacts/seo-research/dependencies'))
sys.path.insert(0,str(ROOT/'artifacts/seo-research/dependencies'))
sys.path.insert(0,str(SEO))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from research_hub.cli import write_config


class MCPTest(unittest.TestCase):
    def test_two_clients_share_one_store(self):
        test_root = ROOT/'artifacts/seo-research/tests'
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            home = Path(directory)
            write_config(home, dict(schemaVersion=1, projects={
                'grammar': dict(hosts=['grammar.example'], languages=['en'])}, semrush=dict(enabled=False)))

            async def client_work(title):
                params = StdioServerParameters(command=sys.executable,
                    args=[str(SEO/'research_hub_app.py'), '--home', str(home), 'serve'])
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=15) as client:
                        await client.initialize()
                        response = await client.call_tool('save_subject', dict(
                            project='grammar', kind='topic', title=title, language='en'))
                        self.assertFalse(response.is_error)
                        data = response.structured_content or json.loads(response.content[0].text)
                        return data['id']

            async def run():
                return await asyncio.gather(client_work('Present simple'), client_work('Past simple'))

            ids = asyncio.run(asyncio.wait_for(run(), timeout=45))
            self.assertEqual(len(set(ids)), 2)
            from research_hub.service import Service
            service = Service(home)
            try:
                self.assertEqual({row['id'] for row in service.subjects('grammar')['items']}, set(ids))
            finally:
                service.close()

    def test_real_stdio_round_trip_and_detached_worker(self):
        test_root=ROOT/'artifacts/seo-research/tests'
        test_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            home=Path(directory)
            self.assertTrue(home.resolve().is_relative_to(test_root.resolve()))
            write_config(home,dict(schemaVersion=1,projects={'grammar':dict(hosts=['grammar.example'])},semrush=dict(enabled=False)))
            # This process is deliberately outside the MCP client's process tree.
            worker=subprocess.Popen([sys.executable,str(SEO/'research_hub_app.py'),'--home',str(home),'daemon'],
                                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            async def run():
                params=StdioServerParameters(command=sys.executable,args=[str(SEO/'research_hub_app.py'),'--home',str(home),'serve'])
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write,read_timeout_seconds=15) as client:
                        await client.initialize()
                        tools=await client.list_tools()
                        names={t.name for t in tools.tools}
                        self.assertTrue({'list_projects','provider_status','pause_provider','sync_search','research_keywords','prepare_research','save_decision'} <= names)
                        self.assertFalse(any('publish' in n for n in names))
                        async def call(name,args):
                            result=await client.call_tool(name,args)
                            self.assertFalse(result.is_error,str(result))
                            return result.structured_content or json.loads(result.content[0].text)
                        projects=await call('list_projects',{})
                        status=await call('provider_status',{})
                        self.assertEqual(status['provider'],'toolspd')
                        self.assertEqual(status['countedAttempts'],0)
                        self.assertEqual(projects['projects'][0]['id'],'grammar')
                        self.assertFalse(projects['semrushEnabled'])
                        subject=await call('save_subject',dict(project='grammar',kind='topic',title='Past tenses',language='en'))
                        bundle=await call('prepare_research',dict(project='grammar',subject_id=subject['id']))
                        self.assertEqual(bundle['subject']['kind'],'topic')
                        decision=await call('save_decision',dict(project='grammar',bundle_id=bundle['bundleId'],
                            action='new_content',rationale='Research fixture',proposal={'outline':['Examples']}))
                        self.assertFalse(decision['published'])
                        bad=await call('get_subject_text',dict(project='missing',subject_id=subject['id']))
                        self.assertFalse(bad['successful'])
                        job=await call('research_keywords',dict(project='grammar',subject_id=subject['id'],keywords=['past tense'],country='US',language='en'))
                        return job['id']
            try:
                job_id=asyncio.run(asyncio.wait_for(run(),timeout=45))
                # MCP subprocess has exited; the independent worker remains alive.
                self.assertIsNone(worker.poll())
                from research_hub.service import Service
                import time
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    service=Service(home)
                    try: job=service.jobs('grammar',job_id)
                    finally: service.close()
                    if job['state']=='blocked': break
                    time.sleep(.2)
                self.assertEqual(job['state'],'blocked')
                self.assertEqual(job['error'],'semrush_collection_paused_in_configuration')
            finally:
                if os.name == 'nt':
                    # A Windows venv launcher can own a second Python process.
                    subprocess.run(['taskkill','/PID',str(worker.pid),'/T','/F'],
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
                else:
                    worker.terminate()
                worker.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
