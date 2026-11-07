"""Recover the owner's ToolsPD session through visible Google/member controls.

Only the isolated application profile is used. Service URLs are discovered from
the member UI; SSO parameters, cookies and passwords are never exported.
"""
import re
import time
from urllib.parse import urlsplit, urljoin

from toolspd import ReportUnavailable, SCRIPT, origin, parse_snapshot, url

MEMBER = 'https://app.toolspd.com/member'
ACCESS = re.compile(r'\bAccess\s+Semrush(?:\s*[123])?\s*$', re.I)
VARIANT = re.compile(r'^Access\s+Semrush\s*([123])$', re.I)


def service_origin(value):
    parsed = urlsplit(value)
    base = origin('https://' + (parsed.hostname or ''))
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port is not None:
        raise ValueError('Unexpected ToolsPD service URL')
    if parsed.hostname in ('app.toolspd.com', 'www.toolspd.com'):
        raise ValueError('Member page is not a Semrush service')
    return base


class ToolsPDSession:
    def __init__(self, context, page, base, account=None, member_user=None, timeout=90, before_report=None):
        self.context, self.page, self.base = context, page, origin(base)
        if account and not re.fullmatch(r'[A-Za-z0-9._+@-]+', account):
            raise ValueError('Invalid Google account setting')
        self.account, self.member_user = account, member_user
        self.timeout = timeout
        self.events = []
        self.last_snapshot = None
        self.ready = False
        self.before_report = before_report
        self.failed_reports = []

    def check_block(self):
        text = self.page.locator('body').inner_text(timeout=10000).casefold()
        if any(s in text for s in ('verify you are human', 'unusual traffic', 'captcha')):
            raise ReportUnavailable('challenge')
        if any(s in text for s in ('this browser or app may not be secure', "couldn\u2019t sign you in", "couldn't sign you in")):
            raise ReportUnavailable('google_reauthentication_required')
        return text

    def visible(self, locator):
        return any(locator.nth(i).is_visible() for i in range(min(locator.count(), 20)))

    def navigate(self, target):
        from playwright.sync_api import Error as BrowserError
        try:
            return self.page.goto(target, wait_until='domcontentloaded', timeout=45000)
        except BrowserError:
            raise ReportUnavailable('navigation_failed') from None

    def follow(self, locator):
        from playwright.sync_api import Error as BrowserError
        opened = []
        on_page = lambda page: opened.append(page)
        self.context.on('page', on_page)
        try:
            control = next((locator.nth(i) for i in range(min(locator.count(), 20)) if locator.nth(i).is_visible()), None)
            if control is None:
                raise ReportUnavailable('visible_control_not_found')
            expects_popup = control.get_attribute('target') == '_blank'
            control.click(timeout=15000)
            deadline = time.monotonic() + (10 if expects_popup else 1)
            while not opened and time.monotonic() < deadline:
                self.page.wait_for_timeout(200)
            if opened:
                self.page = opened[-1]
            self.page.wait_for_load_state('domcontentloaded', timeout=45000)
        except BrowserError:
            raise ReportUnavailable('navigation_failed') from None
        finally:
            self.context.remove_listener('page', on_page)

    def sign_in(self, target=MEMBER):
        if target is not None:
            self.navigate(target)
        deadline = time.monotonic() + self.timeout
        started = selected = submitted = False
        while True:
            text = self.check_block()
            host = urlsplit(self.page.url).hostname
            state = dict(stage='authentication_state', host=host, memberVisible='userid:' in text, logoutCount=self.page.locator('a[href*="/logout"]').count())
            if not self.events or self.events[-1] != state:
                self.events.append(state)
            if host == 'app.toolspd.com':
                logout = self.page.locator('a[href*="/logout"]')
                if self.visible(logout):
                    if self.member_user and not re.search(r'userid\s*:\s*' + re.escape(self.member_user) + r'(?![\w.-])', text, re.I):
                        raise ReportUnavailable('toolspd_account_mismatch')
                    self.events.append(dict(stage='member_authenticated', host=host))
                    return
                if time.monotonic() >= deadline:
                    raise ReportUnavailable('login_required')
                google = self.page.locator('a[href*="/misc/google-signin/redirect"]')
                if not started and self.visible(google):
                    if not self.account:
                        raise ReportUnavailable('google_account_not_configured')
                    self.follow(google)
                    started = True
                    continue
            elif host == 'accounts.google.com':
                if not self.account:
                    raise ReportUnavailable('google_account_not_configured')
                chooser = self.page.locator('[data-identifier="' + self.account + '"],[data-email="' + self.account + '"]')
                if not selected and self.visible(chooser):
                    self.follow(chooser)
                    selected = True
                    continue
                email = self.page.locator('input[type="email"]')
                if not submitted and self.visible(email):
                    email.first.fill(self.account)
                    self.follow(self.page.locator('#identifierNext'))
                    submitted = True
                    continue
                if self.visible(self.page.locator('input[type="password"]')) or any(s in text for s in ('2-step verification', 'verify it\u2019s you', "verify it's you")):
                    raise ReportUnavailable('google_reauthentication_required')
            else:
                raise ReportUnavailable('unexpected_authentication_host')
            if time.monotonic() >= deadline:
                raise ReportUnavailable('login_required')
            self.page.wait_for_timeout(500)

    def controls(self, pattern):
        # Locator identities stay local; never persist SSO hrefs or query strings.
        for role in ('link', 'button'):
            controls = self.page.get_by_role(role, name=pattern)
            for i in range(min(controls.count(), 10)):
                control = controls.nth(i)
                if control.is_visible():
                    yield control

    def catalog(self):
        self.sign_in()
        links = list(self.controls(ACCESS))
        if not links:
            raise ReportUnavailable('semrush_access_not_available')
        catalog_target = urljoin(self.page.url, links[0].get_attribute('href') or '')
        self.follow(links[0])
        if urlsplit(self.page.url).hostname == 'app.toolspd.com' and self.visible(self.page.locator('input[type="password"]')):
            # Follow Google from the service-targeted login page, preserving its
            # visible return flow instead of starting again at the member root.
            self.sign_in(target=None)
            if urlsplit(catalog_target).hostname == 'app.toolspd.com':
                self.navigate(catalog_target)
        # Access may open the service directly or a page listing service options.
        self.check_block()
        if urlsplit(self.page.url).hostname != 'app.toolspd.com':
            return self.page.url, []
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            labels = [c.inner_text().strip() for c in self.controls(VARIANT)]
            if labels:
                return self.page.url, sorted(set(labels), key=lambda x: int(VARIANT.fullmatch(x)[1]))[:3]
            self.page.wait_for_timeout(500)
        raise ReportUnavailable('semrush_access_not_available')

    def report(self, request, base):
        self.last_snapshot = None
        try:
            if self.before_report:
                self.before_report()
            return self.read_report(request, base)
        except Exception as error:
            self.failed_reports.append(dict(origin=base,reason=getattr(error,'reason',type(error).__name__),
                                            snapshot=self.last_snapshot))
            raise

    def read_report(self, request, base):
        response = self.navigate(url(request, base))
        if response and response.status >= 400:
            self.events.append(dict(stage='report_http_error', host=urlsplit(base).hostname, status=response.status))
            raise ReportUnavailable('provider_unavailable')
        if urlsplit(self.page.url).hostname != urlsplit(base).hostname or urlsplit(self.page.url).path != '/analytics/keywordmagic/':
            raise ReportUnavailable('login_required')
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.visible(self.page.locator('input[type="password"]')):
                raise ReportUnavailable('login_required')
            snapshot = self.page.evaluate(SCRIPT, request['limit'])
            self.last_snapshot = snapshot
            try:
                parse_snapshot(request, snapshot, base)
                self.base = base
                self.ready = True
                self.events.append(dict(stage='report_verified', host=urlsplit(base).hostname))
                return snapshot
            except ReportUnavailable as error:
                if error.reason != 'report_not_ready_or_login_required':
                    raise
            except ValueError as error:
                self.events.append(dict(stage='report_validation_failed', host=urlsplit(base).hostname, reason=str(error)))
                raise ReportUnavailable('report_validation_failed') from None
            self.page.wait_for_timeout(1000)
        raise ReportUnavailable('report_not_ready_or_login_required')

    def capture(self, request, before_retry):
        self.last_snapshot = None
        self.failed_reports = []
        # A new browser activates a visible service before its first lookup.
        # Within the same context, reuse a verified report session directly.
        attempted = False
        if self.ready:
            attempted = True
            try:
                return self.report(request, self.base)
            except ReportUnavailable as error:
                if error.reason in ('challenge', 'report_validation_failed'):
                    raise
                self.events.append(dict(stage='session_recovery', reason=error.reason))
                self.ready = False
        catalog_url, labels = self.catalog()
        last = 'semrush_services_unavailable'
        catalog_page = self.page
        for label in labels or [None]:
            try:
                if label:
                    self.page = catalog_page
                    controls = list(self.controls(re.compile('^' + re.escape(label) + '$', re.I)))
                    if not controls:
                        self.events.append(dict(stage='service_unavailable', option=label, reason='visible_control_not_found'))
                        continue
                    self.follow(controls[0])
                base = service_origin(self.page.url)
                self.events.append(dict(stage='service_opened', option=label, host=urlsplit(base).hostname))
                self.check_block()
                if attempted:
                    before_retry()
                attempted = True
                return self.report(request, base)
            except ReportUnavailable as error:
                if error.reason in ('challenge', 'daily_limit_reached', 'google_reauthentication_required', 'report_validation_failed'):
                    raise
                last = error.reason
                self.events.append(dict(stage='service_unavailable', option=label, reason=last))
            except ValueError:
                last = 'invalid_service_destination'
                self.events.append(dict(stage='service_unavailable', option=label, reason=last))
        raise ReportUnavailable(last)
