const base=(process.env.SITE_TEST_URL||'http://127.0.0.1:3000').replace(/\/$/,'');
const expected=process.env.EXPECTED_DEPLOY_COMMIT;
function ensure(value:unknown,message:string):asserts value {if(!value)throw Error(message);}
async function get(route:string){const r=await fetch(base+route,{redirect:'manual',signal:AbortSignal.timeout(12000)});return r;}
const health=await get('/api/health');ensure(health.ok,'Health request failed');
const status=await health.json() as {status:string;site:string;articles:number;commit:string};
ensure(status.status==='ok'&&status.site==='wrenchclue'&&status.articles===20,'Wrong health identity');
if(expected)ensure(status.commit===expected,'Unexpected deployed commit');
ensure(health.headers.get('x-robots-tag')?.includes('noindex'),'API must stay out of search');
const sitemapResponse=await get('/sitemap.xml');ensure(sitemapResponse.ok,'Sitemap unavailable');
const sitemap=await sitemapResponse.text();
const routes=[...sitemap.matchAll(/<loc>https:\/\/wrenchclue\.site([^<]+)<\/loc>/g)].map(m=>m[1]);
ensure(routes.length===31,'Unexpected sitemap route count');
ensure(routes.filter(r=>/^\/guides\/[^/]+\/$/.test(r)).length===20,'Sitemap must include all twenty articles');
ensure(!routes.some(r=>r.startsWith('/search')||r.startsWith('/api')),'Private routes in sitemap');
const resources=new Set<string>();
for(const route of routes){
  const r=await get(route);ensure(r.status===200,`Page failed: ${route}`);const html=await r.text();
  ensure((html.match(/<h1>/g)||[]).length===1,`H1 count: ${route}`);
  ensure(html.includes(`rel="canonical" href="https://wrenchclue.site${route}"`),`Canonical: ${route}`);
  ensure(!html.includes('content="noindex'),`Accidental noindex: ${route}`);
  ensure(!html.includes('\uFFFD'),`Encoding: ${route}`);
  ensure(!/<script[^>]+src=/.test(html),`Unexpected browser script on an indexed page: ${route}`);
  if(/^\/guides\/[^/]+\/$/.test(route)){
    ensure(html.includes('AI-generated illustration.'),`Image label: ${route}`);
    ensure(html.includes('id="sources"'),`Sources: ${route}`);
    ensure(html.includes('"@type":"Article"'),`Structured data: ${route}`);
  }
  for(const m of html.matchAll(/(?:src|href)="(\/(?:images|assets)\/[^\"]+|\/favicon\.svg)"/g))resources.add(m[1]);
  for(const m of html.matchAll(/srcset="([^\"]+)"/g))for(const candidate of m[1].split(',')){
    const resource=candidate.trim().split(/\s+/)[0];
    ensure(/^\/images\/[a-z0-9.-]+\.webp$/.test(resource),`Unexpected responsive image: ${route}`);
    resources.add(resource);
  }
}
const search=await get('/search/?q=P0420');ensure(search.status===200,'Search route');
const searchHtml=await search.text();ensure(searchHtml.includes('noindex,follow'),'Search indexing');
const searchScript=searchHtml.match(/<script type="module" src="(\/assets\/[^\"]+\.js)"><\/script>/);
ensure(searchScript,'Missing search enhancement');resources.add(searchScript[1]);
for(const resource of resources){const r=await get(resource);ensure(r.status===200,`Resource: ${resource}`);ensure((await r.arrayBuffer()).byteLength>0,`Empty resource: ${resource}`);if(/\.[a-f0-9]{12}\./.test(resource))ensure(r.headers.get('cache-control')?.includes('immutable'),`Cache header: ${resource}`);}
const missing=await get('/this-guide-does-not-exist/');ensure(missing.status===404,'Missing page must be 404');
const privateFile=await get('/manifest.json');ensure(privateFile.status===404,'Build manifest must not be public');
const redirect=await get('/guides');ensure(redirect.status===308&&redirect.headers.get('location')==='/guides/','Canonical trailing slash');
const robots=await get('/robots.txt');const robotsText=await robots.text();ensure(robotsText.includes('Disallow: /api/')&&robotsText.includes('Disallow: /search/'),'Robots exclusions');
console.log(JSON.stringify({status:'passed',base,articles:20,indexedPages:routes.length,resources:resources.size,commit:status.commit}));
export {};
