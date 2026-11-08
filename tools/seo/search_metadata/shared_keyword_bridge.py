"""Import completed shared-broker UI evidence at a metadata generation boundary."""
import argparse
import hashlib
import json
import sqlite3
from contextlib import closing, nullcontext
from pathlib import Path

from archive_catalog import ensure_no_adoption
from research import ROOT, key, now, packed, refresh_stage
from ranking_policy import eligibility
from semrush_workflow import add_job, context
from toolspd import ingest_snapshot, parse_snapshot


def read_plan(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT / 'artifacts') or path.stat().st_size > 1024 * 1024:
        raise ValueError('Use a bounded saved plan inside workspace artifacts')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if key({k: v for k, v in value.items() if k != 'manifestSha256'}) != value.get('manifestSha256'):
        raise ValueError('Shared keyword plan integrity mismatch')
    if value.get('schemaVersion') != 1 or value.get('project') != 'manualsdump' or value.get('publicationAllowed') is not False:
        raise ValueError('Expected a draft-only ManualsDump shared keyword plan')
    if not isinstance(value.get('reports'), list) or not 1 <= len(value['reports']) <= 20:
        raise ValueError('Expected1..20 captured reports')
    return value


def validate(db, hub, period, plan):
    """Validate everything before the first write; never request a provider."""
    if key({k: v for k, v in plan.items() if k != 'manifestSha256'}) != plan.get('manifestSha256'):
        raise ValueError('Shared keyword plan integrity mismatch')
    ensure_no_adoption(db)
    epoch = db.execute('SELECT status FROM research_archive_periods WHERE id=?', (period,)).fetchone()
    active = db.execute("SELECT value FROM research_settings WHERE name='archive_active_period'").fetchone()
    inferred_initial = not active and db.execute("SELECT count(*) FROM research_archive_periods WHERE status='indexed'").fetchone()[0] == 1
    if not epoch or epoch['status'] != 'indexed' or not (inferred_initial or active and json.loads(active['value']) == period):
        raise ValueError('Select the current indexed archive period')
    pdf, page = plan['sourcePdfId'], plan['page']
    target = db.execute('SELECT * FROM research_archive_pages WHERE period_id=? AND pdf=? AND page=?', (period, pdf, page)).fetchone()
    if not target or target['url'] != plan['url']:
        raise ValueError('Shared keyword target differs from the active archive page')
    if not target['eligible'] or not eligibility(db, pdf, page)['eligible']:
        return dict(state='held', reason='ranking_protection'), []
    current = db.execute('SELECT content_id,stage FROM research_pages WHERE pdf=? AND page=?', (pdf, page)).fetchone()
    if not current or not current['content_id'] or current['stage'] == 'identity_review' or target['state'] == 'skipped':
        return dict(state='held', reason='source_requires_review'), []
    sha, text = context(db, pdf, page)
    if sha != plan['contentSha256'] or hashlib.sha256(text.encode()).hexdigest() != plan['sourceTextSha256']:
        return dict(state='held', reason='source_content_changed'), []
    query = plan['queryProvenance']
    window = db.execute('''SELECT 1 FROM research_windows w JOIN research_queries q ON q.window_id=w.id
        WHERE w.pdf=? AND w.page=? AND w.engine=? AND w.start<=? AND w.end>=? AND q.query=?
          AND json_extract(w.payload,'$.verified.url')=? LIMIT 1''',
        (pdf, page, query['provider'], query['date'], query['date'], query['keyword'], plan['url'])).fetchone()
    if not target['history_imported'] or not window:
        return dict(state='held', reason='query_history_not_adopted'), []
    seed_proof = plan['contentSeedProvenance']
    if seed_proof['verbatimSource'] not in text:
        raise ValueError('Content seed lacks its exact source quotation')
    job = hub.execute('SELECT * FROM jobs WHERE id=? AND project=?', (plan['sharedJobId'], 'manualsdump')).fetchone()
    if not job or job['kind'] != 'keywords' or job['state'] != 'done':
        raise ValueError('Shared keyword job is not completed')
    request = json.loads(job['request'])
    if request['subject'] != plan['subjectId']:
        raise ValueError('Shared job subject mismatch')
    subject = hub.execute('SELECT payload FROM subjects WHERE id=? AND project=?', (plan['subjectId'], 'manualsdump')).fetchone()
    subject = json.loads(subject['payload']) if subject else {}
    if subject.get('url') != plan['url'] or subject.get('text') != text:
        raise ValueError('Shared subject differs from the exact page text')
    captured, seen = [], set()
    for report in plan['reports']:
        legacy = report['request']
        if report['seed'] in seen or legacy != dict(method='toolspd_keywordmagic', keyword=report['seed'],
                country=request['country'], month=request['requestedMonth'], limit=request['limit']):
            raise ValueError('Duplicate seed or shared report request mismatch')
        seen.add(report['seed'])
        if report['seed'] not in request['keywords'] or report['seed'] not in (query['keyword'], seed_proof['keyword']):
            raise ValueError('Report seed lacks query/content provenance')
        stored = hub.execute('''SELECT r.* FROM keyword_reports r JOIN keyword_links l ON l.report=r.id
            WHERE r.id=? AND l.project=? AND l.subject=? AND l.seed=?''',
            (report['hubReportId'], 'manualsdump', plan['subjectId'], report['seed'])).fetchone()
        if not stored or stored['artifact'] != report['hubEvidenceId']:
            raise ValueError('Missing shared keyword report link')
        shared_request = json.loads(stored['request'])
        if any(shared_request[k] != request[k] for k in ('country', 'language', 'limit')) or shared_request['keyword'] != report['seed'] or shared_request['month'] != legacy['month']:
            raise ValueError('Shared stored report scope mismatch')
        snapshot_path = Path(report['snapshotPath']).resolve()
        if not snapshot_path.is_relative_to(ROOT / 'artifacts') or snapshot_path.stat().st_size > 2 * 1024**2:
            raise ValueError('Snapshot is outside bounded workspace evidence')
        data = snapshot_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != report['snapshotSha256']:
            raise ValueError('Snapshot file integrity mismatch')
        snapshot = json.loads(data.decode('utf-8-sig'))
        parsed = parse_snapshot(legacy, snapshot, report['origin'])
        if key(snapshot) != stored['artifact'] or parsed != json.loads(stored['result']) or len(parsed) != report['candidates']:
            raise ValueError('Snapshot differs from the saved shared report')
        previous = db.execute('SELECT * FROM semrush_jobs WHERE id=?', (key(legacy),)).fetchone()
        if previous and (previous['status'] not in ('planned', 'done') or
                previous['status'] == 'done' and (previous['artifact_id'] != report['snapshotSha256'] or json.loads(previous['result']) != parsed)):
            raise ValueError('Existing legacy job is uncertain or has different evidence')
        captured.append((report, parsed))
    if seen != set(request['keywords']):
        raise ValueError('The completed shared job reports are incomplete')
    return dict(state='ready', sourcePdfId=pdf, page=page, reports=len(captured), candidates=sum(len(p) for _, p in captured)), captured


