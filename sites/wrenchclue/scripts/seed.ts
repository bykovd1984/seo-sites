import {mkdirSync,renameSync,rmSync} from 'node:fs';
import {resolve} from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {ROOT,readCatalog,validateContent,articleMarkdown} from '../src/content.ts';

const catalog=readCatalog();
validateContent(catalog);
mkdirSync(resolve(ROOT,'data'),{recursive:true});
const target=resolve(ROOT,'data/content.sqlite');
const temporary=target+`.${process.pid}.tmp`;
const db=new DatabaseSync(temporary);
try{
  db.exec('PRAGMA journal_mode=DELETE; CREATE TABLE articles (id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, data TEXT NOT NULL, markdown TEXT NOT NULL); CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL); BEGIN;');
  const insert=db.prepare('INSERT INTO articles VALUES (?, ?, ?, ?)');
  for(const a of catalog.articles)insert.run(a.id,a.slug,JSON.stringify(a),articleMarkdown(a));
  db.prepare('INSERT INTO metadata VALUES (?, ?)').run('catalog',JSON.stringify(catalog));
  db.exec('COMMIT;');
}catch(e){db.close();rmSync(temporary,{force:true});throw e;}
db.close();
renameSync(temporary,target);
console.log(JSON.stringify({seeded:catalog.articles.length,database:'data/content.sqlite',mode:'read-only snapshot for build/runtime'}));
