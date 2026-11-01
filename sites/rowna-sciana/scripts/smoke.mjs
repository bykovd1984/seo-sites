import assert from 'node:assert/strict';
import fs from 'node:fs';
const base = new URL(process.env.SITE_TEST_URL || 'http://127.0.0.1:3000');
const catalog = JSON.parse(fs.readFileSync(new URL('../content/catalog.json', import.meta.url), 'utf8'));
async function get(path) {
  const response = await fetch(new URL(path, base), { signal: AbortSignal.timeout(10000) });
  assert.equal(response.status, 200, path);
  return response;
}
const health = await (await get('/api/health')).json();
assert.equal(health.status, 'ok');
assert.equal(health.articles, catalog.length);
if (process.env.EXPECTED_DEPLOY_COMMIT) assert.equal(health.commit, process.env.EXPECTED_DEPLOY_COMMIT);
const home = await (await get('/')).text();
for (const entry of catalog) {
  const route = '/poradniki/' + entry.slug;
  assert(home.includes(route), 'Missing home link: ' + route);
  const page = await get(route);
  const html = await page.text();
  assert.equal((html.match(/<h1[ >]/g) || []).length, 1, route);
  assert(html.includes('checklist'), route);
  assert(html.includes('noindex'), route);
  assert.equal((await fetch(new URL(entry.coverImage, base), {method:'HEAD'})).status, 200);
}
const search = await (await get('/szukaj?q=ile+schnie+farba+na+scianie')).text();
assert(search.includes('Wyniki dla'));
assert(search.includes('/poradniki/ile-schnie-farba-na-scianie'));
assert.equal((await fetch(new URL('/poradniki/not-a-real-article',base))).status, 404);
assert((await (await get('/robots.txt')).text()).includes('Disallow: /'));
console.log(JSON.stringify({status:'ok',articles:catalog.length,commit:health.commit,base:base.origin}));
