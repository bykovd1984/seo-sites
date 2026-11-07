"""Build a local runtime candidate from current validated drafts; never deploy it."""
import argparse
import json
from pathlib import Path

from generate import atomic_json
from history import connect
from ranking_policy import eligibility
from research import ROOT, artifact, import_generation, init, now, packed


def export(db,directory):
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'artifacts'):
        raise ValueError('Runtime candidates must be workspace artifacts')
    # Always create a new snapshot: a previously exported file must never survive
    # when its current page is held or its draft has become stale.
    directory.mkdir(parents=True,exist_ok=False)
    report=dict(createdAt=now(),directory=str(directory),exported=[],held=[],productionChanged=False)
    rows=db.execute('''SELECT v.* FROM research_metadata_versions v
        WHERE v.rowid=(SELECT MAX(n.rowid) FROM research_metadata_versions n WHERE n.pdf=v.pdf AND n.page=v.page)
        ORDER BY v.pdf,v.page''').fetchall()
    for row in rows:
        page=dict(sourcePdfId=row['pdf'],page=row['page'],version=row['id'],
                  rankingPolicy=eligibility(db,row['pdf'],row['page']))
        if row['status']!='validated_draft':
            report['held'].append(dict(page,reason='Latest version is '+row['status']))
            continue
        source=directory/'responses'/f'{row["pdf"]}-{row["page"]}.json'
        atomic_json(source,json.loads(row['payload']))
        try:
            result=import_generation(db,source,directory/'metadata')
        except ValueError as exc:
            report['held'].append(dict(page,reason=str(exc)))
        else:
            report['exported'].append(dict(page,status=result['status'],path=f'{row["pdf"]%1000:03d}/{row["pdf"]}/{row["page"]}.json'))
    report['exportedPages']=len(report['exported']);report['heldPages']=len(report['held'])
    manifest=directory/'manifest.json';atomic_json(manifest,report)
    report['manifestArtifact']=artifact(db,manifest,'runtime_candidate_manifest')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'artifacts/search-metadata/research.sqlite3')
    parser.add_argument('--directory',type=Path,required=True,help='New local snapshot directory; must not already exist')
    args=parser.parse_args()
    with connect(args.db) as db:
        init(db);print(packed(export(db,args.directory)))


if __name__=='__main__':
    try: main()
    except (ValueError,FileExistsError) as exc: raise SystemExit(str(exc))
