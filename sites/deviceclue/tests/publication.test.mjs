import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { loadContent } from '../scripts/content.mjs';
import { openRepository } from '../db/repository.ts';
import { validatePublishAt } from '../lib/publication.ts';
import { parseMarkdown, publishedHref } from '../lib/content.ts';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const rows = loadContent(root);
const scheduled = rows.filter(row => row.metadata.publishAt).sort((a, b) => a.metadata.publishAt.localeCompare(b.metadata.publishAt));

test('fifty-five consecutive releases are at 09:00 Kyiv, starting 2 November', () => {
  assert.equal(scheduled.length, 55);
  const formatter = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Kyiv', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  for (let i = 0; i < scheduled.length; i++) {
    const date = new Date(scheduled[i].metadata.publishAt);
    assert.equal(date.getTime(), Date.parse('2026-11-02T07:00:00.000Z') + i * 86_400_000);
    assert.ok(formatter.format(date).endsWith(', 09:00'));
    if (i) assert.equal(date - new Date(scheduled[i - 1].metadata.publishAt), 86_400_000);
  }
});

test('all public query paths release exactly one article at each boundary without reconnecting', () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'deviceclue-publication-'));
  const filename = path.join(folder, 'content.sqlite');
  try {
    const db = new DatabaseSync(filename);
    db.exec(fs.readFileSync(path.join(root, 'db/schema.sql'), 'utf8'));
    const insert = db.prepare('INSERT INTO articles VALUES (?, ?, ?, ?, ?)');
    for (const row of rows) insert.run(row.slug, JSON.stringify(row.metadata), row.body, row.searchText, row.order);
    db.close();
    let current = new Date('2026-11-01T12:00:00.000Z');
    const repo = openRepository(filename, () => current);
    try {
      assert.equal(repo.count(), 10);
      for (let i = 0; i < scheduled.length; i++) {
        const target = scheduled[i];
        const timestamp = Date.parse(target.metadata.publishAt);
        current = new Date(timestamp - 1);
        assert.equal(repo.count(), 10 + i);
        assert.equal(repo.find(target.slug), null);
        assert.ok(!repo.all().some(a => a.slug === target.slug));
        assert.ok(!repo.search(target.metadata.brand).some(a => a.slug === target.slug));
        let available = new Set(repo.all().map(a => a.slug));
        assert.equal(publishedHref('/guides/' + target.slug, available), null);
        current = new Date(timestamp);
        assert.equal(repo.count(), 11 + i);
        assert.equal(repo.all().length, 11 + i);
        assert.equal(repo.find(target.slug)?.publishAt, target.metadata.publishAt);
        assert.ok(repo.search(target.metadata.brand).some(a => a.slug === target.slug));
        available = new Set(repo.all().map(a => a.slug));
        assert.equal(publishedHref('/guides/' + target.slug, available), '/guides/' + target.slug);
        for (const future of scheduled.slice(i + 1)) {
          assert.equal(repo.find(future.slug), null);
          assert.ok(!repo.search(future.metadata.brand).some(a => a.slug === future.slug));
        }
      }
    } finally { repo.close(); }
  } finally { fs.rmSync(folder, { recursive: true, force: true }); }
});

test('invalid, ambiguous and noncanonical publication timestamps cannot enter a content snapshot', () => {
  for (const value of [null, '', 123, 'tomorrow', '2026-11-02', '2026-11-02T09:00:00+02:00', '2026-11-02T07:00:00Z', '2026-02-30T07:00:00.000Z', '2026-11-02T25:00:00.000Z']) {
    assert.throws(() => validatePublishAt(value), /publishAt/);
  }
  validatePublishAt(undefined);
  validatePublishAt('2026-11-02T07:00:00.000Z');
});

test('numbered procedures preserve their list structure; internal links respect publication availability', () => {
  const parsed = parseMarkdown('1. Identify the model.\n2. Follow its controls.');
  assert.equal(parsed[0].type, 'list');
  assert.equal(parsed[0].ordered, true);
  assert.equal(parsed[0].items.length, 2);
  const published = new Set(['zanussi-oven-clock']);
  assert.equal(publishedHref('/guides/zanussi-oven-clock', published), '/guides/zanussi-oven-clock');
  for (const href of ['/guides/aeg-oven-symbols', '/guides/aeg-oven-symbols#grill', 'https://deviceclue.site/guides/aeg-oven-symbols']) assert.equal(publishedHref(href, published), null);
  assert.equal(publishedHref('https://support.zanussi.co.uk/', published), 'https://support.zanussi.co.uk/');
  assert.equal(publishedHref('javascript:alert(1)', published), null);
});
