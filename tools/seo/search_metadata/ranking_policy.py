"""Pilot protection: optimize only pages with a reported page position >= 8."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from history import connect, page_key

MINIMUM_POSITION = 8.0


def init(db):
    db.execute('''CREATE TABLE IF NOT EXISTS research_page_rankings (
      id TEXT PRIMARY KEY,engine TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,url TEXT NOT NULL,
      pdf INTEGER NOT NULL,page INTEGER NOT NULL,position REAL,impressions INTEGER,
      raw_artifact TEXT NOT NULL,source TEXT NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS research_rankings_page ON research_page_rankings(pdf,page,end)')


def record(db,engine,start,end,url,position,impressions,proof,source):
    pdf,page=page_key(url)
    if engine not in ('google','bing'): raise ValueError('Unknown ranking provider')
    value=float(position) if position is not None else None
    if value is not None and (not math.isfinite(value) or value<1): value=None
    if impressions is None or impressions<=0: value=None
    payload=(engine,start,end,url,value,impressions,proof,source)
    ident=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    db.execute('INSERT OR IGNORE INTO research_page_rankings VALUES (?,?,?,?,?,?,?,?,?,?,?)',
               (ident,engine,start,end,url,pdf,page,value,impressions,proof,source))


def eligibility(db,pdf,page):
    # Query-level positions cover only disclosed queries and are never used here.
    metrics={}
    for row in db.execute('SELECT * FROM research_page_rankings WHERE pdf=? AND page=? ORDER BY rowid',(pdf,page)):
        item=dict(row)
        metrics[(row['engine'],row['start'],row['end'],row['url'])]=item
    for row in db.execute('SELECT * FROM research_windows WHERE pdf=? AND page=? ORDER BY rowid',(pdf,page)):
        url=json.loads(row['payload'])['verified']['url']
        metrics.setdefault((row['engine'],row['start'],row['end'],url),
            dict(engine=row['engine'],start=row['start'],end=row['end'],url=url,position=None,
                 impressions=row['page_impressions'],raw_artifact=row['raw_artifact'],source='Page position not reported'))
    latest={}
    for item in sorted(metrics.values(),key=lambda r:(r['end'],r['start'])):
        latest[(item['engine'],item['url'])]=item
    observations=list(latest.values())
    protected=any(r['position'] is not None and r['position']<MINIMUM_POSITION for r in observations)
    missing=not observations or any(r['position'] is None for r in observations)
    allowed=not protected and not missing
    return dict(eligible=allowed,minimumAveragePosition=MINIMUM_POSITION,
                reason='protected_top_positions' if protected else 'page_position_unknown' if missing else 'position_at_least_8',
                observations=observations)


def audit(db):
    rows=[];counts={}
    for page in db.execute('SELECT pdf,page,url FROM research_pages ORDER BY pdf,page'):
        verdict=eligibility(db,page['pdf'],page['page'])
        counts[verdict['reason']]=counts.get(verdict['reason'],0)+1
        rows.append(dict(sourcePdfId=page['pdf'],page=page['page'],url=page['url'],**verdict))
    return dict(minimumAveragePosition=MINIMUM_POSITION,counts=counts,pages=rows)


def backfill(db):
    """Recover page aggregates from already archived exports; no network access."""
    from research import csv_rows, field, gsc_export, gsc_tables, metric
    imported=0
    for inventory in db.execute('''SELECT i.*,a.path,a.kind FROM research_inventory i
            JOIN research_artifacts a ON a.id=i.raw_artifact ORDER BY i.rowid'''):
        if inventory['kind'] in ('api_page_metrics','saved_api_page_batch'): continue
        path=Path(inventory['path'])
        if inventory['engine']=='google':
            tables=gsc_tables(path,inventory['start'],inventory['end'])
            rows=tables.get('Страницы.csv',tables.get('Pages.csv',[]))
        else: rows=csv_rows(path.read_bytes())
        for row in rows:
            url=field(row,'Популярные страницы','Top pages','Page')
            try: page_key(url)
            except (ValueError,TypeError): continue
            record(db,inventory['engine'],inventory['start'],inventory['end'],url,
                   metric(field(row,'Позиция','Position','Avg. Position','Average Position')),
                   metric(field(row,'Показы','Impressions'),True),inventory['raw_artifact'],'page_inventory')
            imported+=1
    for window in db.execute('''SELECT w.*,a.path,a.kind FROM research_windows w
            JOIN research_artifacts a ON a.id=w.raw_artifact WHERE w.engine='google' ORDER BY w.rowid'''):
        if window['kind']!='page_query_export': continue
        data=gsc_export(Path(window['path']),window['pdf'],window['page'],window['start'],window['end'])
        record(db,'google',window['start'],window['end'],data['url'],data.get('pageAveragePosition'),
               data['observedImpressions'],window['raw_artifact'],'page_filtered_export')
        imported+=1
    return dict(processedPageReports=imported,**audit(db))


def main():
    from generate import atomic_json
    from research import ROOT, init as research_init, packed
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'artifacts/search-metadata/research.sqlite3')
    parser.add_argument('--backfill',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    with connect(args.db) as db:
        research_init(db)
        result=backfill(db) if args.backfill else audit(db)
        if args.output: atomic_json(args.output,result)
        print(packed({k:v for k,v in result.items() if k!='pages'}))


if __name__=='__main__': main()
