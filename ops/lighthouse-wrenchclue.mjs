import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

const tools=process.env.LIGHTHOUSE_PACKAGE_DIR;
if(!tools)throw Error('Set LIGHTHOUSE_PACKAGE_DIR to the isolated Lighthouse installation');
const require=createRequire(path.join(path.resolve(tools),'package.json'));
const {default:lighthouse}=await import(pathToFileURL(require.resolve('lighthouse')).href);
const launcher=await import(pathToFileURL(require.resolve('chrome-launcher')).href);
const {default:desktop}=await import(pathToFileURL(require.resolve('lighthouse/core/config/desktop-config.js')).href);
const origin='https://wrenchclue.site';
const expected=process.env.EXPECTED_DEPLOY_COMMIT;
if(!/^[a-f0-9]{40}$/.test(expected||''))throw Error('Set the full expected live commit');
const output=path.resolve(process.env.LIGHTHOUSE_OUTPUT_DIR||'.local/wrenchclue-lighthouse');
await fs.mkdir(output,{recursive:true});
const get=async route=>{
  const r=await fetch(origin+route,{signal:AbortSignal.timeout(20000)});
  if(!r.ok)throw Error('Public request failed: '+route);
  return r;
};
const assertRelease=async()=>{
  const h=await(await get('/api/health')).json();
  if(h.site!=='wrenchclue'||h.articles!==20||h.commit!==expected)throw Error('Live release changed or is incomplete');
};
await assertRelease();
const sitemap=await(await get('/sitemap.xml')).text();
const urls=[...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
urls.push(origin+'/search/');
if(urls.length!==32||new Set(urls).size!==32||urls.some(u=>!u.startsWith(origin+'/')))throw Error('Unexpected public page inventory');
const method={lighthouseVersion:'13.6.0',runner:process.env.RUNNER_OS||process.platform,chromeFlags:['--headless=new'],mobile:'Lighthouse default mobile emulation and throttling',desktop:'Official Lighthouse desktop configuration',storage:'Default reset on every audit',release:expected};
const results=[];
const comparisons=[];
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const chrome=await launcher.launch({chromePath:process.env.CHROME_PATH||undefined,chromeFlags:method.chromeFlags,handleSIGINT:true});
let completed=false;
try{
  async function audit(url,profile,name){
    const r=await lighthouse(url,{port:chrome.port,logLevel:'error',output:['json','html'],onlyCategories:['performance','accessibility','best-practices','seo']},profile==='desktop'?desktop:undefined);
    if(!r||r.lhr.runtimeError)throw Error('Lighthouse failed: '+url);
    await fs.writeFile(path.join(output,name+'.report.json'),JSON.stringify(r.lhr));
    await fs.writeFile(path.join(output,name+'.report.html'),r.report[1]);
    const a=r.lhr.audits;
    const requests=a['network-requests'].details.items;
    return {url,profile,report:name+'.report.html',scores:Object.fromEntries(Object.entries(r.lhr.categories).map(([k,v])=>[k,Math.round(v.score*100)])),lcp:a['largest-contentful-paint'].numericValue,tbt:a['total-blocking-time'].numericValue,browserScripts:requests.filter(r=>r.resourceType==='Script').map(r=>({url:r.url,bytes:r.resourceSize})),images:requests.filter(r=>r.resourceType==='Image'&&r.url.includes('/images/')).map(r=>({url:r.url,bytes:r.resourceSize})),fetchTime:r.lhr.fetchTime,environment:r.lhr.environment};
  }
  for(const url of urls){
    await assertRelease();
    const name=url.slice(origin.length).replace(/^\/|\/$/g,'').replaceAll('/','__')||'home';
    for(const profile of ['mobile','desktop']){
      const row=await audit(url,profile,name+'--'+profile);
      if(!url.endsWith('/search/')&&row.browserScripts.length)throw Error('Unexpected browser script on an indexed page');
      results.push(row);
      await fs.writeFile(path.join(output,'progress.json'),JSON.stringify({method,results},null,2));
      console.log(JSON.stringify({page:urls.indexOf(url)+1,url,profile,scores:row.scores,tbt:row.tbt}));
    }
  }
  for(const [i,url] of ['https://deviceclue.site/','https://deviceclue.site/guides/zanussi-oven-clock','https://rownasciana.site/','https://rownasciana.site/poradniki/farba-odchodzi-z-tasma'].entries()){
    const row=await audit(url,'mobile','comparison-'+i);comparisons.push(row);
    console.log(JSON.stringify({comparison:url,scores:row.scores}));
  }
  await assertRelease();
  completed=results.length===64;
}finally{
  await chrome.kill();
  const summary={complete:completed,pages:32,audits:results.length,method,results,comparisons};
  await fs.writeFile(path.join(output,'summary.json'),JSON.stringify(summary,null,2));
  const categories=['performance','accessibility','best-practices','seo'];
  const rows=results.map(r=>'<tr><td><a href="'+escape(r.url)+'">'+escape(r.url.slice(origin.length))+'</a></td><td>'+r.profile+'</td>'+categories.map(k=>'<td>'+r.scores[k]+'</td>').join('')+'<td><a href="'+r.report+'">HTML</a></td></tr>').join('');
  const compareRows=comparisons.map(r=>'<tr><td>'+escape(r.url)+'</td>'+categories.map(k=>'<td>'+r.scores[k]+'</td>').join('')+'<td><a href="'+r.report+'">HTML</a></td></tr>').join('');
  await fs.writeFile(path.join(output,'report.html'),'<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>WrenchClue — независимый аудит Lighthouse</title><style>body{background:#f7f5f0;color:#252820;font:15px/1.6 system-ui;margin:35px}h1{font:42px Georgia,serif}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #d9dcd1;text-align:left}th{background:#eae9e1}a{color:inherit}code{overflow-wrap:anywhere}.scroll{overflow:auto}</style><h1>WrenchClue — Lighthouse всех страниц</h1><p>Чистый GitHub runner, стандартные настройки мобильного и настольного Lighthouse. Все измерения сохранены без отбора по баллам.</p><p>Версия: <code>'+expected+'</code>. Проверено страниц: 32, аудитов: '+results.length+'. Поиск намеренно закрыт от индексации.</p><div class="scroll"><table><tr><th>Страница</th><th>Устройство</th><th>Скорость</th><th>Доступность</th><th>Рекомендации</th><th>SEO</th><th>Отчёт</th></tr>'+rows+'</table></div><h2>Сравнение на том же runner</h2><div class="scroll"><table><tr><th>Страница</th><th>Скорость</th><th>Доступность</th><th>Рекомендации</th><th>SEO</th><th>Отчёт</th></tr>'+compareRows+'</table></div></html>');
}
if(!completed)throw Error('Incomplete audit');
console.log(JSON.stringify({complete:true,pages:32,audits:64,output}));
process.exit(0);
