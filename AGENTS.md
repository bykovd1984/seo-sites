# SEO sites

- Work in this repository only. Article text and illustrations were migrated from the earlier prototype.
- Site: sites/rowna-sciana; Node 24, Next.js, read-only SQLite content snapshot.
- Content source: content/catalog.json and Markdown. Run npm run db:seed after editing.
- Preserve manufacturer citations, product-specific conditions, AI illustration labels and honest review status.
- Never invent SEO metrics or independent test results.
- Keep secrets, runtime databases and local research out of Git.
- Validate with npm test, npm run db:seed, npm run build and npm run typecheck.
- Main deploys through .github/workflows/deploy.yml to the VPS runner labelled seo-sites.
- Deploy each site independently: rowna-sciana uses seo-rowna-sciana, /opt/seo-sites/rowna-sciana and loopback port 5005; deviceclue uses seo-deviceclue, /opt/seo-sites/deviceclue and loopback port 5006. Never change or prune unrelated containers.
- DeviceClue public deployment and DNS configuration were authorized on 2026-11-01. Preserve its source citations and honest editorial limits; no independent equipment testing is claimed.
- Public launch and search registration were authorized on 2026-11-01. Index article pages; keep search and API pages out of the index. Preserve consent-before-analytics behavior.
