"""Stable repository entry point for the installed shared runtime."""
import json
import os
from pathlib import Path
import sys


def main():
    repo = Path(__file__).resolve().parents[2]
    runtime = Path(os.environ.get('SEO_RESEARCH_RUNTIME', repo/'.local/seo-research'))
    manifest = runtime/'runtime.json'
    if not manifest.is_file():
        raise SystemExit('Install the runtime first. See tools/seo/README.md.')
    config = json.loads(manifest.read_text(encoding='utf-8'))
    command = config['command']
    if not command or not Path(command[0]).is_file():
        raise SystemExit('The runtime Python executable is missing. Reinstall the runtime.')
    os.execv(command[0], command+sys.argv[1:])


if __name__=='__main__':
    main()
