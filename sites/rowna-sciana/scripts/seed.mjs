import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import { loadArticleSeeds, buildUpsertSql } from './load-content.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'content/catalog.json'), 'utf8'));
const rows = loadArticleSeeds(root, catalog); // Validate every article before opening the file.
const filename = process.env.CONTENT_DB_PATH || path.join(root, 'data/content.sqlite');
fs.mkdirSync(path.dirname(filename), { recursive: true });
const db = new DatabaseSync(filename);
try {
  db.exec(fs.readFileSync(path.join(root, 'db/schema.sql'), 'utf8'));
  db.exec('BEGIN IMMEDIATE');
  try {
    db.exec(buildUpsertSql(rows));
    const placeholders = rows.map(() => '?').join(',');
    if (!placeholders) throw new Error('Refusing an empty content snapshot');
    db.prepare(`DELETE FROM articles WHERE slug NOT IN (${placeholders})`).run(...rows.map(r => r[0]));
    db.exec('COMMIT');
  } catch (error) { db.exec('ROLLBACK'); throw error; }
  console.log(`Content snapshot ready: ${db.prepare('SELECT count(*) AS n FROM articles').get().n} articles.`);
} finally { db.close(); }
