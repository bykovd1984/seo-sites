# SEO sites

- Work in this repository only. Article text and illustrations were migrated from the earlier prototype.
- Site: sites/rowna-sciana; Node 24, Next.js, read-only SQLite content snapshot.
- Content source: content/catalog.json and Markdown. Run npm run db:seed after editing.
- Preserve manufacturer citations, product-specific conditions, AI illustration labels and honest review status.
- Never invent SEO metrics or independent test results.
- Keep secrets, runtime databases and local research out of Git.
- Validate with npm test, npm run db:seed, npm run build and npm run typecheck.
- Main deploys through .github/workflows/deploy.yml to the VPS runner labelled seo-sites.
- Deployment touches only seo-rowna-sciana and /opt/seo-sites/rowna-sciana.
- Keep noindex until the domain and editorial launch are explicitly finalized.
