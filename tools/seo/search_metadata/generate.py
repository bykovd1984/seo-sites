"""Conservative generation: search demand ranks topics that actually occur on the page."""
import base64
import datetime as dt
import html
import json
import math
import os
import re
import tempfile
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

from history import digest, evidence, watermark

STOP = set('a an and are as at be by for from how i in is it manual of on or the to user with you your instructions guide page'.split())
WORD = re.compile(r'[^\W_]+(?:[-.][^\W_]+)*', re.UNICODE)


def tokens(text):
    values = []
    for word in WORD.findall(unicodedata.normalize('NFKC', text).casefold()):
        if word in STOP: continue
        if word.startswith('scann') or word == 'scan': word = 'scan'
        elif word.startswith('configur'): word = 'configure'
        elif word.endswith('ing') and len(word) > 6: word = word[:-3]
        elif word.endswith('s') and len(word) > 4: word = word[:-1]
        values.append(word)
    return set(values)


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore = 0; self.text = []; self.heading = []; self.heading_depth = 0; self.headings = []

    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'script'): self.ignore += 1
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.heading_depth += 1

    def handle_endtag(self, tag):
        if tag in ('style', 'script'): self.ignore = max(0, self.ignore-1)
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') and self.heading_depth:
            self.headings.append(' '.join(self.heading)); self.heading = []; self.heading_depth -= 1
        if tag in ('p', 'div', 'main', 'li', 'td', 'tr', 'h1', 'h2', 'h3'): self.text.append(' ')

    def handle_data(self, data):
        if not self.ignore:
            self.text.append(data + ' ')
            if self.heading_depth: self.heading.append(data)


def plain(text):
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def safe(text, limit):
    return bool(text) and len(text) <= limit and not any(unicodedata.category(c) in ('Cc','Cs') or c in '<>' for c in text)


