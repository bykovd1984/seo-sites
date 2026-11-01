import { DatabaseSync } from "node:sqlite";
import { normalizeQuery, escapeLike } from "../lib/content.ts";

export type Article = {
  slug: string; title: string; description: string; category: string;
  tagsJson: string; bodyMarkdown: string; coverImage: string; coverAlt: string;
  readingMinutes: number; checkedDate: string; reviewStatus: string;
};
const columns = `slug, title, description, category, tags_json AS tagsJson,
 body_markdown AS bodyMarkdown, cover_image AS coverImage, cover_alt AS coverAlt,
 reading_minutes AS readingMinutes, checked_date AS checkedDate, review_status AS reviewStatus`;

export function openArticleRepository(filename: string) {
  const db = new DatabaseSync(filename, { readOnly: true });
  db.exec("PRAGMA query_only = ON");
  return {
    all: () => db.prepare(`SELECT ${columns} FROM articles ORDER BY checked_date, rowid LIMIT 50`).all() as Article[],
    find: (slug: string) => (db.prepare(`SELECT ${columns} FROM articles WHERE slug = ?`).get(slug) as Article | undefined) ?? null,
    search(query: unknown) {
      const q = normalizeQuery(query);
      if (!q) return this.all();
      return db.prepare(`SELECT ${columns} FROM articles WHERE search_text LIKE ? ESCAPE char(92) ORDER BY rowid LIMIT 50`).all("%" + escapeLike(q) + "%") as Article[];
    },
    count: () => Number(db.prepare("SELECT count(*) AS n FROM articles").get()?.n),
    close: () => db.close(),
  };
}
