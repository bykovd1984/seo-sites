# WrenchClue

US automotive repair guidebook at https://wrenchclue.site. Twenty original articles were written with `gpt-6-astra`, reasoning effort `xhigh`. Their frozen bodies, primary-source registry and generation receipts are in `content/`. Each article has a distinct AI-generated illustration, visibly labelled, with responsive 400, 640, 800 and 1200 pixel WebP versions. No independent vehicle testing or certified mechanic review is claimed.

The design uses warm off-white, charcoal, a restrained orange accent and serif headlines. Pages are rendered at build time; only the search page receives a small plain-JavaScript search enhancement. Article and information pages load no browser JavaScript or framework runtime. No analytics, advertising trackers or account forms are installed.

## Local checks

Use Node 24:

```sh
npm ci
npm test
npm run db:seed
npm run build
npm run typecheck
npm start
# In another terminal:
npm run smoke
```

The content snapshot is generated locally with Node SQLite and opened read-only. Do not commit `data/`, `dist/`, original generated images, local research or credentials. Article edits require an intentional update to the frozen body checksum and editorial review. Preserve the manufacturer's vehicle-specific conditions and the published estimate dates.

## Production

Changes on `main` to this site or its own operations files trigger `.github/workflows/deploy-wrenchclue.yml`. Validation runs before the existing `seo-sites` VPS runner builds the image. A temporary isolated candidate must pass the full HTTP smoke check before the production service changes. Failed activation restores WrenchClue's previous image. No other containers are pruned or restarted.

- Service and Compose project: `seo-wrenchclue`
- Directory: `/opt/seo-sites/wrenchclue`
- Public proxy: Caddy, HTTPS apex; `www` redirects to apex
- Container port: `3000`; host binding: `127.0.0.1:5010`
- Health: `/api/health`, with the exact deployed commit and article count
- Image: `seo-wrenchclue:<full commit SHA>`
- Runtime: unprivileged user, read-only filesystem, 256 MB memory limit

For first installation, run `ops/provision-wrenchclue.py prepare` as root on the existing VPS. After the workflow successfully deploys the expected commit, copy that script and `ops/wrenchclue.caddy` to the site's directory and run `publish-route --expected-commit <SHA>`. It verifies health before enabling the site's own Caddy fragment, backs up the routing files, validates and reloads Caddy. Never replace another site's configuration.

Run `SITE_TEST_URL=https://wrenchclue.site EXPECTED_DEPLOY_COMMIT=<SHA> npm run smoke` to verify all twenty articles, thirty-one indexed pages, images, metadata and indexing rules after publication.
