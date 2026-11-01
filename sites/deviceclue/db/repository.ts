import { DatabaseSync } from 'node:sqlite';
import { normalizeText, normalizeQuery, escapeLike } from '../lib/content.ts';
import type { Article } from '../lib/types.ts';
export function openRepository(filename: string) {
  const db = new DatabaseSync(filename, { readOnly: true });
  db.exec('PRAGMA query_only = ON');
  const decode = (row: unknown): Article => {
    const record = row as { metadata_json: string; body_markdown: string };
    return { ...JSON.parse(record.metadata_json), bodyMarkdown: record.body_markdown };
  };
  return {
    all: () => db.prepare('SELECT * FROM articles ORDER BY sort_order').all().map(decode),
    find: (slug: string) => { const row = db.prepare('SELECT * FROM articles WHERE slug = ?').get(slug); return row ? decode(row) : null; },
    search: (input: unknown) => {
      const words = normalizeText(normalizeQuery(input)).split(/\s+/).filter(Boolean).slice(0, 12);
      if (!words.length) return [];
      const sql = `SELECT * FROM articles WHERE ${words.map(() => "search_text LIKE ? ESCAPE char(92)").join(' AND ')} ORDER BY sort_order LIMIT 30`;
      return db.prepare(sql).all(...words.map(word => `%${escapeLike(word)}%`)).map(decode);
    },
    count: () => Number(db.prepare('SELECT COUNT(*) AS n FROM articles').get()?.n),
    close: () => db.close(),
  };
}
