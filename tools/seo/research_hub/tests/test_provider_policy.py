import unittest
from unittest.mock import patch
from research_hub.provider_policy import effective_policy
from research_hub.collectors import collection_policy,ToolsPDBrowser,ReportUnavailable


class PolicyTests(unittest.TestCase):
    def config(self):return dict(enabled=True,dailyLimit=150,delaySeconds=15,temporaryAllowanceDay='2026-11-07',allowedProjects=['german-grammar'])

    def test_temporary_total150_is_valid_only_on_the_approved_day(self):
        self.assertTrue(effective_policy(self.config(),'2026-11-07')['enabled'])
        self.assertFalse(effective_policy(self.config(),'2026-11-08')['enabled'])
        self.assertFalse(effective_policy(self.config(),'2026-11-06')['enabled'])

    def test_bounds_are_finite_and_project_scoped(self):
        for value in (151,0,True,150.5):
            cfg=self.config();cfg['dailyLimit']=value
            with self.assertRaises(ValueError):effective_policy(cfg,'2026-11-07')
        cfg=self.config();cfg['allowedProjects']=[]
        with self.assertRaises(ValueError):effective_policy(cfg,'2026-11-07')

    def test_other_projects_and_expired_days_cannot_reserve(self):
        with patch('research_hub.collectors.now',return_value='2026-11-07T23:59:00+00:00'):
            collection_policy(self.config(),'german-grammar')
            with self.assertRaises(ReportUnavailable):collection_policy(self.config(),'manualsdump')
        with patch('research_hub.collectors.now',return_value='2026-11-08T00:00:00+00:00'):
            with self.assertRaises(ReportUnavailable):collection_policy(self.config(),'german-grammar')

    def test_dispatch_after_expiry_is_blocked_even_if_attempt_was_reserved(self):
        browser=ToolsPDBrowser.__new__(ToolsPDBrowser);browser.config=self.config();browser.current_project='german-grammar'
        browser.current_attempt=lambda:'already-counted';browser.pacer=type('Pacer',(),{'dispatch':lambda *args:self.fail('No report after expiry')})()
        with patch('research_hub.collectors.now',return_value='2026-11-08T00:00:00+00:00'):
            with self.assertRaises(ReportUnavailable):browser.before_report()


if __name__=='__main__':unittest.main()
