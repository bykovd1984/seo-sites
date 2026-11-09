import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {marked} from 'marked';

export const ROOT=fileURLToPath(new URL('../',import.meta.url));
export interface Source {id:string;title:string;url:string;checkedAt:string}
export interface Category {slug:string;title:string;description:string}
export interface Article {id:string;slug:string;title:string;shortTitle:string;description:string;category:string;intent:string;markdown:string;sourceIds:string[];relatedSlugs:string[];wordCount:number;readMinutes:number;imageAlt:string;sourceCheckedAt:string;markdownSha256:string}
export interface Catalog {version:number;site:{name:string;origin:string;publishedAt:string};categories:Category[];articles:Article[];sources:Source[]}
export interface Picture {id:string;slug:string;large:string;small:string;medium:string;thumbnail:string;width:number;height:number;sha256:string}
export interface Body {html:string;headings:{id:string;title:string}[]}
export const sha=(value:string|Buffer)=>createHash('sha256').update(value).digest('hex');
export const escape=(value:unknown)=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export const jsonLd=(value:unknown)=>JSON.stringify(value).replace(/</g,'\\u003c');
export function readCatalog():Catalog {return JSON.parse(readFileSync(resolve(ROOT,'content/catalog.json'),'utf8')) as Catalog;}
export function readPictures():Picture[] {return JSON.parse(readFileSync(resolve(ROOT,'content/images.json'),'utf8')) as Picture[];}
export function articleMarkdown(a:Article):string {return readFileSync(resolve(ROOT,'content',a.markdown),'utf8').replace(/\r\n/g,'\n');}
export function validateContent(catalog:Catalog):void {
  if(catalog.site.origin!=='https://wrenchclue.site'||catalog.articles.length!==20)throw Error('Unexpected publication catalog');
  const slugs=new Set(catalog.articles.map(a=>a.slug));
  const ids=new Set(catalog.articles.map(a=>a.id));
  if(slugs.size!==20||ids.size!==20)throw Error('Duplicate articles');
  for(const a of catalog.articles){
    const body=articleMarkdown(a);
    if(sha(body)!==a.markdownSha256)throw Error(`Article body changed: ${a.slug}`);
    if(!body.startsWith(`# ${a.title}\n`)||a.wordCount<750)throw Error(`Invalid article: ${a.slug}`);
    if(!catalog.categories.some(c=>c.slug===a.category))throw Error('Unknown category');
    if(a.sourceIds.length<2||a.sourceIds.some(id=>!catalog.sources.some(s=>s.id===id)))throw Error('Missing source');
    if(a.relatedSlugs.some(slug=>!slugs.has(slug)))throw Error('Broken related article');
    const allowed=new Set(a.sourceIds.map(id=>catalog.sources.find(s=>s.id===id)!.url));
    for(const match of body.matchAll(/\]\((https?:\/\/[^)]+)\)/g))if(!allowed.has(match[1]))throw Error(`Unknown source in ${a.slug}`);
    for(const match of body.matchAll(/\]\(([a-z0-9-]+)\.md\)/g))if(!slugs.has(match[1]))throw Error(`Broken article link in ${a.slug}`);
    if(/<script\b|<iframe\b|\bCPC\b|\bSemrush\b|\bINPUTS_JSON\b|\uFFFD/i.test(body))throw Error(`Invalid reader content: ${a.slug}`);
  }
}
export function renderBody(markdown:string):Body {
  const body=markdown.replace(/^# [^\n]+\n+/,'').replace(/\]\(([a-z0-9-]+)\.md\)/g,'](/guides/$1/)');
  const headings:Body['headings']=[];
  let html=marked.parse(body,{async:false,gfm:true}) as string;
  html=html.replace(/<h2>(.*?)<\/h2>/g,(_,inner:string)=>{
    const title=inner.replace(/<[^>]+>/g,'').replace(/&amp;/g,'&').replace(/&#39;/g,"'");
    const base=title.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
    const id=base+(headings.some(h=>h.id===base)?`-${headings.length}`:'');
    headings.push({id,title});
    return `<h2 id="${escape(id)}">${inner}</h2>`;
  });
  let tables=0;
  html=html.replace(/<table>[\s\S]*?<\/table>/g,t=>`<div class="table-scroll" role="region" aria-label="Comparison table ${++tables}" tabindex="0">${t}</div>`);
  return {html,headings};
}
