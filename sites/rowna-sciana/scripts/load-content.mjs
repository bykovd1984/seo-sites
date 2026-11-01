import fs from 'node:fs';
import path from 'node:path';
import { normalizeText } from '../lib/content.ts';

export function loadArticleSeeds(root, catalog) {
  const slugs = new Set();
  return catalog.map(entry => {
    if (!/^[a-z0-9-]+$/.test(entry.slug) || slugs.has(entry.slug)) throw new Error('Invalid or duplicate article slug.');
    slugs.add(entry.slug);
    const readContent = name => {
      const file = path.resolve(root, name);
      if (!file.startsWith(path.resolve(root, 'content') + path.sep)) throw new Error('Content path must stay inside content/.');
      return fs.readFileSync(file, 'utf8');
    };
    const seo = JSON.parse(readContent(entry.seoPath));
    if (seo.proposed_slug !== entry.slug) throw new Error(`Slug mismatch for ${entry.slug}.`);
    if (!/^\/images\/[a-z0-9-]+\.(png|webp|jpg)$/.test(entry.coverImage) || !fs.existsSync(path.join(root, 'public', entry.coverImage))) throw new Error(`Missing cover for ${entry.slug}.`);
    const body = readContent(entry.bodyPath).replaceAll('(assets/', '(/images/');
    const visible = body.replace(/!?\[([^\]]+)\]\([^)]+\)/g, '$1');
    const words = visible.match(/[\p{L}\p{N}]+(?:['’–-][\p{L}\p{N}]+)*/gu) ?? [];
    return [entry.slug, seo.h1, seo.meta_description, entry.category, JSON.stringify(entry.tags), body,
      entry.coverImage, entry.coverAlt, Math.max(1, Math.ceil(words.length / 200)),
      seo.source_checked_date ?? seo.prepared_date, seo.status, normalizeText(seo.h1 + ' ' + body)];
  });
}

export function buildUpsertSql(rows) {
  const columns = ['slug','title','description','category','tags_json','body_markdown','cover_image','cover_alt','reading_minutes','checked_date','review_status','search_text'];
  const quote = value => "'" + String(value).replaceAll("'", "''") + "'";
  return rows.map(values => `INSERT INTO articles (${columns.join(',')}) VALUES (${values.map(quote).join(',')}) ON CONFLICT(slug) DO UPDATE SET ${columns.slice(1).map(name => `${name}=excluded.${name}`).join(',')};`).join('\n') + '\n';
}
