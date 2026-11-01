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
- `content/*.md`: sixteen full English articles; six use the daily release schedule in `PUBLICATION.md`.
- `scripts/seed.mjs`: validates content and creates an atomic SQLite snapshot. Re-run after editing content.
- `db/repository.ts`: read-only SQLite queries. No account or user database.
- `app/`: home, six topic pages, date-filtered article pages, search, about, privacy, 404, robots, sitemap and health.
- `components/diagram.tsx`: original conceptual SVG diagrams. They do not document actual hardware geometry or certify a model.
- `app/globals.css`: responsive graphite / warm-white / amber visual system; no external fonts.

The reference was the sibling Równa ściana site’s Next.js 16 / React 19 / Node 24 / SQLite architecture. Its article text, illustrations, operator information, analytics identity and deployment configuration were not copied. The DeviceClue components, branding, visual system and article body are separate.

## Editorial and launch status

These are **new answer-focused drafts**, not the withdrawn Miller manual-oriented articles. The ten topics came from the current research shortlist. Keyword demand and difficulty were recorded earlier; actual low competition and all cluster boundaries remain unconfirmed. Building the site does not close that research gap. No traffic or ranking claims are made in the reader-facing pages.

Sources are linked per article; no hands-on testing or independent engineer review is claimed. See `EDITORIAL.md` for the publication checklist and known model limitations.

Public article, topic, home and information pages allow indexing. Search is `noindex, follow`; API endpoints are `noindex, nofollow`. Robots excludes search and API, and the sitemap includes only articles whose publication time has arrived. Search-engine account registration and sitemap submission are separate tasks and are not implied by publishing the site.

Google Analytics is optional and loads only after consent. No advertising tags, third-party fonts or external embeds are present. A public operator/corrections contact is still to be supplied; registrar contact details are private and must not be reused. Independent technical review remains outstanding.

## Search services and Analytics

- Google Search Console: verified domain property `sc-domain:deviceclue.site`; DNS TXT verification must be preserved. The submitted sitemap was processed successfully with 18 discovered URLs.
- Bing Webmaster Tools: verified `https://deviceclue.site/`; preserve CNAME `a144345c47f85ebf49a2c32b64a1aa1f` → `verify.bing.com.`. Sitemap status was Success, with 18 URLs.
- GA4 account `365831891`, property `561806272` (DeviceClue — deviceclue.site), stream `16247839345` (DeviceClue Web), measurement ID `G-VRLR3QNXZQ`. Reporting timezone America/New_York; currency USD. Search Console is linked to this stream.
- Google Signals is off; ad personalization is allowed in zero regions. Enhanced site-search, form, video and browser-history pageviews are off. Scroll, outbound-link and file-download measurement remain enabled.
- `AnalyticsConsent` uses basic consent: no Google tag before acceptance or after a saved rejection. The footer reopens the choice. Revocation disables the stream, removes its first-party GA cookies and reloads without the tag.
- Pageview and referrer URLs have all query strings and fragments removed. One explicit pageview is sent per full document after consent, with automatic initial pageviews disabled. The site currently uses native document navigation, not client-side Link routing.
- Cookie lifetime is configured to 180 days. Privacy copy describes the current behavior; no independent legal review is claimed.

Service registration evidence is saved locally under the chat's `deviceclue-services` visualization folder. Deployment and browser/network evidence for the installed tag are recorded separately in `.local/deviceclue-analytics-receipt.json` when verified.

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

## Operational logging

The production Node 24 process preloads `runtime/logging.cjs`. Node HTTP diagnostic channels record completed application requests (status and duration), startup and application errors. Health checks, Next static assets, favicon and social images are excluded. Only published article/topic paths and fixed public routes are admitted; other paths become `/[unmatched]`. Query strings, search terms, cookies, headers, IP addresses and raw error messages are not sent. Error objects retain built-in error type and code-frame locations under `/app`; full local container diagnostics remain separate.

Logs are sent in ECS-shaped batches to data stream `logs-deviceclue-prod`, shown in Kibana as **DeviceClue — server logs** (data-view ID `deviceclue-logs`). Filter by `service.name: deviceclue`, `event.action`, `http.response.status_code`, `url.path` or `service.version`. The stream has a 30-day data-retention policy; actual deletion follows Elasticsearch's lifecycle schedule.

`ops/provision-deviceclue-logging.py` runs as root on the existing VPS, using the existing administrative connection only to provision this site's resources. It creates a `create_doc`-only key for this exact stream, verifies it cannot read/delete/manage or access the main site's logs, stores it only in `/opt/seo-sites/deviceclue/secrets/elasticsearch-api-key` (root:10001, 0640), and creates the data view. No key or administrative credential is stored in Git, the image, build output or browser. The private internal Docker network `deviceclue-logs` connects only Elasticsearch and DeviceClue. Run provisioning again after recreating the Elasticsearch container to restore this network attachment. Deploy preflight checks both the attachment and secret readability before replacing a release.

Delivery uses batches of up to 50, a 1.5-second timeout and bounded retries, with stable IDs preventing duplicates after ambiguous delivery. The in-memory queue holds at most 1,000 entries and never delays HTTP responses. Logging is best effort: a long Elasticsearch outage or an abrupt process stop can lose queued events, including the final crash event. No disk queue or browser error collector is installed. Local Docker logs rotate at 10 MB × 3. Unit/integration tests exercise privacy, partial retries and a real preloaded HTTP server. Local previews have remote logging disabled unless explicitly configured.

## Daily publication

`content/catalog.json` uses optional `publishAt` timestamps in canonical UTC (`YYYY-MM-DDTHH:mm:ss.sssZ`). Entries without it remain immediately public. The six-article schedule is documented in `PUBLICATION.md`: 2–7 November 2026 at 09:00 Europe/Kyiv (07:00 UTC).

The read-only repository evaluates the current clock for every lookup, count and search. Home, topics, guides and sitemap are dynamic, so a release needs no rebuild, cron or manual deployment. Before release the guide returns 404 and is excluded from listings, search, structured data and sitemap. Contextual links are plain text until their target is available. Browser tabs already open need a reload; search-engine discovery is not instantaneous.

Run `npm test`, reseed, build, typecheck, then run the HTTP smoke against the deployment. Tests exercise every release boundary on the same repository connection. The smoke derives published and pending counts from the actual schedule.
