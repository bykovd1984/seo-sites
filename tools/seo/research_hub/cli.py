"""Console entry points for the same operations exposed through MCP."""
import argparse
import json
import os
import sys
from pathlib import Path

from .settings import DEFAULT_HOME, Settings, identifier, web_url
from .service import Service
from .store import packed


OPERATIONS = ('projects', 'put_subject', 'subjects', 'subject_text', 'import_search', 'search_rows',
              'datasets', 'queue_search', 'queue_keywords', 'jobs', 'resume_job', 'keywords', 'bundle',
              'save_decision', 'decisions', 'import_keywords')


def write_config(home, value):
    home.mkdir(parents=True, exist_ok=True)
    path = home / 'config.private.json'
    temporary = home / 'config.private.json.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=DEFAULT_HOME)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init', help='Create empty local settings; never reads or copies credentials')
    project = commands.add_parser('project-add', help='Configure one project locally; credentials are file references only')
    project.add_argument('id'); project.add_argument('--name'); project.add_argument('--hosts', nargs='+', required=True)
    project.add_argument('--languages', nargs='+', default=[]); project.add_argument('--minimum-position', type=float)
    project.add_argument('--google-property'); project.add_argument('--google-account'); project.add_argument('--google-credentials', type=Path)
    project.add_argument('--bing-property'); project.add_argument('--bing-credentials', type=Path)
    project.add_argument('--enable-providers', action='store_true')
    call = commands.add_parser('call', help='Run a shared service operation with JSON from --input or stdin')
    call.add_argument('operation', choices=OPERATIONS); call.add_argument('--input', type=Path)
    call.add_argument('--queue-only', action='store_true', help='Persist a job without launching the detached worker')
    commands.add_parser('worker', help='Process queued work until drained; preserves partial/blocked jobs')
    commands.add_parser('daemon', help='Independent persistent worker; install at user sign-in on Windows')
    commands.add_parser('serve', help='Run the local stdio MCP interface')
    commands.add_parser('check-mcp', help='Read-only SDK handshake and project listing; no provider requests')
    commands.add_parser('toolspd-login', help='Interactive owner login in an isolated browser, no credentials in chat')
    args = parser.parse_args(argv)
    home = args.home.resolve()
    if args.command == 'init':
        if (home/'config.private.json').exists():
            raise ValueError('Configuration exists; refusing to overwrite it')
        write_config(home, dict(schemaVersion=1, projects={}, semrush=dict(enabled=False, origin='https://sktiman.toolspd.com',
            dailyLimit=20, delaySeconds=15, channel='msedge')))
        result = dict(initialized=True, liveCollectionStarted=False)
    elif args.command == 'project-add':
        settings = Settings(home); identifier(args.id)
        if args.id in settings.projects:
            raise ValueError('Project exists; edit and review its local configuration explicitly')
        value = dict(name=args.name or args.id, hosts=args.hosts, languages=args.languages, minimumPosition=args.minimum_position)
        for engine in ('google', 'bing'):
            prop = getattr(args, engine+'_property')
            if prop:
                path = getattr(args, engine+'_credentials')
                value[engine] = dict(property=prop, credentialFile=str(path.resolve()) if path else None, enabled=args.enable_providers)
                if engine == 'google':
                    value[engine]['account'] = args.google_account
        # Validate in memory before replacing the on-disk settings.
        settings.projects[args.id] = value
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(dir=home) as temporary:
            write_config(Path(temporary), settings.data)
            Settings(temporary)
        write_config(home, settings.data)
        result = dict(project=args.id, configured=True, liveAccessVerified=False)
    elif args.command in ('worker','daemon'):
        from .worker import work
        result = work(home,daemon=args.command=='daemon')
    elif args.command == 'serve':
        from .mcp_server import create_server
        create_server(home).run(transport='stdio')
        return
    elif args.command == 'check-mcp':
        from .check_connection import run
        result = run(home)
    elif args.command == 'toolspd-login':
        from .collectors import ToolsPDBrowser
        from .worker import worker_lock
        settings = Settings(home)
        with worker_lock(home) as locked:
            if not locked:
                raise ValueError('Worker is active; retry login after it finishes')
            browser = ToolsPDBrowser(settings)
            try:
                browser.open(headless=False)
                browser.page.goto('https://app.toolspd.com/member', wait_until='domcontentloaded')
                print('Sign in and open Access Semrush 1 in the isolated browser. Never send passwords or codes to chat.', file=sys.stderr)
                input('Press Enter after signing in: ')
            finally:
                browser.close()
        result = dict(loginWindowClosed=True, liveReportVerified=False,
                      collectionEnabled=bool(settings.data.get('semrush', {}).get('enabled')))
    else:
        data = args.input.read_text(encoding='utf-8-sig') if args.input else '{}' if args.operation=='projects' else sys.stdin.read()
        kwargs = json.loads(data) if data.strip() else {}
        if not isinstance(kwargs, dict) or len(data)>12000000:
            raise ValueError('Expected a bounded JSON object')
        # A supplied file cannot impersonate our verified API adapter.
        if args.operation == 'import_search' and 'trusted' in kwargs:
            raise ValueError('Trusted provenance is reserved for the provider adapter')
        service = Service(home)
        try:
            result = getattr(service, args.operation)(**kwargs)
            if args.operation in ('queue_search', 'queue_keywords', 'resume_job') and result['state']=='queued' and not args.queue_only:
                from .worker import start_worker
                result['worker'] = start_worker(home)
        finally:
            service.close()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False))


def entrypoint():
    try:
        main()
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(str(exc) if isinstance(exc, ValueError) else 'Invalid input structure') from None
    except OSError as exc:
        raise SystemExit('Local operation failed: '+type(exc).__name__) from None


if __name__ == '__main__':
    entrypoint()
