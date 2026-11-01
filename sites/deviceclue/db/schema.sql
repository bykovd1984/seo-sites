CREATE TABLE IF NOT EXISTS articles (
  slug TEXT PRIMARY KEY NOT NULL,
  metadata_json TEXT NOT NULL,
  body_markdown TEXT NOT NULL,
  search_text TEXT NOT NULL,
  sort_order INTEGER NOT NULL
);
