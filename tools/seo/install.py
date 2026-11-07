"""Build a wheel and install the local SEO research runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import venv


def main():
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=repo/'.local/seo-research')
    parser.add_argument('--home', type=Path, required=True, help='Shared private research data directory')
    parser.add_argument('--browser', action='store_true', help='Install the ToolsPD browser dependency')
    args = parser.parse_args()
    runtime, home = args.runtime.resolve(), args.home.resolve()
    if not (home/'config.private.json').is_file():
        raise SystemExit('Initialize the data directory with research_hub_app.py --home DIRECTORY init first.')
    runtime.mkdir(parents=True, exist_ok=True)
    wheels = runtime/'wheels'
    wheels.mkdir(exist_ok=True)
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                    '--wheel-dir', str(wheels), str(Path(__file__).resolve().parent)], check=True)
    wheel = max(wheels.glob('seo_research-*.whl'), key=lambda path: path.stat().st_mtime_ns)
    release = hashlib.sha256(wheel.read_bytes()).hexdigest()[:16]
    environment = runtime/'releases'/release/'venv'
    if not (environment/'pyvenv.cfg').is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
    executable = environment/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    subprocess.run([str(executable), '-m', 'pip', 'install', '--upgrade', str(wheel)], check=True)
    if args.browser:
        subprocess.run([str(executable), '-m', 'pip', 'install', 'playwright==1.64.1'], check=True)
    subprocess.run([str(executable), '-m', 'research_hub', '--home', str(home), 'check-mcp'], check=True)
    manifest = dict(release=release, python=str(executable), home=str(home), wheel=str(wheel),
                    command=[str(executable), '-m', 'research_hub', '--home', str(home)])
    temporary = runtime/'runtime.json.tmp'
    temporary.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    temporary.replace(runtime/'runtime.json')
    print(json.dumps(dict(installed=True, runtime=str(runtime), home=str(home),
                         mcpCommand=manifest['command']+['serve']), indent=2))


if __name__=='__main__':
    main()
