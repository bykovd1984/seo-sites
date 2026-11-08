import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
import {ROOT,readCatalog,sha,type Picture} from '../src/content.ts';

const receiptPath=process.argv[2];
if(!receiptPath)throw Error('Pass the local generated-image receipts JSON path');
const receipts=JSON.parse(fs.readFileSync(path.resolve(receiptPath),'utf8')) as {images:{id:string;sourcePath:string;prompt:string;method:string}[]};
const catalog=readCatalog();
if(receipts.images.length!==20||new Set(receipts.images.map(i=>i.id)).size!==20)throw Error('Expected twenty distinct article images');
const out=path.resolve(ROOT,'public/images');
const originalDir=path.resolve(ROOT,'../../.local/wrenchclue-assets/originals');
fs.mkdirSync(out,{recursive:true});
fs.mkdirSync(originalDir,{recursive:true});
const pictures:Picture[]=[];
const provenance=[];
for(const a of catalog.articles){
  const r=receipts.images.find(i=>i.id===a.id);
  if(!r)throw Error('Missing image '+a.id);
  const png=fs.readFileSync(r.sourcePath);
  const sourceSha=sha(png);
  fs.writeFileSync(path.join(originalDir,`${a.id}-${a.slug}.png`),png);
  const large=await sharp(png).resize({width:1200,height:800,fit:'cover'}).webp({quality:83,effort:6}).toBuffer();
  const small=await sharp(png).resize({width:640,height:427,fit:'cover'}).webp({quality:80,effort:6}).toBuffer();
  const hash=sha(large).slice(0,12);
  const largePath=`/images/${a.slug}.${hash}.1200.webp`;
  const smallPath=`/images/${a.slug}.${hash}.640.webp`;
  fs.writeFileSync(path.join(ROOT,'public',largePath),large);
  fs.writeFileSync(path.join(ROOT,'public',smallPath),small);
  pictures.push({id:a.id,slug:a.slug,large:largePath,small:smallPath,width:1200,height:800,sha256:sha(large)});
  provenance.push({articleId:a.id,slug:a.slug,method:r.method,prompt:r.prompt,sourceSha256:sourceSha,large:largePath,small:smallPath,largeSha256:sha(large),smallSha256:sha(small),largeBytes:large.length,smallBytes:small.length,caption:'AI-generated illustration. Generic components; not a vehicle-specific repair diagram.'});
}
fs.writeFileSync(path.resolve(ROOT,'content/images.json'),JSON.stringify(pictures,null,2)+'\n');
fs.writeFileSync(path.resolve(ROOT,'content/image-provenance.json'),JSON.stringify({method:'built-in image_gen',images:provenance},null,2)+'\n');
console.log(JSON.stringify({images:pictures.length,totalWebpBytes:provenance.reduce((n,p)=>n+p.largeBytes+p.smallBytes,0)}));
