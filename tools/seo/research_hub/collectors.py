"""Read-only provider adapters. No model invocation and no private ToolsPD APIs."""
import datetime as dt
import json
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote, urlsplit

from .settings import ROOT
from .store import digest, now, packed

# Reuse the tested credential exchange, sanitized HTTP transport and DOM parser.
# Do not call the old collectors: they deliberately accept PDF page URLs only.
LEGACY = Path(__file__).resolve().parents[1] / 'search_metadata'
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))
from providers import Google, Bing, bing_date
from toolspd import parse_snapshot, ReportUnavailable, SCRIPT, COUNTRY_LABELS, origin, url as report_url


def verify_google(provider, config):
    identity = provider.call('https://openidconnect.googleapis.com/v1/userinfo')
    if identity.get('email', '').casefold() != config['account'].casefold() or identity.get('email_verified') is not True:
        raise ValueError('Google account does not match the configured verified account')
    if not any(s.get('siteUrl') == config['property'] and s.get('permissionLevel') != 'siteUnverifiedUser' for s in provider.sites()):
        raise ValueError('Google account lacks the exact configured property')


def collect_google(service, job, factory=Google):
    config, credential = service.settings.credential(job['project'], 'google')
    provider = factory(str(credential))
    verify_google(provider, config)
    request, progress = job['request'], dict(job['progress'])
    progress.setdefault('day', request['end']); progress.setdefault('phase', 'pages'); progress.setdefault('offset', 0)
    count = 0
    endpoint = 'https://www.googleapis.com/webmasters/v3/sites/' + quote(config['property'], safe='') + '/searchAnalytics/query'
    while progress['day'] >= request['start'] and count < request['maxRequests']:
        dimensions = ['page'] if progress['phase'] == 'pages' else ['page', 'query'] + request['dimensions']
        payload = dict(startDate=progress['day'], endDate=progress['day'], dimensions=dimensions,
                       type='web', dataState='final', aggregationType='byPage', rowLimit=25000, startRow=progress['offset'])
        response = provider.call(endpoint, payload)
        raw_rows = response.get('rows', [])
        normalized = []
        for row in raw_rows:
            keys = dict(zip(dimensions, row['keys']))
            if len(row['keys']) != len(dimensions):
                raise ValueError('Unexpected Google report dimensions')
            normalized.append(dict(url=keys.pop('page'), **keys, clicks=row['clicks'],
                                   impressions=row['impressions'], position=row.get('position')))
        # Archive provider proof independently of the normalized, queryable table.
        proof = service.store.artifact(dict(provider='google', property=config['property'], request=payload, response=response))
        offset = progress['offset'] + len(raw_rows)
        coverage = dict(limitation='Google top returned rows only; undisclosed/anonymized queries are unavailable.',
                        offset=progress['offset'], providerCapReached=offset >= 50000, dimensions=dimensions,
                        normalizedRows=len(normalized), returnedRows=len(raw_rows))
        service.import_search(job['project'], dict(provider='google', kind=progress['phase'], start=progress['day'], end=progress['day'],
            observedAt=now(), scope=dict(property=config['property'], searchType='web', dimensions=dimensions),
            rows=normalized, coverage=coverage, sourceReference='evidence:'+proof, snapshotId=job['id']), trusted=True)
        if len(raw_rows) < 25000 or offset >= 50000:
            if progress['phase'] == 'pages':
                progress['phase'] = 'queries'
            else:
                progress['phase'] = 'pages'
                progress['day'] = str(dt.date.fromisoformat(progress['day']) - dt.timedelta(days=1))
            progress['offset'] = 0
        else:
            progress['offset'] = offset
        count += 1
        progress['requestsCompleted'] = progress.get('requestsCompleted', 0) + 1
        service.store.update_job(job['id'], 'running', progress)
    state = 'done' if progress['day'] < request['start'] else 'partial'
    service.store.update_job(job['id'], state, progress, dict(requestsThisBatch=count,
        limitation='Completed requested API traversal is not proof of complete provider history.'))


