# DeviceClue

An English-language equipment guide for **https://deviceclue.site**. Public deployment and DNS configuration were authorized on 2026-11-01. Release evidence is recorded in the repository's local launch receipt.

## Run locally

Node.js 24 LTS:

```powershell
cd C:\Dev\seo-sites\sites\deviceclue
npm ci
npm run db:seed
npm run dev
```

Open http://127.0.0.1:3016. For the production build:

```powershell
npm test
npm run db:seed
npm run build
npm run typecheck
npm start
npm run smoke
```

`npm start -- --port 3016` serves the standalone build. `npm run smoke -- --url http://127.0.0.1:3016` checks another running instance.

## Structure

- `content/catalog.json`: article identity, quick answers, scope, categories, related guides and source citations.
- `content/*.md`: ten full English editorial drafts.
- `scripts/seed.mjs`: validates content and creates an atomic SQLite snapshot. Re-run after editing content.
- `db/repository.ts`: read-only SQLite queries. No account or user database.
- `app/`: home, five topic pages, ten article pages, search, about, privacy, 404, robots, sitemap and health.
- `components/diagram.tsx`: original conceptual SVG diagrams. They do not document actual hardware geometry or certify a model.
- `app/globals.css`: responsive graphite / warm-white / amber visual system; no external fonts.

The reference was the sibling Równa ściana site’s Next.js 16 / React 19 / Node 24 / SQLite architecture. Its article text, illustrations, operator information, analytics identity and deployment configuration were not copied. The DeviceClue components, branding, visual system and article body are separate.

## Editorial and launch status

These are **new answer-focused drafts**, not the withdrawn Miller manual-oriented articles. The ten topics came from the current research shortlist. Keyword demand and difficulty were recorded earlier; actual low competition and all cluster boundaries remain unconfirmed. Building the site does not close that research gap. No traffic or ranking claims are made in the reader-facing pages.

Sources are linked per article; no hands-on testing or independent engineer review is claimed. See `EDITORIAL.md` for the publication checklist and known model limitations.

Public article, topic, home and information pages allow indexing. Search is `noindex, follow`; API endpoints are `noindex, nofollow`. Robots excludes search and API, and the sitemap contains 18 public URLs. Search-engine account registration and sitemap submission are separate tasks and are not implied by publishing the site.

No analytics, ad tags, tracking cookies or external embeds are present. A public operator/corrections contact is still to be supplied; registrar contact details are private and must not be reused. Independent technical review remains outstanding.

## Deployment

`.github/workflows/deploy-deviceclue.yml` validates DeviceClue changes on Node 24. A successful push to `main` builds a standalone Docker image on the existing `seo-sites` VPS runner, checks a temporary candidate, then updates only this site's service with rollback on failure.

- Service/container: `seo-deviceclue`.
- Host binding: `127.0.0.1:5006` → container port 3000.
- Runtime folder: `/opt/seo-sites/deviceclue`.
- Compose source: `ops/docker-compose.deviceclue.yml`.
- Release script: `ops/deploy-deviceclue.sh`.
- Caddy source: `ops/deviceclue.caddy`; deployed separately to `/etc/caddy/domains/deviceclue.caddy` and imported by the existing Caddyfile.
- DNS: BasicDNS A `@` → `65.108.142.86` (Automatic), CNAME `www` → `deviceclue.site.` (30 min).
- HTTPS is managed by Caddy. `www` redirects to the apex with the path and query preserved.
- `/api/health` includes the exact release SHA; deployment smoke checks compare it to `EXPECTED_DEPLOY_COMMIT`.

The Polish workflow is path-filtered so DeviceClue-only changes do not redeploy it. Workflow-only maintenance can be run explicitly with `workflow_dispatch`.
