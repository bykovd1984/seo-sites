import fs from 'node:fs';
import path from 'node:path';
import { normalizeText } from '../lib/content.ts';
import { validatePublishAt } from '../lib/publication.ts';
export function loadContent(root) {
  const catalog = JSON.parse(fs.readFileSync(path.join(root, 'content/catalog.json'), 'utf8'));
  const seen = new Set();
  return catalog.map((entry, index) => {
    if (!/^[a-z0-9-]+$/.test(entry.slug) || seen.has(entry.slug)) throw new Error('Invalid or duplicate article slug');
    seen.add(entry.slug);
    validatePublishAt(entry.publishAt);
    if (!entry.title || !entry.answer || !entry.scope || !entry.sources?.length) throw new Error(`Incomplete metadata: ${entry.slug}`);
    for (const source of entry.sources) if (!source.url.startsWith('https://') || !source.title || !source.note) throw new Error(`Invalid source: ${entry.slug}`);
    const filename = path.resolve(root, 'content', entry.slug + '.md');
    const body = fs.readFileSync(filename, 'utf8');
    if (body.length < 1500 || !body.includes('## ')) throw new Error(`Incomplete article: ${entry.slug}`);
    if (/TODO|lorem ipsum|coming soon/i.test(body)) throw new Error(`Placeholder: ${entry.slug}`);
    const metadata = { ...entry, checkedDate: entry.checkedDate ?? '2026-11-01', readingMinutes: Math.max(3, Math.ceil(body.split(/\s+/).length / 190)) };
    return { slug: entry.slug, metadata, body, order: index, searchText: normalizeText([entry.title, entry.brand, entry.answer, entry.tags.join(' '), body].join(' ')) };
  });
}
