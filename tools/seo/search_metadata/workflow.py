"""Prepare page-specific Sol generation requests from saved application data."""
import argparse
import datetime as dt
from pathlib import Path

from generate import atomic_json
from history import connect
from import_api_history import import_history
from research import ROOT, now, packed, research_status
from semrush_workflow import init, plan
from model_stage import queue as model_queue


def prepare(db,history,directory,country,month,pages=10,seeds=2,related_limit=0,history_limit=100):
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'artifacts'): raise ValueError('Workflow outputs must be workspace artifacts')
    database=next(row['file'] for row in db.execute('PRAGMA database_list') if row['name']=='main')
    if Path(history).resolve()==Path(database).resolve(): raise ValueError('History and research databases must differ')
    if Path(history).is_file():
        imported=import_history(db,history,directory/'api-history',history_limit)
    else:
        imported=dict(importedWindows=0,limitation='No saved API history database; collection has not run.')
    planned=plan(db,country,month,pages,seeds,related_limit)
    generated=model_queue(db,directory/'sol-bundles',pages)
    report=dict(recordedAt=now(),historyImport=imported,semrush=planned,
                apiCandidates=sum(r['importedCandidates'] for r in generated['queued']),
                solQueue=generated['queued'],modelHolds=generated['held'],
                research=research_status(db),productionChanged=False,
                limitation='Local preparation only. No API access, model execution or deployment is performed.')
    atomic_json(directory/'status.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'artifacts/search-metadata/research.sqlite3')
    parser.add_argument('--history',type=Path,default=ROOT/'artifacts/search-metadata/history.sqlite3')
    parser.add_argument('--directory',type=Path,default=ROOT/'artifacts/search-metadata/workflow')
    parser.add_argument('--country',required=True)
    parser.add_argument('--month',default=dt.date.today().strftime('%Y-%m'))
    parser.add_argument('--pages',type=int,default=10);parser.add_argument('--seeds',type=int,default=2)
    parser.add_argument('--related-limit',type=int,default=0);parser.add_argument('--history-limit',type=int,default=100)
    args=parser.parse_args();args.db.parent.mkdir(parents=True,exist_ok=True)
    with connect(args.db) as db:
        init(db)
        print(packed(prepare(db,args.history,args.directory,args.country,args.month,args.pages,args.seeds,args.related_limit,args.history_limit)))


if __name__=='__main__':
    try: main()
    except ValueError as exc: raise SystemExit(str(exc))
