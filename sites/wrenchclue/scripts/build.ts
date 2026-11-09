import fs from 'node:fs';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {ROOT,readCatalog,readPictures,validateContent,renderBody,sha,type Article,type Catalog} from '../src/content.ts';
import {Pages} from '../src/pages.ts';

const catalog=readCatalog();validateContent(catalog);
const pictures=readPictures();
if(pictures.length!==20||new Set(pictures.map(p=>p.id)).size!==20)throw Error('All twenty article illustrations are required');
for(const p of pictures){for(const asset of [p.large,p.small,p.medium,p.thumbnail])if(!asset||!fs.existsSync(path.join(ROOT,'public',asset)))throw Error('Missing illustration '+asset);}
const db=new DatabaseSync(path.resolve(ROOT,'data/content.sqlite'),{readOnly:true});
const saved=JSON.parse((db.prepare("SELECT value FROM metadata WHERE key='catalog'").get() as {value:string}).value) as Catalog;
if(JSON.stringify(saved)!==JSON.stringify(catalog))throw Error('Content snapshot is stale; run npm run db:seed');
const articles=db.prepare('SELECT data, markdown FROM articles ORDER BY id').all() as {data:string;markdown:string}[];
db.close();
const dist=path.resolve(ROOT,'dist');
if(path.dirname(dist)!==path.resolve(ROOT)||path.basename(dist)!=='dist')throw Error('Invalid build directory');
fs.rmSync(dist,{recursive:true,force:true});
fs.mkdirSync(path.join(dist,'assets'),{recursive:true});
fs.cpSync(path.resolve(ROOT,'public'),dist,{recursive:true});
const css=fs.readFileSync(path.resolve(ROOT,'src/site.css'));
const js=fs.readFileSync(path.resolve(ROOT,'src/site.js'));
const assets={css:`/assets/site.${sha(css).slice(0,12)}.css`,js:`/assets/site.${sha(js).slice(0,12)}.js`};
fs.writeFileSync(path.join(dist,assets.css),css);fs.writeFileSync(path.join(dist,assets.js),js);
const pages=new Pages(catalog,pictures,assets);
const routes:string[]=[];
function write(route:string,html:string,index=true){
  const file=path.join(dist,route,'index.html');fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,html);
  if(index)routes.push(route);
}
write('/',pages.home());
write('/guides/',pages.listing('/guides/','The guidebook.','Find a clear starting point for a warning, a symptom or a repair estimate.',catalog.articles));
write('/repair-costs/',pages.listing('/repair-costs/','Understand the estimate.','Parts, labor, scope and the questions that make two repair quotes comparable.',catalog.articles.filter(a=>a.intent==='cost')));
for(const c of catalog.categories)write(`/topics/${c.slug}/`,pages.listing(`/topics/${c.slug}/`,c.title,c.description,catalog.articles.filter(a=>a.category===c.slug)));
for(const row of articles){const a=JSON.parse(row.data) as Article;if(sha(row.markdown)!==a.markdownSha256)throw Error('Snapshot body mismatch');write(`/guides/${a.slug}/`,pages.article(a,renderBody(row.markdown)));}
write('/about/',pages.about());write('/editorial-policy/',pages.editorial());write('/privacy/',pages.privacy());
write('/search/',pages.listing('/search/','Find your next clue.','Search the guidebook by symptom, part or trouble code.',catalog.articles,'search'),false);
fs.writeFileSync(path.join(dist,'404.html'),pages.notFound());
fs.writeFileSync(path.join(dist,'robots.txt'),`User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /search/\nSitemap: ${catalog.site.origin}/sitemap.xml\n`);
fs.writeFileSync(path.join(dist,'sitemap.xml'),`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${routes.map(r=>`<url><loc>${catalog.site.origin}${r}</loc><lastmod>${catalog.site.publishedAt.slice(0,10)}</lastmod></url>`).join('')}</urlset>`);
fs.writeFileSync(path.join(dist,'manifest.json'),JSON.stringify({site:'wrenchclue',articles:20,routes,assets,pictures,buildAt:new Date().toISOString()},null,2));
console.log(JSON.stringify({built:routes.length,indexedArticles:articles.length,illustrations:pictures.length,clientBytes:js.length}));
