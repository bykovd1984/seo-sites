"""ManualsDump console: import a date range, prepare Sol batches, import model results."""
import argparse
import datetime as dt
import json
import os
from dataclasses import dataclass
from contextlib import closing
from pathlib import Path

from generate import atomic_json
from history import connect
from import_api_history import import_history
from model_stage import queue as model_queue
from providers import Bing, Google
from research import ROOT, import_contexts, import_generation, now, packed, research_status
from semrush_workflow import collect as collect_semrush, init, plan, status as semrush_status


@dataclass(frozen=True)
class ImportSettings:
    start: dt.date
    end: dt.date
    providers: tuple = ('google','bing')
    site: str = 'https://manualsdump.com/'
    google_account: str = 'debsites2@gmail.com'
    gsc_credentials: Path | None = None
    approved: bool = False
    max_days: int = 14
    max_pages: int = 50
    history_limit: int = 100
    country: str = 'US'
    semrush_units: int = 0
    semrush_requests: int = 8
    related_limit: int = 0
    contexts: Path | None = None
    bing_credentials: Path | None = None
    semrush_credentials: Path | None = None
    semrush_source: str = 'toolspd'
    archive_only: bool = False


def validate(settings):
    if settings.start>settings.end or settings.end>dt.date.today(): raise ValueError('Invalid import period')
    if not settings.providers or set(settings.providers)-{'google','bing'}: raise ValueError('Unknown search provider')
    if settings.site not in ('https://manualsdump.com/','http://manualsdump.com/','https://www.manualsdump.com/','sc-domain:manualsdump.com'):
        raise ValueError('Select an exact ManualsDump property')
    if not 1<=settings.max_days<=500 or not 1<=settings.max_pages<=10000 or not 1<=settings.history_limit<=10000:
        raise ValueError('Invalid collection batch size')
    if settings.semrush_units<0 or not 1<=settings.semrush_requests<=1000 or not 0<=settings.related_limit<=100:
        raise ValueError('Invalid Semrush bounds')
    if settings.semrush_source not in ('api','toolspd'): raise ValueError('Unknown Semrush source')
    if settings.semrush_units and settings.semrush_source!='api': raise ValueError('Paid Semrush API collection requires --semrush-source api')
    if settings.archive_only and (settings.contexts or settings.semrush_units):
        raise ValueError('Archive collection accepts search-provider inputs only')


def verify_google(provider,settings):
    # The caller must supply account-specific credentials. No translation-service
    # account or generic GOOGLE_APPLICATION_CREDENTIALS fallback is used here.
    identity=provider.call('https://openidconnect.googleapis.com/v1/userinfo')
    if identity.get('email','').casefold()!=settings.google_account.casefold() or identity.get('email_verified') is not True:
        raise ValueError('Google credential account is not the configured verified account')
    if not any(s.get('siteUrl')==settings.site and s.get('permissionLevel')!='siteUnverifiedUser' for s in provider.sites()):
        raise ValueError('Google account lacks the exact requested Search Console property')


def credential_configuration():
    """Report configured inputs without exposing or using any credential value."""
    return dict(gscAccountFileConfigured=bool(os.getenv('MANUALSDUMP_GSC_CREDENTIALS') or credential_path('google')),
                bingKeyConfigured=bool(os.getenv('BING_WEBMASTER_API_KEY') or credential_path('bing')),
                semrushKeyConfigured=bool(os.getenv('SEMRUSH_API_KEY') or credential_path('semrush')),
                limitation='Local configuration only; this status command does not verify live access.')


def credential_path(provider,explicit=None):
    variable='MANUALSDUMP_GSC_CREDENTIALS' if provider=='google' else 'MANUALSDUMP_'+provider.upper()+'_CREDENTIALS'
    path=explicit or os.getenv(variable)
    path=Path(path) if path else ROOT/'artifacts/search-metadata/credentials'/f'{provider}.private.json'
    return path if path.is_file() else None


def provider_key(provider,explicit=None):
    path=credential_path(provider,explicit)
    if path:
        with path.open(encoding='utf-8-sig') as stream: value=json.load(stream)
        if value.get('provider')!=provider or not isinstance(value.get('api_key'),str) or not value['api_key']:
            raise ValueError('Invalid provider credential file')
        return value['api_key']
    if explicit: raise ValueError('Provider credential file is missing')
    return os.getenv('BING_WEBMASTER_API_KEY' if provider=='bing' else 'SEMRUSH_API_KEY')


