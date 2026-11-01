CREATE TABLE IF NOT EXISTS articles (
 slug TEXT PRIMARY KEY NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
 category TEXT NOT NULL, tags_json TEXT NOT NULL, body_markdown TEXT NOT NULL,
 cover_image TEXT NOT NULL, cover_alt TEXT NOT NULL, reading_minutes INTEGER NOT NULL,
 checked_date TEXT NOT NULL, review_status TEXT NOT NULL, search_text TEXT NOT NULL
);
