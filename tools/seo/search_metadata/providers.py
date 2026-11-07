"""Read-only official APIs; credentials are read from local files/environment, never logged."""
import base64
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from history import bind_scope, checkpoint, ingest, ingest_page_metrics, page_key


def request(url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data, {'Content-Type': 'application/json', **(headers or {})})
            with urllib.request.urlopen(req, timeout=45) as response: return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(min(30, 2**attempt * 2)); continue
            # Bing credentials appear in its URL: do not include URL, response body, or exception text.
            raise RuntimeError(f'Provider HTTP {exc.code} ({urllib.parse.urlsplit(url).hostname})') from None
        except urllib.error.URLError:
            raise RuntimeError(f'Provider connection failed ({urllib.parse.urlsplit(url).hostname})') from None


def google_token(credentials):
    with open(credentials, encoding='utf-8-sig') as source: value = json.load(source)
    if value['type'] == 'service_account':
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        enc = lambda x: base64.urlsafe_b64encode(json.dumps(x, separators=(',', ':')).encode()).rstrip(b'=')
        now = int(time.time())
        unsigned = enc({'alg': 'RS256', 'typ': 'JWT'}) + b'.' + enc(dict(iss=value['client_email'],
            scope='https://www.googleapis.com/auth/webmasters.readonly', aud='https://oauth2.googleapis.com/token', iat=now, exp=now+3600))
        private = serialization.load_pem_private_key(value['private_key'].encode(), password=None)
        signed = unsigned + b'.' + base64.urlsafe_b64encode(private.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())).rstrip(b'=')
        fields = {'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': signed.decode()}
    elif value['type'] == 'authorized_user':
        fields = {key: value[key] for key in ('client_id', 'client_secret', 'refresh_token')}
        fields['grant_type'] = 'refresh_token'
    else: raise ValueError('Use service_account or authorized_user credentials')
    req = urllib.request.Request('https://oauth2.googleapis.com/token', urllib.parse.urlencode(fields).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as response: return json.load(response)['access_token']
    except urllib.error.HTTPError as exc: raise RuntimeError(f'Google credential exchange HTTP {exc.code}') from None
    except urllib.error.URLError: raise RuntimeError('Google credential exchange connection failed') from None


class Google:
    def __init__(self, credentials):
        if not credentials: raise ValueError('GOOGLE_APPLICATION_CREDENTIALS is not configured')
        self.credentials, self.token, self.expires = credentials, None, 0

    def call(self, url, body=None):
        if time.time() >= self.expires:
            self.token = google_token(self.credentials); self.expires = time.time() + 3300
        return request(url, body, {'Authorization': 'Bearer ' + self.token})

    def sites(self):
        return self.call('https://www.googleapis.com/webmasters/v3/sites').get('siteEntry', [])

    def collect(self, db, site, start, end, max_days):
        bind_scope(db,'google',site)
        endpoint = 'https://www.googleapis.com/webmasters/v3/sites/' + urllib.parse.quote(site, safe='') + '/searchAnalytics/query'
        day, count = end, 0
        while day >= start and count < max_days:
            key = 'google:web:' + site + ':' + str(day)
            state = checkpoint(db, key) or {'offset': 0, 'done': False}
            if state['done']: day -= dt.timedelta(days=1); continue
            count += 1
            while not state['done']:
                offset = state['offset']
                payload = dict(startDate=str(day), endDate=str(day), dimensions=['page', 'query'], type='web',
                               dataState='final', aggregationType='byPage', rowLimit=25000, startRow=offset,
                               dimensionFilterGroups=[{'groupType': 'and', 'filters': [{'dimension': 'page', 'operator': 'contains', 'expression': '/en/manuals/'}]}])
                rows = self.call(endpoint, payload).get('rows', [])
                normalized = []
                for row in rows:
                    try: page_key(row['keys'][0])
                    except ValueError: continue
                    normalized.append(dict(engine='google', start=str(day), end=str(day), url=row['keys'][0], query=row['keys'][1],
                                           clicks=row['clicks'], impressions=row['impressions'], position=row.get('position')))
                state = dict(offset=offset+len(rows), done=len(rows) < 25000 or offset+len(rows) >= 50000,
                             possibly_truncated=offset+len(rows) >= 50000, limitation='Top rows only; anonymized/omitted queries are unavailable.')
                with db:
                    ingest(db, normalized, 'gsc-api-web-final'); checkpoint(db, key, state)
                print(json.dumps(dict(engine='google', date=str(day), rows=len(rows), **state)), flush=True)
                time.sleep(.3)
            day -= dt.timedelta(days=1)

    def collect_page_metrics(self,db,site,start,end,max_pages):
        """Fetch unsegmented exact-page metrics, separately from disclosed queries."""
        bind_scope(db,'google',site)
        endpoint='https://www.googleapis.com/webmasters/v3/sites/'+urllib.parse.quote(site,safe='')+'/searchAnalytics/query'
        count=0
        pages=db.execute('''SELECT start,end,url,MAX(clicks) clicks FROM (
            SELECT start,end,url,clicks FROM observations
              WHERE engine='google' AND source='gsc-api-web-final' AND start>=? AND end<=?
            UNION ALL SELECT start,end,url,clicks FROM api_page_metrics
              WHERE engine='google' AND site=? AND start>=? AND end<=?)
            GROUP BY start,end,url ORDER BY end DESC,clicks DESC,url''',
            (str(start),str(end),site,str(start),str(end))).fetchall()
        for page in pages:
            state=checkpoint(db,'google:web:'+site+':'+page['start'])
            if not state or not state.get('done'): continue
            identity='google:page-metrics:'+site+':'+page['url']+':'+page['start']+':'+page['end']
            if checkpoint(db,identity): continue
            if count>=max_pages: break
            payload=dict(startDate=page['start'],endDate=page['end'],dimensions=[],type='web',dataState='final',
                         aggregationType='byPage',dimensionFilterGroups=[dict(groupType='and',filters=[
                             dict(dimension='page',operator='equals',expression=page['url'])])])
            response=self.call(endpoint,payload);rows=response.get('rows',[])
            if len(rows)>1: raise ValueError('Expected one unsegmented page aggregate')
            data=rows[0] if rows else dict(clicks=0,impressions=0,position=None)
            with db:
                ingest_page_metrics(db,'google',site,page['start'],page['end'],page['url'],data['clicks'],data['impressions'],
                                    data.get('position'),dict(method='SearchAnalytics.query',request=payload,response=response))
                checkpoint(db,identity,dict(done=True))
            count+=1
            print(json.dumps(dict(engine='google',pageMetrics=page['url'],date=page['start'])),flush=True)
            time.sleep(.3)

    def collect_page_inventory(self,db,site,start,end,max_days):
        """Discover page traffic independently of whether queries are disclosed."""
        bind_scope(db,'google',site)
        endpoint='https://www.googleapis.com/webmasters/v3/sites/'+urllib.parse.quote(site,safe='')+'/searchAnalytics/query'
        day=end;processed=0
        while day>=start and processed<max_days:
            identity='google:pages:web:'+site+':'+str(day)
            state=checkpoint(db,identity) or dict(offset=0,done=False)
            if state['done']: day-=dt.timedelta(days=1);continue
            processed+=1
            while not state['done']:
                payload=dict(startDate=str(day),endDate=str(day),dimensions=['page'],type='web',dataState='final',
                    aggregationType='byPage',rowLimit=25000,startRow=state['offset'],
                    dimensionFilterGroups=[dict(groupType='and',filters=[dict(dimension='page',operator='contains',expression='/en/manuals/')])])
                rows=self.call(endpoint,payload).get('rows',[])
                with db:
                    for row in rows:
                        try: page_key(row['keys'][0])
                        except ValueError: continue
                        ingest_page_metrics(db,'google',site,str(day),str(day),row['keys'][0],row['clicks'],row['impressions'],
                            row.get('position'),dict(method='SearchAnalytics.query',kind='page_inventory',request=payload,responseRow=row))
                    offset=state['offset']+len(rows)
                    state=dict(offset=offset,done=len(rows)<25000 or offset>=50000,possibly_truncated=offset>=50000,
                               limitation='Top returned page rows only; full coverage is not established.')
                    checkpoint(db,identity,state)
                print(json.dumps(dict(engine='google',inventoryDate=str(day),rows=len(rows),**state)),flush=True)
                time.sleep(.3)
            day-=dt.timedelta(days=1)


def bing_date(value):
    match = re.fullmatch(r'/Date\((-?\d+)(?:[+-]\d{4})?\)/', value)
    return str(dt.datetime.fromtimestamp(int(match[1])/1000, dt.timezone.utc).date()) if match else str(dt.date.fromisoformat(value[:10]))


class Bing:
    def __init__(self, key):
        if not key: raise ValueError('BING_WEBMASTER_API_KEY is not configured')
        self.key = key

    def call(self, method, **fields):
        return request('https://ssl.bing.com/webmaster/api.svc/json/' + method + '?' + urllib.parse.urlencode({**fields, 'apikey': self.key}))['d']

    def sites(self): return self.call('GetUserSites')

    def collect(self, db, site, start, end, max_pages):
        bind_scope(db,'bing',site)
        stats = self.call('GetPageStats', siteUrl=site)
        pages = {}
        for row in stats:
            try: page_key(row['Query'])
            except ValueError: continue
            date = bing_date(row['Date'])
            if start <= dt.date.fromisoformat(date) <= end:
                rank = (date, row['Clicks']); pages[row['Query']] = max(pages.get(row['Query'], rank), rank)
                if row.get('Impressions') is not None:
                    with db:
                        ingest_page_metrics(db,'bing',site,date,date,row['Query'],row['Clicks'],row['Impressions'],
                                            row.get('AvgImpressionPosition'),dict(method='GetPageStats',site=site,row=row))
        # Retained provider inventories can change between batches. Keep URLs
        # discovered by earlier batches in this same bound archive, even if the
        # newest GetPageStats response no longer includes them.
        for row in db.execute("""SELECT url,MAX(end) recent,MAX(clicks) clicks FROM (
                SELECT url,end,clicks FROM api_page_metrics WHERE engine='bing' AND site=? AND start>=? AND end<=?
                UNION ALL SELECT url,end,clicks FROM observations WHERE engine='bing'
                    AND source='bing-api-page-query' AND start>=? AND end<=?
            ) GROUP BY url""",(site,str(start),str(end),str(start),str(end))):
            rank=(row['recent'],row['clicks'])
            pages[row['url']]=max(pages.get(row['url'],rank),rank)
        done = 0
        for url in sorted(pages, key=lambda url: pages[url], reverse=True):
            # Different requested ranges on the same day must not share a checkpoint.
            # The API exposes its retained snapshot, not arbitrary historical coverage.
            key = 'bing:v2:' + site + ':' + url + ':' + str(dt.datetime.now(dt.timezone.utc).date()) + ':' + str(start) + ':' + str(end)
            if checkpoint(db, key): continue
            if done >= max_pages: break
            rows = self.call('GetPageQueryStats', siteUrl=site, page=url)
            normalized = []
            for row in rows:
                date = bing_date(row['Date'])
                if start <= dt.date.fromisoformat(date) <= end:
                    normalized.append(dict(engine='bing', start=date, end=date, url=url, query=row['Query'],
                        clicks=row['Clicks'], impressions=row['Impressions'], position=row.get('AvgImpressionPosition')))
            with db:
                db.execute('''CREATE TABLE IF NOT EXISTS api_bing_reports (
                    checkpoint_key TEXT PRIMARY KEY, payload TEXT NOT NULL, rejected_rows TEXT NOT NULL)''')
                rejected = []
                accepted = 0
                for index, item in enumerate(normalized):
                    try:
                        ingest(db, [item], 'bing-api-page-query')
                        accepted += 1
                    except ValueError as exc:
                        rejected.append(dict(index=index, reason=str(exc), row=item))
                db.execute('INSERT OR REPLACE INTO api_bing_reports VALUES (?,?,?)',
                    (key, json.dumps(rows, ensure_ascii=False), json.dumps(rejected, ensure_ascii=False)))
                checkpoint(db, key, dict(rows=accepted, rejectedRows=len(rejected)))
            done += 1
            print(json.dumps(dict(engine='bing', page=url, rows=len(normalized))), flush=True)
            time.sleep(.5)
