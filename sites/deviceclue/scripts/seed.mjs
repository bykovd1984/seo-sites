import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import { loadContent } from './content.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const rows = loadContent(root);
const filename = process.env.CONTENT_DB_PATH || path.join(root, 'data/content.sqlite');
fs.mkdirSync(path.dirname(filename), { recursive: true });
const db = new DatabaseSync(filename);
try {
  db.exec(fs.readFileSync(path.join(root, 'db/schema.sql'), 'utf8'));
  db.exec('BEGIN IMMEDIATE');
  try {
    db.exec('DELETE FROM articles');
    const statement = db.prepare('INSERT INTO articles VALUES (?, ?, ?, ?, ?)');
    for (const row of rows) statement.run(row.slug, JSON.stringify(row.metadata), row.body, row.searchText, row.order);
    db.exec('COMMIT');
  } catch (error) { db.exec('ROLLBACK'); throw error; }
  console.log(`Content snapshot ready: ${rows.length} articles.`);
} finally { db.close(); }
