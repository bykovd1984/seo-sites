import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import { loadArticleSeeds, buildUpsertSql } from '../scripts/load-content.mjs';
import { parseMarkdown, safeHref } from '../lib/content.ts';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'content/catalog.json'), 'utf8'));

test('catalog import round-trips all articles and updates without duplicates', () => {
  const rows = loadArticleSeeds(root, catalog);
  const db = new DatabaseSync(':memory:');
  try {
    db.exec('CREATE TABLE articles (slug TEXT PRIMARY KEY, title TEXT, description TEXT, category TEXT, tags_json TEXT, body_markdown TEXT, cover_image TEXT, cover_alt TEXT, reading_minutes INTEGER, checked_date TEXT, review_status TEXT, search_text TEXT)');
    db.exec(buildUpsertSql(rows));
    db.exec(buildUpsertSql(rows));
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM articles').get().n, catalog.length);
    for (const row of rows) {
      const saved = db.prepare('SELECT body_markdown, cover_image FROM articles WHERE slug = ?').get(row[0]);
      assert.equal(saved.body_markdown, row[5]);
      assert.equal(saved.cover_image, row[6]);
    }
    assert.equal(new Set(catalog.map(e => e.checklistStorageKey)).size, catalog.length);
  } finally { db.close(); }
});

test('article navigation targets and local assets resolve across the catalog', () => {
  const slugs = new Set(catalog.map(e => e.slug));
  for (const row of loadArticleSeeds(root, catalog)) {
    const body = row[5];
    const blocks = parseMarkdown(body);
    const headings = new Set(blocks.filter(b => b.type === 'heading').map(h => h.id));
    for (const [, href] of body.matchAll(/(?<!!)\[[^\]]+\]\(([^)]+)\)/g)) {
      assert(safeHref(href), `Unsupported link in ${row[0]}: ${href}`);
      if (href.startsWith('#')) assert(headings.has(href.slice(1)));
      if (href.startsWith('/poradniki/')) assert(slugs.has(href.split('/')[2]));
    }
    for (const block of blocks.filter(b => b.type === 'image')) assert(fs.existsSync(path.join(root, 'public', block.src)), `Missing ${block.src}`);
    assert.equal(blocks.filter(b => b.type === 'image').length, 2);
  }
  for (const [slug, componentPath] of [
    ['smugi-na-suficie-po-malowaniu', 'components/ceiling-guide.tsx'],
    ['smugi-na-scianie-po-malowaniu', 'components/wall-guide.tsx'],
    ['farba-odchodzi-przy-malowaniu-walkiem', 'components/roller-guide.tsx'],
    ['akryl-przed-czy-po-malowaniu', 'components/acrylic-guide.tsx'],
    ['odpylanie-scian-po-szlifowaniu', 'components/dust-guide.tsx'],
    ['farba-na-plamy-i-zacieki', 'components/stain-guide.tsx'],
    ['ile-schnie-farba-na-scianie', 'components/drying-guide.tsx'],
  ]) {
    const article = catalog.find(e => e.slug === slug);
    const sections = new Set(parseMarkdown(fs.readFileSync(path.join(root, article.bodyPath), 'utf8')).filter(b => b.type === 'heading').map(h => h.id));
    const component = fs.readFileSync(path.join(root, componentPath), 'utf8');
    for (const [, anchor] of component.matchAll(/anchor: "([^"]+)"/g)) assert(sections.has(anchor), `Missing diagram destination ${anchor}`);
  }
});

test('invalid content configuration fails before database import', () => {
  assert.throws(() => loadArticleSeeds(root, [catalog[0], catalog[0]]), /duplicate/);
  assert.throws(() => loadArticleSeeds(root, [{ ...catalog[0], slug: 'mismatched-slug' }]), /mismatch/);
  assert.throws(() => loadArticleSeeds(root, [{ ...catalog[0], bodyPath: '../outside.md' }]), /inside content/);
});
