"""Import saved API observations into the research database without API calls."""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

from generate import atomic_json
from history import connect, page_key
from ranking_policy import record as record_ranking
from research import ROOT, artifact, attach_context, init, key, now, packed, refresh_stage, start_run


def store_window(db,evidence_dir,engine,site,start,end,url,provenance,state,rows,page_metrics):
    pdf,page=page_key(url)
    evidence=dict(kind='saved_api_observations',engine=engine,site=site,start=start,end=end,url=url,
        source=provenance,checkpoint=state,queries=rows,pageMetrics=dict(page_metrics) if page_metrics else None,
        limitation='Disclosed page-query rows only; missing page totals and omitted queries remain unknown.')
    evidence_id=key(evidence);window_id=key(('api_history',evidence_id))
    if db.execute('SELECT 1 FROM research_windows WHERE id=?',(window_id,)).fetchone(): return 0
    path=evidence_dir/(evidence_id+'.json')
    if not path.exists(): atomic_json(path,evidence)
    raw_id=artifact(db,path,'saved_api_observations',url)
    verified=False
    current=db.execute('SELECT stage FROM research_pages WHERE pdf=? AND page=?',(pdf,page)).fetchone()
    for previous in db.execute('SELECT payload FROM research_windows WHERE pdf=? AND page=?',(pdf,page)):
        if current and current['stage']=='identity_review': break
        payload=json.loads(previous['payload'])
        if (payload.get('verified',{}).get('url')==url and payload.get('verifiedSourcePdfId')==pdf
                and not payload.get('identityReviewRequired')):
            verified=True;break
    clicks=page_metrics['clicks'] if page_metrics else None
    impressions=page_metrics['impressions'] if page_metrics else None
    data=dict(verified=dict(url=url,queries=rows,observedClicks=clicks,observedImpressions=impressions,
        queryRows=len(rows),exportedClicks=sum(r['clicks'] for r in rows),
        exportedImpressions=sum(r['impressions'] for r in rows),sourceType='saved_api_observations'),
        identityReviewRequired=not verified,verifiedSourcePdfId=pdf if verified else None,
        identityReviewReason='api_source_mapping_pending' if not verified else None)
    db.execute('INSERT OR IGNORE INTO research_pages VALUES (?,?,?,NULL,?,?)',(pdf,page,url,'content_pending',now()))
    attach_context(db,pdf,page)
    db.execute('INSERT INTO research_windows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (window_id,'api-history',pdf,page,engine,start,end,clicks,impressions,raw_id,'api','none',
         'Disclosed queries only; page totals use a separate aggregate when available',packed(data)))
    db.executemany('INSERT INTO research_queries VALUES (?,?,?,?,?)',
        [(window_id,r['query'],r['clicks'],r['impressions'],r['position']) for r in rows])
    refresh_stage(db,pdf,page);db.commit()
    return 1


