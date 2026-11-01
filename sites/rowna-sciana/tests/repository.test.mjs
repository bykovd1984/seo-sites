import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { openArticleRepository } from '../db/repository.ts';
import { loadArticleSeeds, buildUpsertSql } from '../scripts/load-content.mjs';

test('VPS SQLite repository reads all ten articles and keeps user queries parameterized', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'rowna-sqlite-'));
  const filename = path.join(temp, 'content.sqlite');
  const catalog = JSON.parse(fs.readFileSync('content/catalog.json', 'utf8'));
  const writer = new DatabaseSync(filename);
  writer.exec(fs.readFileSync('db/schema.sql', 'utf8'));
  writer.exec(buildUpsertSql(loadArticleSeeds(process.cwd(), catalog)));
  writer.close();
  const repository = openArticleRepository(filename);
  try {
    assert.equal(repository.count(), catalog.length);
    assert.equal(repository.all().length, catalog.length);
    for (const article of repository.all()) {
      assert.equal(repository.find(article.slug).bodyMarkdown, article.bodyMarkdown);
      assert(article.coverImage.startsWith('/images/'));
    }
    assert.equal(repository.search('ile schnie farba na scianie')[0].slug, 'ile-schnie-farba-na-scianie');
    assert.equal(repository.search('%%%').length, 0);
    assert.equal(repository.search("' OR 1=1 --").length, 0);
    assert.equal(repository.find("' OR 1=1 --"), null);
  } finally { repository.close(); fs.rmSync(temp, { recursive: true, force: true }); }
});
