import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from authorize_google import SCOPE, SCOPES, load_client, verify_identity, verify_lifetime


class GoogleAuthorizationTests(unittest.TestCase):
    def test_long_term_grant_refuses_explicit_test_lifetime(self):
        with self.assertRaisesRegex(ValueError,'time-limited'): verify_lifetime(dict(refresh_token_expires_in=604800),True)
        self.assertIsNone(verify_lifetime({},True))
        self.assertEqual(verify_lifetime(dict(refresh_token_expires_in=604800)),604800)
    def test_downloaded_desktop_client_and_reject_web_client(self):
        base=Path(__file__).resolve().parents[3]/'artifacts/search-metadata-tests'
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            path=Path(directory)/'client.json'
            client=dict(client_id='test.apps.googleusercontent.com',client_secret='test-secret')
            path.write_text(json.dumps(dict(installed=client)),encoding='utf-8')
            self.assertEqual(load_client(path),(client['client_id'],client['client_secret']))
            path.write_text(json.dumps(dict(web=client)),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'installed-app'): load_client(path)

    def test_identity_must_be_exact_and_verified(self):
        token=dict(access_token='test-access',refresh_token='test-refresh',scope=' '.join(SCOPES))
        for email,verified,allowed in [('debsites2@gmail.com',True,True),
                                       ('different@example.com',True,False),
                                       ('debsites2@gmail.com',False,False)]:
            with self.subTest(email=email,verified=verified):
                response=io.BytesIO(json.dumps(dict(email=email,email_verified=verified)).encode())
                with patch('authorize_google.urllib.request.urlopen',return_value=response) as request:
                    if allowed: verify_identity(token,'debsites2@gmail.com')
                    else:
                        with self.assertRaisesRegex(ValueError,'match'): verify_identity(token,'debsites2@gmail.com')
                    self.assertEqual(request.call_args.args[0].full_url,'https://openidconnect.googleapis.com/v1/userinfo')

    def test_no_offline_or_readonly_grant_stops_before_userinfo(self):
        for token in [dict(access_token='test',scope=SCOPE),
                      dict(access_token='test',refresh_token='test',scope='openid')]:
            with patch('authorize_google.urllib.request.urlopen') as request:
                with self.assertRaises(ValueError): verify_identity(token,'debsites2@gmail.com')
                request.assert_not_called()

    def test_failed_userinfo_error_contains_no_token(self):
        token=dict(access_token='private-test-token',refresh_token='test',scope=SCOPE)
        with patch('authorize_google.urllib.request.urlopen',side_effect=urllib.error.URLError('private-test-token')):
            with self.assertRaisesRegex(ValueError,'verification failed') as result:
                verify_identity(token,'debsites2@gmail.com')
            self.assertNotIn(token['access_token'],str(result.exception))


if __name__=='__main__': unittest.main()
