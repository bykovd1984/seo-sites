import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
import {ROOT,readCatalog,readPictures,validateContent,articleMarkdown,renderBody} from '../src/content.ts';
import {Pages} from '../src/pages.ts';
import {safeStaticPath,isPrivatePath} from '../src/routing.ts';

const catalog=readCatalog();
const pictures=readPictures();
const pages=new Pages(catalog,pictures,{css:'/assets/site.123456abcdef.css',js:'/assets/site.123456abcdef.js'});
test('the complete Astra xhigh publication preserves all twenty article bodies and source links',()=>{
  validateContent(catalog);
  const generation=JSON.parse(fs.readFileSync(path.join(ROOT,'content/generation.json'),'utf8'));
  assert.equal(generation.model,'gpt-6-astra');assert.equal(generation.reasoningEffort,'xhigh');
  assert.equal(generation.runs.length,4);assert.equal(generation.articleCount,20);
  assert.equal(generation.independentMechanicReview,false);
  const modified=structuredClone(catalog);modified.articles[0].markdownSha256='altered';
  assert.throws(()=>validateContent(modified),/body changed/);
});
test('every article has a distinct optimized cover in both responsive sizes',async()=>{
  assert.equal(pictures.length,20);assert.equal(new Set(pictures.map(p=>p.sha256)).size,20);
  for(const p of pictures){
    const large=await sharp(path.join(ROOT,'public',p.large)).metadata();
    const small=await sharp(path.join(ROOT,'public',p.small)).metadata();
    assert.equal(large.width,1200);assert.equal(large.height,800);assert.equal(large.format,'webp');
    assert.equal(small.width,640);assert.equal(small.height,427);
  }
});
test('published article pages have one H1, valid navigation, sources, AI labels and Article metadata',()=>{
  const allSlugs=new Set(catalog.articles.map(a=>a.slug));
  for(const a of catalog.articles){
    const body=renderBody(articleMarkdown(a));const html=pages.article(a,body);
    assert.equal((html.match(/<h1>/g)||[]).length,1);
    const heading=html.match(/<h1>(.*?)<\/h1>/)[1].replaceAll('&amp;','&').replaceAll('&#39;',"'").replaceAll('&quot;','"').replaceAll('&lt;','<').replaceAll('&gt;','>');
    assert.equal(heading,a.title);
    assert.ok(html.includes('AI-generated illustration.'));
    assert.ok(html.includes('has not been independently reviewed by a certified mechanic'));
    assert.ok(html.includes(`https://wrenchclue.site/guides/${a.slug}/`));
    assert.ok(html.includes('"@type":"Article"'));assert.ok(html.includes('content="index,follow"'));
    for(const h of body.headings)assert.ok(html.includes(`id="${h.id}"`));
    for(const m of html.matchAll(/href="\/guides\/([^/]+)\/"/g))assert.ok(allSlugs.has(m[1]));
    for(const id of a.sourceIds)assert.ok(html.includes(catalog.sources.find(s=>s.id===id).title.replaceAll('&','&amp;')));
    assert.ok(!/href="[^\"]+\.md"/.test(html));
  }
});
test('the home page provides usable topic navigation and real editorial limits',()=>{
  const html=pages.home();assert.equal((html.match(/<h1>/g)||[]).length,1);
  for(const c of catalog.categories)assert.ok(html.includes(`/topics/${c.slug}/`));
  assert.ok(html.includes('action="/search/"'));assert.ok(html.includes('AI-generated illustration'));
  assert.ok(!/googletagmanager|google-analytics|facebook\.net|independently tested/i.test(html));
});
test('search and missing pages are excluded from indexing',()=>{
  assert.ok(pages.listing('/search/','Search','Find a guide',catalog.articles,'search').includes('content="noindex,follow"'));
  assert.ok(pages.notFound().includes('content="noindex,follow"'));
});
test('static path resolution blocks encoded traversal, backslashes and null bytes',()=>{
  const root=path.resolve(ROOT,'dist');
  assert.equal(safeStaticPath(root,'/%2e%2e/%2e%2e/secrets'),null);
  assert.equal(safeStaticPath(root,'/images/%5csecret'),null);
  assert.equal(safeStaticPath(root,'/%00'),null);assert.equal(safeStaticPath(root,'/%ZZ'),null);
  assert.equal(safeStaticPath(root,'/guides/'),path.join(root,'guides'));
  assert.ok(isPrivatePath('/manifest.json'));assert.ok(isPrivatePath('/.env'));assert.ok(isPrivatePath('/api/private'));
  assert.ok(isPrivatePath('/man%69fest.json'));assert.ok(isPrivatePath('/%2eenv'));
});
test('tables are keyboard-accessible scrolling regions and article links point to published routes',()=>{
  const result=renderBody('# Test\n\n## Compare options\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n[Guide](car-overheating.md)');
  assert.equal(result.headings[0].id,'compare-options');assert.ok(result.html.includes('tabindex="0"'));
  assert.ok(result.html.includes('href="/guides/car-overheating/"'));assert.ok(!result.html.includes('<h1>'));
});

test('guide listings preserve sequential headings for screen-reader navigation',()=>{
  const html=pages.listing('/guides/','The guidebook.','Find a guide.',catalog.articles);
  assert.equal((html.match(/<h1>/g)||[]).length,1);
  assert.equal((html.match(/<h2>/g)||[]).length,21);
  assert.ok(!html.includes('<h3>'));
});