def import_data(db,history_path,directory,settings,google_factory=Google,bing_factory=Bing):
    validate(settings)
    if not settings.approved: raise ValueError('Explicit API credential-use approval is required')
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'artifacts'): raise ValueError('Import outputs must be workspace artifacts')
    history_path=Path(history_path).resolve()
    database=next(row['file'] for row in db.execute('PRAGMA database_list') if row['name']=='main')
    if history_path==Path(database).resolve(): raise ValueError('History and research databases must differ')
    history_path.parent.mkdir(parents=True,exist_ok=True)
    report=dict(recordedAt=now(),start=str(settings.start),end=str(settings.end),site=settings.site,providers={},productionChanged=False)
    with closing(connect(history_path)) as history, history:
        for engine in settings.providers:
            try:
                if engine=='google':
                    credentials=settings.gsc_credentials or os.getenv('MANUALSDUMP_GSC_CREDENTIALS') or credential_path('google')
                    if not credentials: raise ValueError('Account-specific MANUALSDUMP_GSC_CREDENTIALS is not configured')
                    provider=google_factory(str(credentials));verify_google(provider,settings)
                    provider.collect_page_inventory(history,settings.site,settings.start,settings.end,settings.max_days)
                    provider.collect(history,settings.site,settings.start,settings.end,settings.max_days)
                    if not settings.archive_only:
                        provider.collect_page_metrics(history,settings.site,settings.start,settings.end,settings.max_pages)
                else:
                    provider=bing_factory(provider_key('bing',settings.bing_credentials))
                    if not any(s.get('Url',s.get('siteUrl'))==settings.site for s in provider.sites()):
                        raise ValueError('Bing account lacks the exact requested property')
                    provider.collect(history,settings.site,settings.start,settings.end,settings.max_pages)
                report['providers'][engine]=dict(batchSucceeded=True,
                    limitation='Bounded retained-provider batch; not a claim of complete historical collection.')
            except (ValueError,RuntimeError,OSError) as exc:
                # Provider implementations sanitize their errors. File/OS errors
                # are reduced to a type so a credential path is never echoed.
                report['providers'][engine]=dict(batchSucceeded=False,error=type(exc).__name__ if isinstance(exc,OSError) else str(exc))
    if settings.archive_only:
        report['stage']='search_history_archive'
        report['historyDatabase']=str(history_path)
        report['fullHistoryVerified']=False
        atomic_json(directory/'archive-status.json',report)
        return report
    report['historyImport']=import_history(db,history_path,directory/'evidence',settings.history_limit,
                                          settings.site,settings.start,settings.end)
    if settings.contexts: report['contextsImported']=import_contexts(db,settings.contexts)
    report['semrushPlan']=plan(db,settings.country,dt.date.today().strftime('%Y-%m'),related_limit=settings.related_limit,
                               start=str(settings.start),end=str(settings.end),transport=settings.semrush_source)
    db.commit()
    if settings.semrush_units:
        try:
            report['semrushCollection']=collect_semrush(db,directory/'semrush',provider_key('semrush',settings.semrush_credentials),True,
                                                       settings.semrush_units,settings.semrush_requests,
                                                       allowed_job_ids=set(report['semrushPlan']['jobIds']))
        except ValueError as exc: report['semrushCollection']=dict(error=str(exc),**semrush_status(db))
    else: report['semrushCollection']=dict(skipped=True,transport=settings.semrush_source,
        reason='ToolsPD uses the separate semrush browser worker' if settings.semrush_source=='toolspd' else 'No paid API-unit budget supplied',**semrush_status(db))
    report['research']=research_status(db)
    report['fullHistoryVerified']=False
    report['limitation']='Batch progress only. Check provider checkpoints, remaining pages and model queue; no model is run by import.'
    atomic_json(directory/'import-status.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'artifacts/search-metadata/research.sqlite3')
    commands=parser.add_subparsers(dest='command',required=True)
    imp=commands.add_parser('import');imp.add_argument('--start',type=dt.date.fromisoformat,required=True)
    imp.add_argument('--end',type=dt.date.fromisoformat,default=dt.date.today()-dt.timedelta(days=3))
    imp.add_argument('--provider',choices=('google','bing','both'),default='both')
    imp.add_argument('--site',default='https://manualsdump.com/');imp.add_argument('--google-account',default='debsites2@gmail.com')
    imp.add_argument('--gsc-credentials',type=Path);imp.add_argument('--approved-api-use',action='store_true')
    imp.add_argument('--bing-credentials',type=Path);imp.add_argument('--semrush-credentials',type=Path)
    imp.add_argument('--max-days',type=int,default=14);imp.add_argument('--max-pages',type=int,default=50)
    imp.add_argument('--history-limit',type=int,default=100);imp.add_argument('--country',default='US')
    imp.add_argument('--semrush-units',type=int,default=0);imp.add_argument('--semrush-requests',type=int,default=8)
    imp.add_argument('--related-limit',type=int,default=0);imp.add_argument('--contexts',type=Path)
    imp.add_argument('--semrush-source',choices=('toolspd','api'),default='toolspd')
    imp.add_argument('--history',type=Path,default=ROOT/'artifacts/search-metadata/history.sqlite3')
    imp.add_argument('--directory',type=Path,default=ROOT/'artifacts/search-metadata/import-runs')
    imp.add_argument('--dry-run',action='store_true')
    imp.add_argument('--archive-only',action='store_true',help='Save provider page and query history for later processing')
    prepare=commands.add_parser('prepare');prepare.add_argument('--limit',type=int,default=25)
    prepare.add_argument('--directory',type=Path,default=ROOT/'artifacts/search-metadata/model-bundles')
    generated=commands.add_parser('generation');generated.add_argument('file',type=Path)
    commands.add_parser('status')
    outcomes=commands.add_parser('outcomes',help='Save a per-page assessment of the imported inventory and drafts')
    outcomes.add_argument('--start',type=dt.date.fromisoformat,required=True)
    outcomes.add_argument('--end',type=dt.date.fromisoformat,required=True)
    sem=commands.add_parser('semrush',help='ToolsPD browser workflow; no Semrush API key is used')
    sem.add_argument('action',choices=('plan','queue','login','run','import','retry','status'))
    sem.add_argument('--origin',default='https://sktiman.toolspd.com')
    sem.add_argument('--country',default='US');sem.add_argument('--seeds',type=int,default=2)
    sem.add_argument('--limit',type=int,default=5);sem.add_argument('--daily-limit',type=int,default=20)
    sem.add_argument('--delay',type=float,default=15);sem.add_argument('--channel',choices=('msedge','chrome'),default='msedge')
    sem.add_argument('--profile',type=Path,default=ROOT/'artifacts/search-metadata/toolspd-profile')
    sem.add_argument('--directory',type=Path,default=ROOT/'artifacts/search-metadata/toolspd')
    sem.add_argument('--snapshot',type=Path);sem.add_argument('--job')
    sem.add_argument('--approved-browser-use',action='store_true')
    args=parser.parse_args()
    if args.command=='import':
        settings=ImportSettings(args.start,args.end,('google','bing') if args.provider=='both' else (args.provider,),
            args.site,args.google_account,args.gsc_credentials,args.approved_api_use,args.max_days,args.max_pages,
            args.history_limit,args.country,args.semrush_units,args.semrush_requests,args.related_limit,args.contexts,
            args.bing_credentials,args.semrush_credentials,args.semrush_source,args.archive_only)
        validate(settings)
        if args.dry_run:
            print(packed(dict(start=str(settings.start),end=str(settings.end),providers=settings.providers,site=settings.site,
                expectedGoogleAccount=settings.google_account,archiveOnly=settings.archive_only,maximumSemrushUnits=settings.semrush_units,apiRequestsMade=0,
                limitation='Configuration preview only; access and historical availability are unverified.')))
            return
    args.db.parent.mkdir(parents=True,exist_ok=True)
    with connect(args.db) as db:
        init(db)
        if args.command=='import': result=import_data(db,args.history,args.directory,settings)
        elif args.command=='prepare': result=model_queue(db,args.directory,args.limit)
        elif args.command=='generation': result=import_generation(db,args.file)
        elif args.command=='outcomes':
            from outcomes import reconcile
            result=reconcile(db,args.start,args.end)
        elif args.command=='semrush':
            from toolspd import init_ui, pending, ingest_snapshot, retry, run_worker
            init_ui(db);db.commit()
            if args.action=='plan': result=plan(db,args.country,dt.date.today().strftime('%Y-%m'),page_limit=args.limit,seeds=args.seeds,transport='toolspd')
            elif args.action=='queue': result=dict(jobs=pending(db,args.limit,args.origin))
            elif args.action in ('run','login'):
                if not args.approved_browser_use: raise ValueError('Explicit --approved-browser-use is required')
                result=run_worker(db,args.profile,args.directory,args.limit,args.daily_limit,args.delay,args.origin,args.channel,args.action=='login')
            elif args.action=='import':
                if not args.job or not args.snapshot: raise ValueError('--job and --snapshot are required')
                result=ingest_snapshot(db,args.job,args.snapshot,args.origin)
            elif args.action=='retry':
                if not args.job: raise ValueError('--job is required')
                result=retry(db,args.job)
            else: result=dict(**semrush_status(db),uiAttempts=db.execute('SELECT COUNT(*) FROM semrush_ui_attempts').fetchone()[0])
        else: result=dict(research=research_status(db),semrush=semrush_status(db),apiConfiguration=credential_configuration())
        # Console code pages on Windows may not represent all collected keywords.
        print(json.dumps(result,ensure_ascii=True,sort_keys=True,separators=(',',':')))


if __name__=='__main__':
    try: main()
    except (ValueError,RuntimeError) as exc: raise SystemExit(str(exc))
