import {createServer} from 'node:http';
import {readFile,stat} from 'node:fs/promises';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {safeStaticPath,isPrivatePath} from '../src/routing.ts';

const dist=fileURLToPath(new URL('../dist/',import.meta.url));
const database=fileURLToPath(new URL('../data/content.sqlite',import.meta.url));
const manifest=JSON.parse(readFileSync(path.join(dist,'manifest.json'),'utf8')) as {articles:number};
const db=new DatabaseSync(database,{readOnly:true});
const count=(db.prepare('SELECT count(*) AS count FROM articles').get() as {count:number}).count;
db.close();
if(count!==20||manifest.articles!==count)throw Error('Incomplete content snapshot');
const port=Number(process.env.PORT||5187);
const host=process.env.HOST||'127.0.0.1';
const commit=process.env.DEPLOY_COMMIT||'local';
const mime:Record<string,string>={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.svg':'image/svg+xml','.webp':'image/webp','.png':'image/png','.ico':'image/x-icon','.txt':'text/plain; charset=utf-8','.xml':'application/xml; charset=utf-8','.json':'application/json; charset=utf-8'};
const server=createServer(async(req,res)=>{
  res.setHeader('X-Content-Type-Options','nosniff');
  res.setHeader('Referrer-Policy','strict-origin-when-cross-origin');
  res.setHeader('Permissions-Policy','camera=(), microphone=(), geolocation=()');
  res.setHeader('X-Frame-Options','DENY');
  if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405,{'Allow':'GET, HEAD'});res.end();return;}
  let url:URL;
  try{url=new URL(req.url||'/','http://local.invalid');}catch{res.writeHead(400);res.end('Bad request');return;}
  const pathname=url.pathname;
  if(pathname==='/api/health'){
    res.writeHead(200,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'});
    res.end(req.method==='HEAD'?undefined:JSON.stringify({status:'ok',site:'wrenchclue',articles:count,commit}));return;
  }
  if(isPrivatePath(pathname)){res.writeHead(404,{'X-Robots-Tag':'noindex, nofollow'});res.end('Not found');return;}
  let file=safeStaticPath(dist,pathname);
  if(!file){res.writeHead(400,{'X-Robots-Tag':'noindex, nofollow'});res.end('Bad request');return;}
  try{
    let status=200;
    let info;
    try{info=await stat(file);}catch{info=null;}
    if(info?.isDirectory()){
      if(!pathname.endsWith('/')){res.writeHead(308,{'Location':pathname+'/'+url.search});res.end();return;}
      file=path.join(file,'index.html');
      try{info=await stat(file);}catch{info=null;}
    }
    if(!info?.isFile()){file=path.join(dist,'404.html');info=await stat(file);status=404;}
    const data=await readFile(file);
    const ext=path.extname(file);
    const tag='"'+createHash('sha256').update(data).digest('base64url').slice(0,24)+'"';
    const immutable=(pathname.startsWith('/images/')||pathname.startsWith('/assets/'))&&/\.[a-f0-9]{12}\./.test(pathname);
    res.setHeader('Cache-Control',immutable?'public, max-age=31536000, immutable':'public, max-age=0, must-revalidate');
    res.setHeader('Content-Type',mime[ext]||'application/octet-stream');
    res.setHeader('ETag',tag);
    if(pathname.startsWith('/search/')||status===404)res.setHeader('X-Robots-Tag','noindex, follow');
    if(ext==='.html'){
      const hashes=[...data.toString('utf8').matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map(m=>"'sha256-"+createHash('sha256').update(m[1]).digest('base64')+"'");
      res.setHeader('Content-Security-Policy',`default-src 'none'; script-src 'self' ${hashes.join(' ')}; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`);
    }
    if(status===200&&req.headers['if-none-match']===tag){res.writeHead(304);res.end();return;}
    res.setHeader('Content-Length',data.length);
    res.writeHead(status);res.end(req.method==='HEAD'?undefined:data);
  }catch(error){
    console.error(JSON.stringify({level:'error',event:'response_failed',code:(error as NodeJS.ErrnoException).code||'UNKNOWN'}));
    if(!res.headersSent)res.writeHead(500,{'Content-Type':'text/plain; charset=utf-8','X-Robots-Tag':'noindex, nofollow'});
    res.end('Unable to serve this page.');
  }
});
server.listen(port,host,()=>console.log(`WrenchClue ready at http://${host}:${port}`));
for(const signal of ['SIGTERM','SIGINT'] as const)process.on(signal,()=>{server.close(()=>process.exit(0));setTimeout(()=>process.exit(1),10000).unref();});