def collect_bing(service, job, factory=Bing):
    config, path = service.settings.credential(job['project'], 'bing')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if value.get('provider') != 'bing' or not value.get('api_key'):
        raise ValueError('Invalid Bing credential file')
    provider = factory(value['api_key'])
    if not any(s.get('Url', s.get('siteUrl')) == config['property'] for s in provider.sites()):
        raise ValueError('Bing account lacks the exact configured property')
    request, progress = job['request'], dict(job['progress'])
    count = 0
    if 'inventoryEvidence' not in progress:
        stats = provider.call('GetPageStats', siteUrl=config['property'])
        proof = service.store.artifact(dict(provider='bing', method='GetPageStats', property=config['property'], rows=stats))
        groups, pages = {}, {}
        for row in stats:
            day = bing_date(row['Date'])
            if not request['start'] <= day <= request['end']:
                continue
            groups.setdefault(day, []).append(dict(url=row['Query'], clicks=row['Clicks'], impressions=row['Impressions'],
                                                   position=row.get('AvgImpressionPosition')))
            pages[row['Query']] = max(pages.get(row['Query'], ('', 0)), (day, row['Clicks']))
        for day, rows in groups.items():
            service.import_search(job['project'], bing_report(config, 'pages', day, rows, proof), trusted=True)
        progress.update(inventoryEvidence=proof, pages=sorted(pages, key=lambda u: pages[u], reverse=True), pageIndex=0)
        service.store.update_job(job['id'], 'running', progress)
        count += 1
    while progress['pageIndex'] < len(progress['pages']) and count < request['maxRequests']:
        url = progress['pages'][progress['pageIndex']]
        stats = provider.call('GetPageQueryStats', siteUrl=config['property'], page=url)
        proof = service.store.artifact(dict(provider='bing', method='GetPageQueryStats', property=config['property'], page=url, rows=stats))
        groups = {}
        for row in stats:
            day = bing_date(row['Date'])
            if request['start'] <= day <= request['end']:
                groups.setdefault(day, []).append(dict(url=url, query=row['Query'], clicks=row['Clicks'],
                    impressions=row['Impressions'], position=row.get('AvgImpressionPosition')))
        for day, rows in groups.items():
            report = bing_report(config, 'queries', day, rows, proof)
            report['scope']['page'] = url
            service.import_search(job['project'], report, trusted=True)
        progress['pageIndex'] += 1
        service.store.update_job(job['id'], 'running', progress)
        count += 1
    service.store.update_job(job['id'], 'done' if progress['pageIndex'] >= len(progress['pages']) else 'partial', progress,
        dict(requestsThisBatch=count, limitation='Bing retained snapshots only. API-labelled dates are not invented daily coverage.'))


def bing_report(config, kind, day, rows, proof):
    return dict(provider='bing', kind=kind, start=day, end=day, observedAt=now(), rows=rows,
                scope=dict(property=config['property'], searchType='web'), sourceReference='evidence:'+proof,
                coverage=dict(limitation='Bing retained snapshot with API-labelled date; reporting interval may not be one day.',
                              temporalResolution='provider_labelled_snapshot'))


def cache_key(request, keyword):
    return digest(dict(keyword=keyword, country=request['country'], language=request['language'],
                       method='toolspd_keywordmagic', match='all', limit=request['limit']))


def attach_report(service, job, keyword, report):
    with service.store.db:
        service.store.db.execute('INSERT OR IGNORE INTO keyword_links VALUES (?,?,?,?)',
                                (job['project'], job['request']['subject'], report, keyword))


def save_keyword_snapshot(service, job, keyword, snapshot):
    request = dict(job['request'], keyword=keyword, month=job['request']['requestedMonth'])
    base = service.settings.data.get('semrush', {}).get('origin', 'https://sktiman.toolspd.com')
    candidates = parse_snapshot(request, snapshot, base)
    artifact = service.store.artifact(snapshot)
    ident = digest((cache_key(request, keyword), artifact))
    with service.store.db:
        service.store.db.execute('INSERT OR IGNORE INTO keyword_reports VALUES (?,?,?,?,?,?)',
            (ident, cache_key(request, keyword), snapshot['observedAt'], artifact, packed(request), packed(candidates)))
    attach_report(service, job, keyword, ident)
    return ident