def import_plan(db, hub, period, plan):
    result, captured = validate(db, hub, period, plan)
    if result['state'] != 'ready':
        return result
    pdf, page, ident = plan['sourcePdfId'], plan['page'], plan['manifestSha256']
    prior = db.execute("SELECT 1 FROM research_events WHERE event='shared_semrush_imported' AND pdf=? AND page=? AND json_extract(payload,'$.plan')=? AND json_extract(payload,'$.period')=?", (pdf, page, ident, period)).fetchone()
    if prior:
        return dict(result, state='already_imported')
    # Mark the current outcome stale in the same transaction as the first report.
    # ingest_snapshot commits locally; a partial import therefore remains pending.
    db.execute("UPDATE research_archive_pages SET state='pending',reason='shared_keyword_evidence_added',updated=? WHERE period_id=? AND pdf=? AND page=?", (now(), period, pdf, page))
    for report, _ in captured:
        request = report['request']
        add_job(db, request, pdf, page, plan['contentSha256'], report['seed'], plan['queryProvenance']['date'], 0)
        provenance = plan['queryProvenance'] if report['seed'] == plan['queryProvenance']['keyword'] else plan['contentSeedProvenance']
        db.execute('INSERT OR IGNORE INTO semrush_seed_sources VALUES (?,?,?,?,?,?,?)',
            (key(request), pdf, page, plan['contentSha256'], report['seed'], provenance['role'], packed(dict(provenance, sharedJobId=plan['sharedJobId'], importPlan=ident))))
        ingest_snapshot(db, key(request), report['snapshotPath'], report['origin'])
    refresh_stage(db, pdf, page)
    db.execute('INSERT INTO research_events(created,pdf,page,event,payload) VALUES (?,?,?,?,?)',
        (now(), pdf, page, 'shared_semrush_imported', packed(dict(plan=ident, period=period, sharedJobId=plan['sharedJobId'], candidates=result['candidates']))))
    db.commit()
    return dict(result, state='imported', modelReviewRequired=True, providerRequestsMade=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'artifacts/search-metadata/research.sqlite3')
    parser.add_argument('--hub-db', type=Path, default=ROOT / 'artifacts/seo-research/research.sqlite3')
    parser.add_argument('--period', required=True)
    parser.add_argument('--plans', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    folder = args.plans.resolve()
    if not folder.is_relative_to(ROOT / 'artifacts'):
        raise ValueError('Plans must be saved under workspace artifacts')
    plans = [read_plan(p) for p in sorted(folder.glob('*-import-plan.json'))]
    if len(plans) > 100:
        raise ValueError('Use at most100 staged plans per invocation')
    from research_hub.worker import worker_lock
    generation = ROOT / 'artifacts/search-metadata/codex-generation'
    if not args.dry_run:
        generation.mkdir(parents=True, exist_ok=True)
    with (nullcontext(True) if args.dry_run else worker_lock(generation)) as acquired:
        if not acquired:
            raise ValueError('Another generation or reconciliation is active; import between batches')
        with closing(sqlite3.connect(args.db.resolve().as_uri() + ('?mode=ro' if args.dry_run else '?mode=rw'), uri=True, timeout=30)) as db, \
                closing(sqlite3.connect(args.hub_db.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)) as hub:
            db.row_factory = hub.row_factory = sqlite3.Row
            hub.execute('BEGIN')
            results = [validate(db, hub, args.period, p)[0] if args.dry_run else import_plan(db, hub, args.period, p) for p in plans]
    print(packed(dict(results=results, dryRun=args.dry_run, providerRequestsMade=0, modelCallsMade=0, publicationAllowed=False)))


if __name__ == '__main__':
    main()
