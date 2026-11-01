import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
const directory=path.resolve('public/images');
const manifest={};
for (const name of fs.readdirSync(directory).filter(n=>n.endsWith('-illustration.png'))) {
 const original=path.join(directory,name);
 const stem=name.replace(/\.png$/,'');
 const {createHash}=await import('node:crypto');
 const hash=createHash('sha256').update(fs.readFileSync(original)).digest('hex').slice(0,10);
 const output=stem+'-'+hash+'.webp';
 const small=stem+'-'+hash+'-640.webp';
 const result=await sharp(original).resize({width:1200,withoutEnlargement:true}).webp({quality:80,effort:6}).toFile(path.join(directory,output));
 await sharp(original).resize({width:640,withoutEnlargement:true}).webp({quality:78,effort:6}).toFile(path.join(directory,small));
 manifest['/images/'+name]={src:'/images/'+output,small:'/images/'+small,width:result.width,height:result.height,originalBytes:fs.statSync(original).size,bytes:result.size,smallBytes:fs.statSync(path.join(directory,small)).size};
}
fs.writeFileSync(path.join(directory,'optimized-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(JSON.stringify({images:Object.keys(manifest).length,originalBytes:Object.values(manifest).reduce((n,r)=>n+r.originalBytes,0),webpBytes:Object.values(manifest).reduce((n,r)=>n+r.bytes,0),smallBytes:Object.values(manifest).reduce((n,r)=>n+r.smallBytes,0)}));