def import_history(db, history_path, evidence_dir, limit=100, site='https://manualsdump.com/',start=None,end=None):
    if not 1 <= limit <= 10000:
        raise ValueError('Limit must be between 1 and 10000')
    start=str(dt.date.fromisoformat(str(start))) if start is not None else None
    end=str(dt.date.fromisoformat(str(end))) if end is not None else None
    if bool(start)!=bool(end) or start and start>end: raise ValueError('Specify a valid start/end import period')
    history_path = Path(history_path).resolve()
    evidence_dir = Path(evidence_dir).resolve()
    if not history_path.is_file():
        raise ValueError('History database does not exist')
    if not evidence_dir.is_relative_to(ROOT / 'artifacts'):
        raise ValueError('Evidence directory must be inside workspace artifacts')
    source = sqlite3.connect(history_path.as_uri() + '?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    imported = skipped = ranking_imports = discovery_imports = 0
    try:
        # Page-level aggregates have independent provenance; never derive them by
        # averaging the query rows, which can omit private and low-volume queries.
        if source.execute("SELECT 1 FROM sqlite_master WHERE name='api_page_metrics'").fetchone():
            for row in source.execute('SELECT * FROM api_page_metrics ORDER BY end DESC,rowid'):
                if start and (row['start']<start or row['end']>end): continue
                if row['site']!=site: raise ValueError('Page metric property binding mismatch')
                evidence=dict(row);ident=key(evidence)
                path=evidence_dir/(ident+'.json')
                if not path.exists(): atomic_json(path,evidence)
                proof=artifact(db,path,'api_page_metrics',row['url'])
                inventory_id=key(('api_page_inventory',proof))
                discovery_imports+=db.execute('INSERT OR IGNORE INTO research_inventory VALUES (?,?,?,?,?,?,?)',
                    (inventory_id,row['engine'],row['start'],row['end'],proof,1,
                     'Saved API page aggregate; queries may be absent or undisclosed; full history is not established.')).rowcount
                db.execute('INSERT OR IGNORE INTO research_discovered_pages VALUES (?,?,?,?,?,?)',
                    (inventory_id,row['pdf'],row['page'],row['url'],row['clicks'],row['impressions']))
                existing=db.execute('SELECT 1 FROM research_page_rankings WHERE raw_artifact=?',(proof,)).fetchone()
                if not existing:
                    record_ranking(db,row['engine'],row['start'],row['end'],row['url'],row['position'],
                                   row['impressions'],proof,'api_page_metrics')
                    ranking_imports+=1
                db.commit()
                if max(ranking_imports,discovery_imports)>=limit: break
        groups = source.execute('''SELECT engine,start,end,url,source FROM observations
            WHERE source IN ('gsc-api-web-final','bing-api-page-query')
            GROUP BY engine,start,end,url,source ORDER BY end DESC,start DESC,url''')
        for group in groups:
            engine, window_start, window_end, url, provenance = tuple(group)
            if start and (window_start<start or window_end>end): continue
            scopes=source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='provider_scopes'").fetchone()
            scope=source.execute('SELECT site FROM provider_scopes WHERE engine=?',(engine,)).fetchone() if scopes else None
            if not scope or scope['site']!=site:
                raise ValueError('API history lacks an exact property binding; recollect into a dedicated history database')
            if engine == 'google':
                state_row = source.execute('SELECT payload FROM checkpoints WHERE key=?',
                    ('google:web:' + site + ':' + window_start,)).fetchone()
                if window_start != window_end or not state_row or not json.loads(state_row[0]).get('done'):
                    skipped += 1
                    continue
                state = json.loads(state_row[0])
            elif engine == 'bing':
                # A retained Bing snapshot is not proof of complete historical coverage.
                state = {'coverage': 'retained snapshot; historical completeness unknown'}
            else:
                continue
            rows = [dict(row) for row in source.execute('''SELECT query,clicks,impressions,position
                FROM observations WHERE engine=? AND start=? AND end=? AND url=? AND source=? ORDER BY query''',
                (engine,window_start,window_end,url,provenance))]
            metric_table=source.execute("SELECT 1 FROM sqlite_master WHERE name='api_page_metrics'").fetchone()
            page_metrics=source.execute('''SELECT * FROM api_page_metrics WHERE engine=? AND site=?
                AND start=? AND end=? AND url=? ORDER BY rowid DESC LIMIT 1''',
                (engine,site,window_start,window_end,url)).fetchone() if metric_table else None
            imported+=store_window(db,evidence_dir,engine,site,window_start,window_end,url,provenance,state,rows,page_metrics)
            if imported >= limit:
                break
        # A successful aggregate plus a finished query batch can disclose traffic
        # while returning no queries for this URL. Keep an explicitly empty subset,
        # not a fabricated keyword or a claim that there were no real queries.
        if imported<limit and source.execute("SELECT 1 FROM sqlite_master WHERE name='api_page_metrics'").fetchone():
            for row in source.execute('''SELECT m.* FROM api_page_metrics m WHERE m.engine='google'
                AND m.rowid=(SELECT MAX(n.rowid) FROM api_page_metrics n WHERE n.engine=m.engine
                    AND n.site=m.site AND n.start=m.start AND n.end=m.end AND n.url=m.url)
                AND NOT EXISTS(SELECT 1 FROM observations o WHERE o.engine=m.engine AND o.start=m.start
                    AND o.end=m.end AND o.url=m.url AND o.source='gsc-api-web-final') ORDER BY m.end DESC,m.url'''):
                if row['site']!=site or start and (row['start']<start or row['end']>end): continue
                state_row=source.execute('SELECT payload FROM checkpoints WHERE key=?',
                    ('google:web:'+site+':'+row['start'],)).fetchone()
                if not state_row or not json.loads(state_row[0]).get('done'): continue
                imported+=store_window(db,evidence_dir,'google',site,row['start'],row['end'],row['url'],
                    'gsc-api-no-disclosed-query-rows',json.loads(state_row[0]),[],row)
                if imported>=limit: break
    finally:
        source.close()
    return dict(importedWindows=imported,importedPageMetrics=ranking_imports,importedPageInventories=discovery_imports,
                skippedIncompleteGoogleWindows=skipped,
                limitation='Full history and omitted queries are not established; identity may require review.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history',type=Path,default=ROOT/'artifacts/search-metadata/history.sqlite3')
    parser.add_argument('--db',type=Path,default=ROOT/'artifacts/search-metadata/research.sqlite3')
    parser.add_argument('--evidence-dir',type=Path,default=ROOT/'artifacts/search-metadata/api-import')
    parser.add_argument('--site',default='https://manualsdump.com/')
    parser.add_argument('--limit',type=int,default=100)
    args=parser.parse_args()
    args.db.parent.mkdir(parents=True,exist_ok=True)
    with connect(args.db) as db:
        init(db)
        start_run(db,'api-history')
        print(packed(import_history(db,args.history,args.evidence_dir,args.limit,args.site)))


if __name__ == '__main__':
    main()
