"""Reconcile discovered manual pages with the current draft or next processing step."""
from collections import Counter
import json

from model_stage import page_bundle, SourceTextUnavailable
from ranking_policy import eligibility
from research import GENERATOR, now, packed


def observed_pages(db, start, end):
    dates = db.execute('''SELECT pdf, page, MAX(end) AS last_seen FROM (
        SELECT d.pdf, d.page, i.end FROM research_discovered_pages d
        JOIN research_inventory i ON i.id=d.inventory_id WHERE i.start>=? AND i.end<=?
        UNION ALL SELECT pdf, page, end FROM research_page_rankings WHERE start>=? AND end<=?
        UNION ALL SELECT pdf, page, end FROM research_windows WHERE start>=? AND end<=?
    ) GROUP BY pdf, page''', (start, end)*3)
    latest = {(r['pdf'], r['page']): r['last_seen'] for r in dates}
    for report in db.execute('SELECT end,payload FROM research_inventory_ui_observations WHERE start>=? AND end<=?',
                             (start, end)):
        for row in json.loads(report['payload'])['pages']:
            if row.get('sourcePdfId') is None:
                continue
            page = (row['sourcePdfId'], row['page'])
            latest[page] = max(latest.get(page, ''), report['end'])
    # Stable ID ordering for observations on the same date.
    return sorted(sorted(latest.items()), key=lambda item: item[1], reverse=True)


def page_outcome(db, pdf, page):
    rank = eligibility(db, pdf, page)
    outcome = dict(eligible=rank['eligible'], rankingEvidence=rank['observations'])
    if not rank['eligible']:
        return dict(outcome, state='excluded', reason=rank['reason'])
    has_report = db.execute('SELECT 1 FROM research_windows WHERE pdf=? AND page=? LIMIT 1', (pdf,page)).fetchone()
    if not has_report:
        return dict(outcome, state='pending', reason='page_search_report_missing')
    try:
        request = page_bundle(db, pdf, page)
    except SourceTextUnavailable as exc:
        return dict(outcome,state='skipped',reason=exc.reason,sourceEvidence=exc.proof,
                    followUp='Image/OCR review is required before text-grounded metadata can be generated.')
    except ValueError as exc:
        return dict(outcome, state='pending', reason=str(exc))
    version = db.execute('''SELECT id,status FROM research_metadata_versions
        WHERE request_id=? AND model=? AND effort=? ORDER BY created DESC,rowid DESC LIMIT 1''',
        (request['requestId'], *GENERATOR)).fetchone()
    outcome['requestId'] = request['requestId']
    if version is None:
        status=db.execute('SELECT status FROM research_requests WHERE id=?',(request['requestId'],)).fetchone()[0]
        return dict(outcome, state='pending', reason=status if status!='pending' else 'ready_for_generation')
    if version['status'] == 'validated_draft':
        return dict(outcome, state='validated_draft', reason=None, versionId=version['id'])
    return dict(outcome, state='pending', reason=version['status'], versionId=version['id'])


def reconcile(db, start, end):
    if start > end:
        raise ValueError('Invalid observation period')
    start, end = str(start), str(end)
    db.execute('''CREATE TABLE IF NOT EXISTS research_period_outcomes (
        start TEXT, end TEXT, pdf INTEGER, page INTEGER, last_seen TEXT NOT NULL,
        eligible INTEGER NOT NULL, state TEXT NOT NULL, reason TEXT, detail TEXT NOT NULL,
        assessed_at TEXT NOT NULL, PRIMARY KEY(start,end,pdf,page))''')
    pages = observed_pages(db, start, end)
    assessed = now()
    counts, reasons = Counter(), Counter()
    with db:
        db.execute('DELETE FROM research_period_outcomes WHERE start=? AND end=?', (start,end))
        for (pdf,page), last_seen in pages:
            result = page_outcome(db, pdf, page)
            db.execute('INSERT INTO research_period_outcomes VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (start,end,pdf,page,last_seen,result['eligible'],result['state'],
                        result['reason'],packed(result),assessed))
            counts[result['state']] += 1
            if result['reason']:
                reasons[result['reason']] += 1
    return dict(start=start, end=end, savedPages=len(pages), states=dict(counts),
                reasons=dict(reasons), assessedAt=assessed, model=GENERATOR[0], effort=GENERATOR[1],
                scope='Currently stored provider observations. Pending rows require follow-up.')