def propose(context, rows, skipped):
    raw = base64.b64decode(context['rawHtmlBase64'], validate=True).decode('utf-8-sig')
    parser = PageText(); parser.feed(raw)
    content = plain(' '.join(parser.text)); body_tokens = tokens(content)
    brand = plain(context['brand'])
    models = [plain(m) for m in context['models'] if plain(m)]
    result = dict(sourcePdfId=context['sourcePdfId'], page=context['page'], status='needs_content_review',
                  skippedOverlappingWindows=skipped, generatorVersion='search-topics-v1')
    if not safe(brand, 80) or not models or not safe(models[0], 80): return {**result, 'reason': 'Missing product identity'}
    if not body_tokens: return {**result, 'reason': 'No text layer'}
    identities = tokens(' '.join([brand, *models]))
    compact_models = [''.join(c.casefold() for c in model if c.isalnum()) for model in models]
    headings = []
    for text in [*(context.get('headings') or []), *parser.headings]:
        text = plain(text)
        # Keep source numbers: capacities and model numbers are meaningful parts of a title.
        if not safe(text, 120) or len(text) < 5 or len(text.split()) > 15: continue
        if re.match(r'^(?:note|warning|caution|danger|copyright)\b', text, re.I): continue
        if text.endswith(('.', '!', '?')) or not tokens(text) <= body_tokens: continue
        if text not in headings: headings.append(text)
    candidates = []
    for row in rows:
        if row['clicks'] <= 0 or row['impressions'] < 5: continue
        query_words = tokens(row['query'])
        numeric = [w for w in query_words if any(c.isdigit() for c in w)]
        if any(not any(''.join(c for c in w if c.isalnum()) in model for model in compact_models) and w not in body_tokens for w in numeric): continue
        intent = query_words - identities - set(numeric) - {'printer', 'pdf'}
        if not intent or len(intent & body_tokens) / len(intent) < .6: continue
        for heading in headings:
            shared = tokens(heading) & intent
            if not shared: continue
            score = len(shared) / len(intent) + min(1, math.log1p(row['clicks'])/5)
            candidates.append((row['end'], score, row['clicks'], heading, row))
        # The SEO path can also work when both heading parsers miss a topic. Only use a
        # short query phrase that occurs verbatim in the page, after removing product terms.
        topic_words = [word for word in WORD.findall(row['query']) if tokens(word) & intent]
        phrase = ' '.join(topic_words)
        normalized_body = ' '.join(WORD.findall(content.casefold()))
        if 2 <= len(topic_words) <= 7 and (' '+phrase.casefold()+' ') in (' '+normalized_body+' ') and safe(phrase,120):
            acronyms = {'ip':'IP', 'usb':'USB', 'hdmi':'HDMI', 'dhcp':'DHCP'}
            topic = ' '.join(acronyms.get(word.casefold(),word) for word in topic_words)
            topic = topic[0].upper()+topic[1:]
            candidates.append((row['end'], .95+min(1,math.log1p(row['clicks'])/5), row['clicks'], topic, row))
    if not candidates: return {**result, 'reason': 'No clicked query with a verified matching page topic'}
    _, score, _, topic, top = max(candidates, key=lambda x: x[:3])
    compact_query = ''.join(c.casefold() for c in top['query'] if c.isalnum())
    matching_models = [model for model, compact in zip(models, compact_models) if compact in compact_query]
    identity = plain(brand + ' ' + (max(matching_models, key=len) if matching_models else models[0]))
    title = identity + ': ' + topic
    if not all((safe(title, 160), safe(title, 180))): return {**result, 'reason': 'Title too long; requires editing'}
    description = f'See {topic} in the {identity} manual, page {context["page"]}.'
    if not safe(description, 320): return {**result, 'reason': 'Description requires editing'}
    metadata = dict(schemaVersion=1, status='active', sourcePdfId=context['sourcePdfId'], page=context['page'],
        contentSha256=digest(raw), pageTitle=title, h1Heading=title, pageDescription=description,
        evidenceThrough=top['end']+'T00:00:00Z')
    return {**result, 'status': 'active', 'metadata': metadata, 'topic': topic, 'selectedQuery': top,
            'reason': 'Clicked query and selected topic both supported by source page text', 'matchScore': score,
            'providerEvidence': {engine: [r for r in rows if r['engine']==engine] for engine in ('google', 'bing')}}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, separators=(',', ':')); file.flush(); os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def generate(db, contexts, output, requested=None):
    items = [json.loads(line) for line in contexts.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    items = [item for item in items if item.get('type','seo_context') == 'seo_context']
    prepared = []
    for context in items:
        if type(context['sourcePdfId']) is not int or not 0 < context['sourcePdfId'] < 2**63 or type(context['page']) is not int or not 0 < context['page'] <= 65535:
            raise ValueError('Invalid context page identity')
        revision = watermark(db, context['sourcePdfId'], context['page'])
        rows, skipped = evidence(db, context['sourcePdfId'], context['page'])
        prepared.append((max((r['end'] for r in rows), default=''), context, rows, skipped, revision))
    report = []
    for _, context, rows, skipped, revision in sorted(prepared, key=lambda x: x[0], reverse=True):
        proposal = propose(context, rows, skipped)
        if proposal['status'] == 'active':
            metadata = proposal['metadata']; pdf = metadata['sourcePdfId']
            metadata['evidenceRevision'] = revision
            destination = output / f'{pdf%1000:03d}' / str(pdf) / f'{metadata["page"]}.json'
            try: previous = json.loads(destination.read_text(encoding='utf-8')) if destination.exists() else None
            except json.JSONDecodeError: previous = None
            if previous and (previous['evidenceThrough'], previous.get('evidenceRevision',0)) > (metadata['evidenceThrough'], revision):
                proposal['status'] = 'skipped_older_than_published'
            else: atomic_json(destination, metadata)
        with db:
            db.execute('INSERT OR REPLACE INTO proposals VALUES (?,?,?,?,?,?)', (context['sourcePdfId'], context['page'],
                dt.datetime.now(dt.timezone.utc).isoformat(), proposal['status'], json.dumps(proposal, ensure_ascii=False),
                revision))
        report.append({k:v for k,v in proposal.items() if k!='providerEvidence'})
    found = {(c['sourcePdfId'],c['page']) for c in items}
    for item in requested or []:
        pdf, page = item['sourcePdfId'], item['page']
        if (pdf,page) in found: continue
        proposal = dict(sourcePdfId=pdf,page=page,status='needs_context',reason='No current source page/product context exported')
        with db:
            db.execute('INSERT OR REPLACE INTO proposals VALUES (?,?,?,?,?,?)', (pdf,page,dt.datetime.now(dt.timezone.utc).isoformat(),
                proposal['status'],json.dumps(proposal),watermark(db,pdf,page)))
        report.append(proposal)
    atomic_json(output.parent / 'generation-report.json', report)
    print(json.dumps({'processed': len(report), 'active': sum(p['status']=='active' for p in report),
                      'review': sum(p['status']=='needs_content_review' for p in report), 'missing_context': sum(p['status']=='needs_context' for p in report)}))
