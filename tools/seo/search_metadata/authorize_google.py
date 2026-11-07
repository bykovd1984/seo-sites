"""Prepare an installed-app, read-only GSC OAuth grant; never print authorization codes or tokens."""
import argparse
import datetime as dt
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCOPE='https://www.googleapis.com/auth/webmasters.readonly'
SCOPES=(SCOPE,'openid','https://www.googleapis.com/auth/userinfo.email')


def load_client(path=None):
    if path:
        try:
            value=json.loads(Path(path).read_text(encoding='utf-8-sig')).get('installed',{})
        except (OSError,ValueError):
            raise ValueError('Could not read the installed-app OAuth client file') from None
        client=value.get('client_id');secret=value.get('client_secret')
    else:
        client=os.environ.get('manuals-prod-GoogleSearchConsole__ClientId')
        secret=os.environ.get('manuals-prod-GoogleSearchConsole__ClientSecret')
    if not isinstance(client,str) or not client.endswith('.apps.googleusercontent.com') or not isinstance(secret,str) or not secret:
        raise ValueError('A Google installed-app OAuth client is required')
    return client,secret


def verify_identity(token,account):
    if not token.get('refresh_token') or not token.get('access_token'):
        raise ValueError('No offline authorization returned; no credential was saved')
    if SCOPE not in set(token.get('scope','').split()):
        raise ValueError('Read-only Search Console permission was not granted')
    request=urllib.request.Request('https://openidconnect.googleapis.com/v1/userinfo',
                                   headers={'Authorization':'Bearer '+token['access_token']})
    try:
        with urllib.request.urlopen(request,timeout=30) as response: identity=json.load(response)
    except (urllib.error.URLError,ValueError):
        raise ValueError('Google account verification failed; no credential was saved') from None
    if identity.get('email','').casefold()!=account.casefold() or identity.get('email_verified') is not True:
        raise ValueError('The authorized Google account does not match the requested verified account')


def verify_lifetime(token,require_no_expiry=False):
    expiry=token.get('refresh_token_expires_in')
    if expiry is not None and (isinstance(expiry,bool) or not isinstance(expiry,(int,float)) or expiry<=0):
        raise ValueError('Unexpected Google refresh-token lifetime')
    if require_no_expiry and expiry is not None:
        raise ValueError('Google still issued a time-limited refresh token; existing credentials were preserved')
    return expiry


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--client-secrets',type=Path,help='Downloaded Google Desktop app OAuth client JSON')
    parser.add_argument('--timeout',type=int,default=600)
    parser.add_argument('--require-no-expiry',action='store_true',help='Refuse a refresh token with an explicit expiry')
    args=parser.parse_args()
    if args.output.exists(): raise SystemExit('Credential file already exists; refusing to replace it')
    try: client,secret=load_client(args.client_secrets)
    except ValueError as error: raise SystemExit(str(error)) from None
    state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result={}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*values): pass
        def do_GET(self):
            query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if not hmac.compare_digest(query.get('state',[''])[0],state):
                self.send_error(400,'Invalid OAuth state'); return
            if 'error' in query: result['error']='Google authorization was not completed'
            elif 'code' in query: result['code']=query['code'][0]
            else: self.send_error(400,'Missing authorization result'); return
            self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.end_headers()
            self.wfile.write(b'Authorization received. You may close this tab.')
    with HTTPServer(('127.0.0.1',0),Callback) as server:
        server.timeout=1
        redirect=f'http://127.0.0.1:{server.server_port}/'
        fields=dict(client_id=client,redirect_uri=redirect,response_type='code',scope=' '.join(SCOPES),
                    access_type='offline',prompt='consent',login_hint=args.account,state=state,
                    code_challenge=challenge,code_challenge_method='S256')
        print(json.dumps({'type':'google_readonly_authorization_ready','url':'https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode(fields),
                          'account_hint':args.account,'scopes':SCOPES}),flush=True)
        deadline=time.monotonic()+args.timeout
        while not result and time.monotonic()<deadline: server.handle_request()
    if not result: raise SystemExit('Authorization timed out; no credential was saved')
    if 'error' in result: raise SystemExit(result['error'])
    fields=dict(client_id=client,client_secret=secret,code=result['code'],redirect_uri=redirect,
                grant_type='authorization_code',code_verifier=verifier)
    request=urllib.request.Request('https://oauth2.googleapis.com/token',urllib.parse.urlencode(fields).encode())
    try:
        with urllib.request.urlopen(request,timeout=30) as response: token=json.load(response)
    except urllib.error.HTTPError as error: raise SystemExit(f'Google token exchange failed: HTTP {error.code}') from None
    except urllib.error.URLError: raise SystemExit('Google token exchange connection failed') from None
    try: verify_identity(token,args.account)
    except ValueError as error: raise SystemExit(str(error)) from None
    try: refresh_expiry=verify_lifetime(token,args.require_no_expiry)
    except ValueError as error: raise SystemExit(str(error)) from None
    value=dict(type='authorized_user',client_id=client,client_secret=secret,refresh_token=token['refresh_token'],account_hint=args.account)
    value.update(authorized_at=dt.datetime.now(dt.timezone.utc).isoformat(),granted_scopes=token.get('scope','').split(),
                 refresh_token_expires_in=refresh_expiry)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    # Create the empty file exclusively and restrict its ACL before writing any secret.
    with args.output.open('x',encoding='utf-8') as file:
        if os.name=='nt':
            acl=subprocess.run(['icacls.exe',str(args.output),'/inheritance:r','/grant:r',getpass.getuser()+':F','*S-1-5-18:F'],capture_output=True)
            if acl.returncode: raise SystemExit('Could not protect the credential file; no token was written')
        else: os.chmod(args.output,0o600)
        json.dump(value,file);file.flush();os.fsync(file.fileno())
    print(json.dumps({'type':'google_readonly_authorized','credential_file':str(args.output),'refresh_token_saved':True,
                      'refresh_token_expiry_reported':refresh_expiry is not None}),flush=True)


if __name__=='__main__': main()
