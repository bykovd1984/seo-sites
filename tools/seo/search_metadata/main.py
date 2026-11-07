"""Search-driven page metadata: collect -> queue -> export content -> generate."""
import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path

from history import connect, ingest, queue
from providers import Bing, Google


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path('artifacts/search-metadata/history.sqlite3'))
    parser.add_argument('--gsc-credentials', type=Path, help='Account-specific Google credential file; overrides the translation/service-account default')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('access')
    collect = sub.add_parser('collect')
    collect.add_argument('--engine', choices=['google', 'bing'], required=True)
    collect.add_argument('--site', default='https://manualsdump.com/')
    collect.add_argument('--start', type=dt.date.fromisoformat, required=True)
    collect.add_argument('--end', type=dt.date.fromisoformat, default=dt.datetime.now(dt.timezone.utc).date()-dt.timedelta(days=3))
    collect.add_argument('--max-days', type=int, default=14)
    collect.add_argument('--max-pages', type=int, default=50)
    imp = sub.add_parser('import-csv')
    imp.add_argument('--engine', choices=['google', 'bing'], required=True)
    imp.add_argument('--start', type=dt.date.fromisoformat, required=True)
    imp.add_argument('--end', type=dt.date.fromisoformat, required=True)
    imp.add_argument('--page-url', required=True, help='Exact page filter used when exporting the query report')
    imp.add_argument('file', type=Path)
    q = sub.add_parser('queue'); q.add_argument('--limit', type=int, default=100); q.add_argument('--output', type=Path, required=True)
    q.add_argument('--recheck', action='store_true', help='Include unchanged pages, for example after reconversion')
    q.add_argument('--include-impressions', action='store_true', help='Also queue pages without observed search clicks')
    gen = sub.add_parser('generate'); gen.add_argument('--contexts', type=Path, required=True)
    gen.add_argument('--output', type=Path, required=True)
    gen.add_argument('--queue', type=Path, help='Record requested pages whose content could not be exported; retry with queue --recheck')
    args = parser.parse_args()
    google_credentials = str(args.gsc_credentials) if args.gsc_credentials else os.getenv('MANUALSDUMP_GSC_CREDENTIALS',os.getenv('GOOGLE_APPLICATION_CREDENTIALS'))
    if args.command == 'access':
        for engine, factory in [('google', lambda: Google(google_credentials)), ('bing', lambda: Bing(os.getenv('BING_WEBMASTER_API_KEY')))]:
            try:
                sites = factory().sites()
                owned = [s for s in sites if 'manualsdump.com' in str(s.get('siteUrl', s.get('Url', '')))]
                print(json.dumps(dict(engine=engine, matching_properties=owned, accessible=bool(owned))))
            except (ValueError, RuntimeError) as exc:
                print(json.dumps(dict(engine=engine, accessible=False, error=str(exc))))
        return
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with connect(args.db) as db:
        if args.command == 'collect':
            if args.start > args.end or min(args.max_days, args.max_pages) < 1: raise ValueError('Invalid collection bounds')
            if args.engine == 'google':
                provider=Google(google_credentials)
                provider.collect_page_inventory(db,args.site,args.start,args.end,args.max_days)
                provider.collect(db,args.site,args.start,args.end,args.max_days)
                provider.collect_page_metrics(db,args.site,args.start,args.end,args.max_pages)
            else: Bing(os.getenv('BING_WEBMASTER_API_KEY')).collect(db,args.site,args.start,args.end,args.max_pages)
        elif args.command == 'import-csv':
            with args.file.open(encoding='utf-8-sig', newline='') as file: rows = list(csv.DictReader(file))
            normalized = []
            for row in rows:
                query = row.get('Keyword', row.get('Top queries', row.get('Популярные запросы')))
                if query is None: raise ValueError('Requires a page-filtered query CSV; page-only/global-query exports cannot be joined')
                normalized.append(dict(engine=args.engine, start=str(args.start), end=str(args.end), url=args.page_url, query=query,
                    clicks=row.get('Clicks', row.get('Клики')), impressions=row.get('Impressions', row.get('Показы')),
                    position=row.get('Avg. Position', row.get('Position', row.get('Позиция')))))
            print(json.dumps({'imported': ingest(db, normalized, str(args.file))}))
        elif args.command == 'queue':
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.limit < 1: raise ValueError('Queue limit must be positive')
            items = queue(db, args.limit, args.recheck, args.include_impressions)
            args.output.write_text(json.dumps(items, indent=2), encoding='utf-8')
            print(json.dumps({'queued_pages': len(items)}))
        elif args.command == 'generate':
            from generate import generate
            generate(db, args.contexts, args.output, json.loads(args.queue.read_text(encoding='utf-8')) if args.queue else None)


if __name__ == '__main__':
    try: main()
    except (ValueError, RuntimeError) as error: raise SystemExit(str(error))
