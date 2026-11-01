import assert from 'node:assert/strict';
import fs from 'node:fs';
import { parseArgs } from 'node:util';
const {values}=parseArgs({options:{url:{type:'string',default:process.env.SITE_TEST_URL||'http://127.0.0.1:3016'}}});
const base=values.url.replace(/\/$/,'');
const catalog=JSON.parse(fs.readFileSync(new URL('../content/catalog.json',import.meta.url),'utf8'));
async function read(route,expected=200){const response=await fetch(base+route);assert.equal(response.status,expected,route);return response.text();}
const health=JSON.parse(await read('/api/health'));assert.equal(health.articles,10);assert.equal(health.site,'deviceclue');assert.equal(health.publication,'public');
if(process.env.EXPECTED_DEPLOY_COMMIT)assert.equal(health.commit,process.env.EXPECTED_DEPLOY_COMMIT,'Deployed commit mismatch');
const home=await read('/');assert.match(home,/Less guesswork/);assert.match(home,/deviceclue\.site/);assert.match(home,/<meta name="robots" content="index, follow"/);assert.ok(!home.includes('noindex'));
for(const a of catalog){
 const html=await read('/guides/'+a.slug);assert.match(html,/application\/ld\+json/);assert.ok(html.includes('https://deviceclue.site/guides/'+a.slug));assert.ok(!html.includes('noindex'));
 assert.ok(html.includes('The quick answer'));assert.ok(html.includes('Sources &amp; scope'));
 const markdown=fs.readFileSync(new URL('../content/'+a.slug+'.md',import.meta.url),'utf8');
 const body=/<div class="prose">([\s\S]*?)<\/div><section class="takeaway"/.exec(html)?.[1];
 assert.ok(body,`Article body missing in ${a.slug}`);
 for(const link of markdown.matchAll(/\]\((\/guides\/[a-z0-9-]+)\)/g))assert.ok(body.includes(`href="${link[1]}"`),`Body cross-link missing in ${a.slug}: ${link[1]}`);
 for(const match of html.matchAll(/href="#([^"]+)"/g))assert.ok(html.includes(`id="${match[1]}"`),`Missing anchor ${match[1]} in ${a.slug}`);
}
for(const route of ['/topics/ovens','/topics/cooling','/topics/home-systems','/topics/batteries','/topics/small-engines','/about','/privacy','/search','/favicon.svg','/opengraph-image.png'])await read(route);
const search=await read('/search?q=Honeywell%20battery');assert.match(search,/honeywell-thermostat-battery-replacement/);assert.match(search,/<meta name="robots" content="noindex, follow"/);
const empty=await read('/search?q=zzzxnonexistent');assert.match(empty,/No matching guide yet/);
const injected=await read('/search?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E');assert.ok(!injected.includes('<script>alert(1)</script>'));
await read('/guides/missing-guide',404);await read('/topics/missing-topic',404);
const robots=await read('/robots.txt');assert.match(robots,/Allow: \//);assert.match(robots,/Disallow: \/search/);assert.match(robots,/Disallow: \/api\//);assert.ok(!/^Disallow: \/$/m.test(robots));assert.match(robots,/Sitemap: https:\/\/deviceclue.site\/sitemap.xml/);
const sitemap=await read('/sitemap.xml');assert.equal((sitemap.match(/<loc>/g)||[]).length,18);assert.ok(!sitemap.includes('/search'));
for(const route of ['/','/guides/'+catalog[0].slug]){const response=await fetch(base+route);assert.ok(!response.headers.get('x-robots-tag')?.includes('noindex'));}
const searchResponse=await fetch(base+'/search?q=clock');assert.match(searchResponse.headers.get('x-robots-tag')||'',/noindex/);
const apiResponse=await fetch(base+'/api/health');assert.match(apiResponse.headers.get('x-robots-tag')||'',/noindex/);
console.log('HTTP smoke passed: 10 articles, 5 topics, search, empty state, escaped query, anchors, canonical URLs, JSON-LD, assets, 404, robots and 18 sitemap URLs.');
