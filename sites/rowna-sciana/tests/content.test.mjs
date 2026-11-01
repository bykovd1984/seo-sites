import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { normalizeText, normalizeQuery, escapeLike, safeHref, parseMarkdown } from '../lib/content.ts';

test('Polish search works without diacritics and treats SQL wildcards literally', () => {
  assert.equal(normalizeText('ŚCIANA, gładź i TAŚMA'), 'sciana, gladz i tasma');
  assert.equal(normalizeQuery(['unexpected']), '');
  assert.equal(normalizeQuery('  taśma   farba '), 'taśma farba');
  assert.equal(normalizeQuery('a'.repeat(200)).length, 100);
  assert.equal(escapeLike('100%_\\'), '100\\%\\_\\\\');
});
test('unsupported URI schemes and protocol-relative destinations are rejected', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,bad', '//evil.test', 'http://untrusted.test', 'not a url']) assert.equal(safeHref(value), null);
  assert.equal(safeHref('https://manufacturer.test/data.pdf#page=4'), 'https://manufacturer.test/data.pdf#page=4');
  assert.equal(safeHref('/poradniki/test'), '/poradniki/test');
});
test('real article keeps both images, tables, distinct headings and source disclosures', () => {
  const source = fs.readFileSync(new URL('../content/article.pl.md', import.meta.url), 'utf8').replaceAll('(assets/', '(/images/');
  const blocks = parseMarkdown(source);
  assert.equal(blocks.filter(b => b.type === 'image').length, 2);
  assert.equal(blocks.filter(b => b.type === 'table').length, 2);
  const headings = blocks.filter(b => b.type === 'heading');
  assert.equal(new Set(headings.map(h => h.id)).size, headings.length);
  assert(headings.some(h => h.id === 'najpierw-sprawdz-co-odeszlo-razem-z-tasma'));
  const ids = new Set(headings.map(h => h.id));
  for (const [, anchor] of source.matchAll(/\]\(#([a-z0-9-]+)\)/g)) assert(ids.has(anchor), `Missing article section: ${anchor}`);
  for (const anchor of ['a-odszedl-cienki-platek-farby', 'b-oderwalo-sie-kilka-warstw', 'c-oderwal-sie-fragment-podloza']) assert(ids.has(anchor));
  assert(blocks.some(b => b.type === 'paragraph' && b.text.includes('Ilustracja wygenerowana z pomocą AI')));
  assert(blocks.filter(b => b.type === 'table').every(b => !b.rows.flat().some(cell => /^-+$/.test(cell))));
});
test('duplicate headings get stable IDs and arbitrary image sources are not embedded', () => {
  const result = parseMarkdown('## Ściana\n\n## Ściana\n\n![x](https://external.test/tracker.png)');
  assert.deepEqual(result.map(b => b.id), ['sciana', 'sciana-2']);
});
