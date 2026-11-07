"""Read-only MCP handshake and tool discovery against a configured local store."""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check(home):
    environment = {'PYTHONPATH': os.pathsep.join(filter(None, [
        str(Path(__file__).resolve().parents[1]), os.environ.get('PYTHONPATH')]))}
    params = StdioServerParameters(command=sys.executable,
        args=['-m', 'research_hub', '--home', str(home), 'serve'], env=environment)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=15) as client:
            initialized = await client.initialize()
            catalog = await client.list_tools()
            result = await client.call_tool('list_projects', {})
            if result.is_error:
                raise ValueError('MCP project read failed')
            data = result.structured_content or json.loads(result.content[0].text)
            return dict(connected=True, tools=sorted(t.name for t in catalog.tools),
                        projects=[p['id'] for p in data['projects']], worker=data['worker'],
                        semrushEnabled=data['semrushEnabled'], providerRequestsMade=0)


def run(home):
    return asyncio.run(asyncio.wait_for(check(home), timeout=30))
