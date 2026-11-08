import datetime as dt
import os
import unittest
from urllib.parse import urlsplit
from unittest.mock import Mock

from toolspd import ReportUnavailable
from toolspd_session import ToolsPDSession, service_origin


class SessionPolicyTests(unittest.TestCase):
    def session(self):
        session = ToolsPDSession(Mock(), Mock(), 'https://old.toolspd.com')
        session.ready = True
        session.context.pages=[]
        return session

    def test_recovery_tries_visible_options_once_and_counts_report_retries(self):
        session = self.session()
        session.report = Mock(side_effect=[ReportUnavailable('login_required'),
            ReportUnavailable('provider_unavailable'), {'report': 'verified'}])
        session.catalog = Mock(return_value=('https://app.toolspd.com/page/semrushnew', ['Access Semrush 1', 'Access Semrush 2']))
        session.controls = Mock(return_value=iter([Mock()]))
        # Each return to the catalog creates a fresh rendered locator list.
        session.controls.side_effect = lambda pattern: iter([Mock()])
        session.navigate = Mock()
        session.check_block = Mock()
        def follow(control):
            session.page.url = 'https://' + ('one' if session.report.call_count == 1 else 'two') + '.toolspd.com/'
        session.follow = follow
        budget = Mock()
        self.assertEqual(session.capture({}, budget), {'report': 'verified'})
        self.assertEqual(budget.call_count, 2)
        self.assertEqual(session.catalog.call_count, 1)
        self.assertEqual([c.args[1] for c in session.report.call_args_list],
                         ['https://old.toolspd.com', 'https://one.toolspd.com', 'https://two.toolspd.com'])

    def test_budget_denial_prevents_failover_report(self):
        session = self.session()
        session.report = Mock(side_effect=ReportUnavailable('login_required'))
        session.catalog = Mock(return_value=('https://one.toolspd.com/', []))
        session.page.url = 'https://one.toolspd.com/'
        session.check_block = Mock()
        with self.assertRaisesRegex(ReportUnavailable, 'daily_limit_reached'):
            session.capture({}, Mock(side_effect=ReportUnavailable('daily_limit_reached')))
        self.assertEqual(session.report.call_count, 1)

    def test_security_challenge_stops_without_recovery_loop(self):
        session = self.session()
        session.report = Mock(side_effect=ReportUnavailable('challenge'))
        session.catalog = Mock()
        with self.assertRaisesRegex(ReportUnavailable, 'challenge'):
            session.capture({}, Mock())
        session.catalog.assert_not_called()

    def test_concurrent_warning_stops_reuse_and_never_opens_catalog(self):
        session = self.session()
        session.report = Mock(side_effect=ReportUnavailable('concurrent_access_detected'))
        session.catalog = Mock()
        retry = Mock()
        with self.assertRaisesRegex(ReportUnavailable, 'concurrent_access_detected'):
            session.capture({}, retry)
        session.catalog.assert_not_called()
        retry.assert_not_called()

    def test_concurrent_warning_on_first_service_never_tries_another_domain(self):
        session = self.session()
        session.ready = False
        session.catalog = Mock(return_value=('https://app.toolspd.com/page/semrushnew', ['Access Semrush 1', 'Access Semrush 2']))
        session.controls = Mock(side_effect=lambda pattern: iter([Mock()]))
        session.follow = Mock()
        session.page.url = 'https://one.toolspd.com/'
        session.check_block = Mock(side_effect=ReportUnavailable('concurrent_access_detected'))
        session.report = Mock()
        retry = Mock()
        with self.assertRaisesRegex(ReportUnavailable, 'concurrent_access_detected'):
            session.capture({}, retry)
        self.assertEqual(session.follow.call_count, 1)
        session.report.assert_not_called()
        retry.assert_not_called()

    def test_warning_on_redirect_is_checked_before_login_recovery(self):
        session = self.session()
        session.page.url = 'https://one.toolspd.com/session-error'
        session.navigate = Mock(return_value=Mock(status=403))
        session.page.locator.return_value.inner_text.return_value = 'Simultaneous access detected'
        with self.assertRaisesRegex(ReportUnavailable, 'concurrent_access_detected'):
            session.read_report(dict(keyword='test',country='US'), 'https://one.toolspd.com')

    def test_explicit_warnings_are_distinct_from_concurrency_keywords(self):
        from toolspd import check_concurrent_access
        for text in ('Simultaneous access detected', 'Multiple active sessions detected',
                     'You are logged in on another device', 'Concurrent sessions are not allowed',
                     'Обнаружен параллельный доступ'):
            with self.subTest(text=text), self.assertRaisesRegex(ReportUnavailable, 'concurrent_access_detected'):
                check_concurrent_access(text)
        for text in ('Keyword Magic Tool: concurrent sessions', 'parallel connection manual', 'multiple devices', ''):
            check_concurrent_access(text)

    def test_member_or_unrelated_host_is_never_accepted_as_report_origin(self):
        for url in ('https://app.toolspd.com/member', 'https://one.toolspd.com.attacker.example/',
                    'http://one.toolspd.com/', 'https://owner:secret@one.toolspd.com/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                service_origin(url)


@unittest.skipUnless(os.environ.get('SEO_BROWSER_TESTS') == '1', 'Opt-in isolated rendered-UI fixtures')
class RenderedSessionTests(unittest.TestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright
        self.api = sync_playwright().start()
        self.browser = self.api.chromium.launch(channel=os.environ.get('SEO_TEST_BROWSER_CHANNEL', 'msedge'), headless=True)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.authenticated = False
        self.member_user = 'owner'
        self.google_block = False
        self.report_hosts = []
        self.context.route('**/*', self.route)
        self.request = dict(keyword='printer manual', country='US', month=dt.date.today().strftime('%Y-%m'), limit=10)

    def tearDown(self):
        self.browser.close()
        self.api.stop()

    def route(self, route):
        from urllib.parse import urlsplit
        parsed = urlsplit(route.request.url)
        host, path = parsed.hostname, parsed.path
        html = ''
        if host == 'app.toolspd.com':
            if path == '/misc/google-signin/redirect':
                route.fulfill(content_type='text/html', body='<script>location.href="https://accounts.google.com/fixture"</script>')
                return
            if path == '/signed-in':
                self.authenticated = True
                route.fulfill(content_type='text/html', body='<script>location.href="https://app.toolspd.com/member"</script>')
                return
            if path == '/page/semrushnew':
                html = ''.join(f'<a target="_blank" onclick="event.preventDefault();setTimeout(()=>window.open(this.href),1400)" href="https://{host}.toolspd.com/auth">Access Semrush {n}</a>'
                               for n, host in enumerate(('one', 'two', 'three'), 1))
            elif self.authenticated:
                html = f'<p>UserID: {self.member_user}</p><a style="display:none" href="/logout">Logout</a><a href="/logout?fixture=1">Logout</a><a aria-label="semrush Access semrush" href="/page/semrushnew">Access semrush</a>'
            else:
                html = '<input type="password"><a href="/misc/google-signin/redirect">Google</a>'
        elif host == 'accounts.google.com':
            html = 'This browser or app may not be secure' if self.google_block else (
                '<a data-identifier="other@example.com" href="https://unexpected.example/">Other account</a>'
                '<a data-identifier="owner@example.com" href="https://app.toolspd.com/signed-in">Owner</a>')
        elif host in ('old.toolspd.com', 'one.toolspd.com', 'two.toolspd.com', 'three.toolspd.com'):
            if path == '/analytics/keywordmagic/':
                self.report_hosts.append(host)
                if host == 'old.toolspd.com':
                    html = '<input type="password">'
                elif host != 'three.toolspd.com':
                    route.fulfill(status=503, body='Temporarily unavailable')
                    return
                else:
                    html = '''<h1>Keyword Magic Tool: printer manual</h1>
                      <button aria-label="Select country">United States</button>
                      <table id="keywords-table"><tr><th>Keyword</th><th>Volume</th><th>KD %</th></tr>
                      <tr><td>printer manual</td><td>100</td><td>n/a</td></tr></table>'''
            else:
                html = '<h1>Semrush</h1>'
        else:
            route.abort()
            if route.request.is_navigation_request():
                raise AssertionError('Unexpected fixture navigation host: '+str(host))
            return
        route.fulfill(content_type='text/html', body=html)

    def session(self):
        return ToolsPDSession(self.context, self.page, 'https://old.toolspd.com',
                              account='owner@example.com', member_user='owner', timeout=10)

    def test_google_account_reuse_popup_variants_and_rendered_report(self):
        session = self.session()
        budget = Mock()
        dispatched=Mock()
        session.before_report=dispatched
        snapshot = session.capture(self.request, budget)
        self.assertEqual(dispatched.call_count,3)
        self.assertEqual(len(session.failed_reports),2)
        self.assertEqual(session.base, 'https://three.toolspd.com')
        self.assertEqual(snapshot['rows'], [['printer manual', '100', 'n/a']])
        self.assertEqual(self.report_hosts, ['one.toolspd.com', 'two.toolspd.com', 'three.toolspd.com'])
        self.assertEqual(budget.call_count, 2)
        self.assertTrue(self.authenticated)
        self.assertEqual([urlsplit(p.url).hostname for p in self.context.pages if urlsplit(p.url).hostname in ('one.toolspd.com','two.toolspd.com','three.toolspd.com')],['three.toolspd.com'])

    def test_shared_browser_gates_actual_report_navigations_after_login(self):
        import sys,tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from research import ROOT
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from research_hub.collectors import ToolsPDBrowser
        from toolspd_pacing import ReportPacer
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/search-metadata-tests') as directory:
            stamp=[dt.datetime.now(dt.timezone.utc)]
            def sleep(seconds): stamp[0]+=dt.timedelta(seconds=seconds)
            pacer=ReportPacer(Path(directory)/'toolspd-profile',15,sleep,lambda:stamp[0])
            try:
                browser=ToolsPDBrowser(SimpleNamespace(data={'semrush':{'origin':'https://old.toolspd.com',
                    'account':'owner@example.com','memberUser':'owner'}},home=Path(directory)))
                browser.browser,browser.page,browser.pacer=self.context,self.page,pacer
                attempt=[0]
                browser.current_attempt=lambda:'fixture-'+str(attempt[0])
                def retry(): attempt[0]+=1
                browser.before_retry=retry
                navigation_times=[]
                def observed(request):
                    if '/analytics/keywordmagic/' in request.url:
                        navigation_times.append(stamp[0])
                self.context.on('request',observed)
                browser.capture(self.request)
                browser.capture(self.request)
                self.assertEqual(len(navigation_times),4)
                self.assertEqual([(b-a).total_seconds() for a,b in zip(navigation_times,navigation_times[1:])],[15,15,15])
            finally:pacer.close()

    def test_google_security_refusal_is_reported_without_retries(self):
        self.google_block = True
        with self.assertRaisesRegex(ReportUnavailable, 'google_reauthentication_required'):
            self.session().sign_in()
        self.assertFalse(self.authenticated)

    def test_wrong_member_identity_is_rejected(self):
        self.authenticated, self.member_user = True, 'other'
        with self.assertRaisesRegex(ReportUnavailable, 'toolspd_account_mismatch'):
            self.session().sign_in()


if __name__ == '__main__':
    unittest.main()
