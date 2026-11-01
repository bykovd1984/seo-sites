# DeviceClue local validation — 2026-11-01

Historical record of the first local draft validation. The owner subsequently authorized public launch; current deployment and indexing settings are described in README. Public release verification is recorded separately in the local launch receipt.

## Successfully executed

- `npm ci --offline --no-audit --no-fund`: 49 packages installed from cache. Node 24.12.0; npm 11.6.2.
- `npm test`: 3 tests passed. Checks ten complete article records, unique identities, internal references and model scopes; read-only SQLite lookup and multiword/literal-wildcard searches; safe Markdown URLs.
- `npm run db:seed`: snapshot contains 10 articles. Re-run after the final source additions and before starting the server.
- `npm run build`: Next.js 16.4.3 production build completed successfully, including TypeScript compilation and standalone output.
- `npm run typecheck`: passed.
- `npm start`: standalone preview served successfully on loopback port 3016.
- `npm run smoke`: passed against the running production preview. Checked all 10 articles, all 5 topics, about/privacy/search, a positive search and empty state, escaped query text, headings/anchors, canonicals, Article JSON-LD, favicon/social image, 404s, robots and the 18-URL sitemap. Search and API are absent from the sitemap.
- Browser: homepage checked at 320, 390, 768 and 1280 px. No horizontal document overflow at any width.
- Browser: every article checked at those four widths: 40 checks, no overflow, exactly one H1, quick answer present and at least two sources on every article.
- Browser: Batteries filter returned 2 cards; returning to All guides restored 10.
- Browser: submitting `Honeywell battery` through the actual search form returned the expected single thermostat guide.
- Browser console: no captured errors or warnings during these checks.
- Temporary viewport overrides were reset after testing.
- Repository status showed only the new `sites/deviceclue/` directory. Existing tracked site files were not changed.

`verification.json` and `screenshots/*.jpg` are local, ignored QA artifacts. They contain the actual responsive-check records and desktop/mobile homepage/article captures.

## Limits

No public deployment, domain/DNS change, search-engine registration, Docker image build, Lighthouse run, physical equipment test or independent technical review was performed. Documentation limits are recorded in `EDITORIAL.md`. The local prototype blocks indexing intentionally. SEO competition and complete keyword coverage remain unconfirmed.
