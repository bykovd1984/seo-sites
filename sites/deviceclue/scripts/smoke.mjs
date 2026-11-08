import assert from 'node:assert/strict';
import { verifyMarkdown } from './markdown-smoke.mjs';
import fs from 'node:fs';
import { parseArgs } from 'node:util';
import { categories } from '../lib/site.ts';

const { values } = parseArgs({ options: { url: { type: 'string', default: process.env.SITE_TEST_URL || 'http://127.0.0.1:3016' }, at: { type: 'string' } } });
const base = values.url.replace(/\/$/, '');
// --at changes expected results only, for an isolated preview snapshot; never the server clock.
const at = new Date(values.at || Date.now()).toISOString();
const catalog = JSON.parse(fs.readFileSync(new URL('../content/catalog.json', import.meta.url), 'utf8'));
const published = catalog.filter(a => !a.publishAt || a.publishAt <= at);
const pending = catalog.filter(a => a.publishAt && a.publishAt > at);
const publicCategories = categories.filter(c => published.some(a => a.category === c.id));
await verifyMarkdown(base, ['/', '/about', '/privacy', ...publicCategories.map(c => '/topics/' + c.id), ...published.map(a => '/guides/' + a.slug)], [...pending.map(a => '/guides/' + a.slug), '/guides/missing-guide']);
const pendingCategories = categories.filter(c => !published.some(a => a.category === c.id));
const publicSlugs = new Set(published.map(a => a.slug));
async function read(route, expected = 200) {
  const response = await fetch(base + route);
  assert.equal(response.status, expected, route);
  return response.text();
}
const health = JSON.parse(await read('/api/health'));
assert.equal(health.articles, published.length);
assert.equal(health.site, 'deviceclue');
assert.equal(health.publication, 'public');
if (process.env.EXPECTED_DEPLOY_COMMIT) assert.equal(health.commit, process.env.EXPECTED_DEPLOY_COMMIT, 'Deployed commit mismatch');
const home = await read('/');
for (const diagram of new Set(published.map(article => article.diagram))) {
  assert.match(await read('/diagrams/' + diagram + '.svg'), /<svg\b/);
}
assert.match(home, /Less guesswork/);
assert.match(home, /deviceclue\.site/);
assert.match(home, /<meta name="robots" content="index, follow"/);
assert.ok(!home.includes('noindex'));
const publicDocuments = [home];
for (const a of published) {
  const html = await read('/guides/' + a.slug);
  publicDocuments.push(html);
  assert.match(html, /application\/ld\+json/);
  assert.ok(html.includes('https://deviceclue.site/guides/' + a.slug));
  assert.ok(!html.includes('noindex'));
  assert.ok(html.includes('The quick answer'));
  assert.ok(html.includes('Sources &amp; scope'));
  const markdown = fs.readFileSync(new URL('../content/' + a.slug + '.md', import.meta.url), 'utf8');
  const body = /<div class="prose">([\s\S]*?)<\/div><section class="takeaway"/.exec(html)?.[1];
  assert.ok(body, `Article body missing in ${a.slug}`);
  for (const link of markdown.matchAll(/\]\((\/guides\/([a-z0-9-]+))\)/g)) {
    assert.equal(body.includes(`href="${link[1]}"`), publicSlugs.has(link[2]), `Incorrect contextual link availability in ${a.slug}: ${link[1]}`);
  }
  if (/^1\. /m.test(markdown)) assert.ok(body.includes('<ol>'), `Numbered procedure missing in ${a.slug}`);
  for (const match of html.matchAll(/href="#([^"]+)"/g)) assert.ok(html.includes(`id="${match[1]}"`), `Missing anchor ${match[1]} in ${a.slug}`);
}
for (const category of publicCategories) publicDocuments.push(await read('/topics/' + category.id));
for (const category of pendingCategories) {
  await read('/topics/' + category.id, 404);
  assert.ok(!home.includes('href="/topics/' + category.id + '"'));
}
for (const route of ['/about', '/privacy', '/search', '/favicon.svg', '/favicon.ico', '/opengraph-image.png']) await read(route);
for (const html of [...publicDocuments, await read('/about'), await read('/privacy'), await read('/search'), await read('/guides/missing-guide', 404)]) {
  assert.match(html, /name="twitter:card" content="summary_large_image"/);
  assert.match(html, /property="og:image"/);
  assert.doesNotMatch(html, /\/_next\/|__next_f|__NEXT_DATA__/, 'Framework bootstrap must not reach the browser');
  const scripts = [...html.matchAll(/<script\b([^>]*)>/g)];
  assert.equal(scripts.filter(match => /\bsrc=/.test(match[1])).length, 1, 'Exactly one plain browser script');
  for (const [, attributes] of scripts) assert.ok(/type="application\/ld\+json"/.test(attributes) || /src="\/assets\/site\.[a-f0-9]{12}\.js"/.test(attributes), 'Unexpected executable script');
}
const clientUrl = /<script[^>]+src="([^"]+)"/.exec(home)?.[1];
assert.ok(clientUrl);
const client = await fetch(base + clientUrl);
assert.match(client.headers.get('content-type') || '', /javascript/);
assert.match(client.headers.get('cache-control') || '', /immutable/);
assert.ok((await client.arrayBuffer()).byteLength < 10_000, 'Plain browser controller exceeds its size budget');
const cachedClient = await fetch(base + clientUrl, { headers: { 'If-None-Match': client.headers.get('etag') } });
assert.equal(cachedClient.status, 304);
for (const route of ['/package.json', '/data/content.sqlite', '/content/catalog.json', '/.env', '/..%2fdata/content.sqlite']) await read(route, 404);
const post = await fetch(base + '/', { method: 'POST' });
assert.equal(post.status, 405);
assert.equal(post.headers.get('allow'), 'GET, HEAD');
const search = await read('/search?q=Honeywell%20battery');
assert.match(search, /honeywell-thermostat-battery-replacement/);
assert.match(search, /<meta name="robots" content="noindex, follow"/);
const empty = await read('/search?q=zzzxnonexistent');
assert.match(empty, /No matching guide yet/);
const injected = await read('/search?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E');
assert.ok(!injected.includes('<script>alert(1)</script>'));
await read('/guides/missing-guide', 404);
await read('/topics/missing-topic', 404);
const robots = await read('/robots.txt');
assert.match(robots, /Allow: \//);
assert.match(robots, /Disallow: \/search/);
assert.match(robots, /Disallow: \/api\//);
assert.ok(!/^Disallow: \/$/m.test(robots));
assert.match(robots, /Sitemap: https:\/\/deviceclue.site\/sitemap.xml/);
const sitemap = await read('/sitemap.xml');
assert.equal((sitemap.match(/<loc>/g) || []).length, 3 + publicCategories.length + published.length);
assert.ok(!sitemap.includes('/search'));
for (const a of published) assert.ok(sitemap.includes('/guides/' + a.slug));
for (const a of pending) {
  const hidden = await read('/guides/' + a.slug, 404);
  assert.match(hidden, /noindex/);
  assert.ok(!hidden.includes('The quick answer'));
  assert.ok(!sitemap.includes('/guides/' + a.slug));
  for (const html of publicDocuments) assert.ok(!html.includes(`href="/guides/${a.slug}"`), `Future guide linked: ${a.slug}`);
  const results = await read('/search?q=' + encodeURIComponent(a.brand));
  assert.ok(!results.includes(`href="/guides/${a.slug}"`), `Future search result: ${a.slug}`);
}
for (const route of ['/', '/guides/' + published[0].slug]) {
  const response = await fetch(base + route);
  assert.ok(!response.headers.get('x-robots-tag')?.includes('noindex'));
}
for (const route of ['/', '/sitemap.xml', '/topics/ovens', '/guides/' + published[0].slug]) {
  const response = await fetch(base + route);
  const cache = response.headers.get('cache-control') || '';
  const alwaysRevalidate = /(?:^|,)\s*max-age=0(?:,|$)/.test(cache) && /\bmust-revalidate\b/.test(cache) && !/(?:s-maxage=[1-9]|stale-while-revalidate)/.test(cache);
  assert.ok(/no-store|no-cache/.test(cache) || alwaysRevalidate, `Publication route can be served stale: ${route} (${cache})`);
}
const searchResponse = await fetch(base + '/search?q=clock');
assert.match(searchResponse.headers.get('x-robots-tag') || '', /noindex/);
const apiResponse = await fetch(base + '/api/health');
assert.match(apiResponse.headers.get('x-robots-tag') || '', /noindex/);
console.log(`HTTP smoke passed: ${published.length} published, ${pending.length} pending, ${publicCategories.length} topics; scheduled URLs, search, contextual links, cache headers, anchors, canonical URLs, JSON-LD, assets, 404 and sitemap verified.`);
