import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
const {values}=parseArgs({options:{port:{type:'string',default:'3000'}}});
if (!/^\d+$/.test(values.port) || Number(values.port)<1 || Number(values.port)>65535) throw new Error('Invalid port');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const standalone=path.join(root,'.next/standalone');
if (!fs.existsSync(path.join(standalone,'server.js'))) throw new Error('Run npm run build first');
for (const [from,to] of [['public','public'],['.next/static','.next/static']]) {
 fs.cpSync(path.join(root,from),path.join(standalone,to),{recursive:true});
}
const child=spawn(process.execPath,[path.join(standalone,'server.js')],{cwd:standalone,stdio:'inherit',env:{...process.env,HOSTNAME:'127.0.0.1',PORT:values.port,CONTENT_DB_PATH:process.env.CONTENT_DB_PATH||path.join(root,'data/content.sqlite')}});
for (const signal of ['SIGTERM','SIGINT']) process.on(signal,()=>child.kill(signal));
child.on('exit',(code)=>process.exit(code??1));