class ToolsPDBrowser:
    def __init__(self, settings):
        self.settings = settings
        self.config = settings.data.get('semrush', {})
        self.base = origin(self.config.get('origin', 'https://sktiman.toolspd.com'))
        self.browser = self.api = None

    def open(self, headless=True):
        # Browser state remains in the isolated owner profile; never copy another browser's cookies.
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            sys.path.insert(0, str(ROOT / 'artifacts/search-metadata/browser-deps'))
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                raise ValueError('Install the optional browser requirements before using ToolsPD') from None
        from toolspd import protect_profile
        profile = protect_profile(self.settings.home / 'toolspd-profile')
        self.api = sync_playwright().start()
        self.browser = self.api.chromium.launch_persistent_context(str(profile), channel=self.config.get('channel', 'msedge'),
                                                                    headless=headless, accept_downloads=False)
        self.page = self.browser.pages[0] if self.browser.pages else self.browser.new_page()

    def capture(self, request):
        if self.browser is None:
            self.open()
        response = self.page.goto(report_url(request, self.base), wait_until='domcontentloaded', timeout=45000)
        if response and response.status >= 400:
            raise ReportUnavailable('provider_unavailable')
        if urlsplit(self.page.url).hostname != urlsplit(self.base).hostname:
            raise ReportUnavailable('login_required')
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            snapshot = self.page.evaluate(SCRIPT, request['limit'])
            try:
                parse_snapshot(request, snapshot, self.base)
                return snapshot
            except ReportUnavailable as exc:
                if exc.reason != 'report_not_ready_or_login_required':
                    raise
            self.page.wait_for_timeout(1000)
        raise ReportUnavailable('report_not_ready_or_login_required')

    def close(self):
        if self.browser:
            self.browser.close()
        if self.api:
            self.api.stop()


def collect_keywords(service, job, browser_factory=ToolsPDBrowser, sleeper=time.sleep):
    request, progress = job['request'], dict(job['progress'])
    service.store.subject(job['project'], request['subject'])
    config = service.settings.data.get('semrush', {})
    progress.setdefault('completedSeeds', [])
    browser = None
    try:
        for keyword in request['keywords']:
            if keyword in progress['completedSeeds']:
                continue
            cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=request['maxAgeDays'])).isoformat()
            cached = service.store.db.execute('SELECT id FROM keyword_reports WHERE cache_key=? AND observed>=? ORDER BY observed DESC LIMIT 1',
                                              (cache_key(request, keyword), cutoff)).fetchone()
            if cached and request['maxAgeDays']:
                attach_report(service, job, keyword, cached['id'])
                progress['cacheHits'] = progress.get('cacheHits', 0) + 1
            else:
                if not config.get('enabled'):
                    raise ReportUnavailable('semrush_collection_paused_in_configuration')
                if request['country'] not in COUNTRY_LABELS:
                    raise ReportUnavailable('country_label_not_yet_verified_by_collector')
                if request['requestedMonth'] != now()[:7]:
                    raise ReportUnavailable('new_month_requires_a_new_keyword_job')
                ceiling = config.get('dailyLimit', 20)
                delay = config.get('delaySeconds', 15)
                if not 1 <= ceiling <= 100 or delay < 10:
                    raise ValueError('Invalid ToolsPD daily limit or delay')
                db = service.store.db
                db.execute('BEGIN IMMEDIATE')
                try:
                    attempts = db.execute('SELECT COUNT(*) FROM attempts WHERE started>=?', (now()[:10],)).fetchone()[0]
                    if attempts >= ceiling:
                        raise ReportUnavailable('daily_limit_reached')
                    last = db.execute('SELECT started FROM attempts ORDER BY started DESC LIMIT 1').fetchone()
                    attempt = uuid.uuid4().hex
                    db.execute('INSERT INTO attempts VALUES (?,?,?,?)', (attempt, job['id'], now(), 'reserved'))
                    db.commit()  # Count before navigation; retries and crashes never refund attempts.
                except BaseException:
                    db.rollback()
                    raise
                if last:
                    elapsed = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last['started'])).total_seconds()
                    sleeper(max(0, delay-elapsed))
                try:
                    if browser is None:
                        browser = browser_factory(service.settings)
                    snapshot = browser.capture(dict(request, keyword=keyword, month=request['requestedMonth']))
                    save_keyword_snapshot(service, job, keyword, snapshot)
                    with db:
                        db.execute("UPDATE attempts SET status='done' WHERE id=?", (attempt,))
                except BaseException:
                    with db:
                        db.execute("UPDATE attempts SET status='failed' WHERE id=?", (attempt,))
                    raise
            progress['completedSeeds'].append(keyword)
            service.store.update_job(job['id'], 'running', progress)
        service.store.update_job(job['id'], 'done', progress, dict(apiUnitsSpent=0, limitation='Rendered report subset; candidates require model review.'))
    finally:
        if browser:
            browser.close()
