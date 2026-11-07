import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import { loadContent } from '../scripts/content.mjs';
import { openRepository } from '../db/repository.ts';
import { parseMarkdown, safeHref } from '../lib/content.ts';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const rows=loadContent(root);
test('sixty-five complete answer-focused articles have valid cross-links and model scopes',()=>{
 assert.equal(rows.length,65);
 const slugs=new Set(rows.map(r=>r.slug));
 const titles=new Set();
 for(const row of rows){
  const a=row.metadata;assert.ok(!titles.has(a.title));titles.add(a.title);
  assert.ok(!/manual|pdf/i.test(a.title),`Document-seeking title: ${a.title}`);
  assert.ok(a.scope.length>80&&a.answer.length>100);
  assert.ok(a.sources.length>=2);
  const headings=parseMarkdown(row.body).filter(b=>b.type==='heading');
  assert.ok(headings.length>=4);assert.equal(new Set(headings.map(h=>h.id)).size,headings.length);
  for(const related of a.related)assert.ok(slugs.has(related)&&related!==a.slug);
  for(const link of row.body.matchAll(/\]\(\/guides\/([a-z0-9-]+)\)/g))assert.ok(slugs.has(link[1]),`Broken cross-link ${link[1]}`);
 }
});
test('SQLite snapshot supports multiword search, exact slug lookup and literal wildcard handling',()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'deviceclue-test-'));const filename=path.join(folder,'content.sqlite');
 try{
  const db=new DatabaseSync(filename);db.exec(fs.readFileSync(path.join(root,'db/schema.sql'),'utf8'));
  const insert=db.prepare('INSERT INTO articles VALUES (?, ?, ?, ?, ?)');
  for(const row of rows)insert.run(row.slug,JSON.stringify(row.metadata),row.body,row.searchText,row.order);db.close();
  const repo=openRepository(filename,()=>new Date('2026-11-01T12:00:00.000Z'));
  try{
   assert.equal(repo.count(),10);
   assert.equal(repo.find('sul-on-battery-charger')?.brand,'Schumacher');
   assert.equal(repo.find("x' OR 1=1 --"),null);
   assert.ok(repo.search('HONEYWELL battery').some(a=>a.slug==='honeywell-thermostat-battery-replacement'));
   assert.deepEqual(repo.search('%'),[]);assert.deepEqual(repo.search('_'),[]);
   assert.deepEqual(repo.search('zzzxnonexistent'),[]);assert.deepEqual(repo.search(''),[]);
  }finally{repo.close();}
 }finally{fs.rmSync(folder,{recursive:true,force:true});}
});
test('Markdown links reject script and protocol-relative URLs',()=>{
 assert.equal(safeHref('javascript:alert(1)'),null);assert.equal(safeHref('//example.com'),null);
 assert.equal(safeHref('https://example.com'),'https://example.com');
 assert.equal(safeHref('/guides/fridge-coldest-setting'),'/guides/fridge-coldest-setting');
});
