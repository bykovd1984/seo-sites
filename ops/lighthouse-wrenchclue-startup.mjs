import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

const tools=process.env.LIGHTHOUSE_PACKAGE_DIR;
if(!tools)throw Error('Set LIGHTHOUSE_PACKAGE_DIR to the isolated Lighthouse installation');
const require=createRequire(path.join(path.resolve(tools),'package.json'));
const {default:lighthouse}=await import(pathToFileURL(require.resolve('lighthouse')).href);
const launcher=await import(pathToFileURL(require.resolve('chrome-launcher')).href);
const expected=process.env.EXPECTED_DEPLOY_COMMIT;
if(!/^[a-f0-9]{40}$/.test(expected||''))throw Error('Set the full expected live commit');
const output=path.resolve(process.env.LIGHTHOUSE_OUTPUT_DIR||'.local/wrenchclue-lighthouse-startup');
await fs.mkdir(output,{recursive:true});
const assertRelease=async()=>{
  const response=await fetch('https://wrenchclue.site/api/health',{signal:AbortSignal.timeout(20000)});
  const health=await response.json();
  if(!response.ok||health.site!=='wrenchclue'||health.articles!==20||health.commit!==expected)throw Error('Unexpected live release');
};
const sites={wrench:'https://wrenchclue.site/',device:'https://deviceclue.site/',rowna:'https://rownasciana.site/'};
// Each site goes first once. The first site is measured again at the end.
// No warm-up navigation, cache override, score-based retry or omitted result.
const orders=[['wrench','device','rowna','wrench'],['device','wrench','rowna','device'],['rowna','wrench','device','rowna']];
const method={lighthouseVersion:'13.6.0',runner:process.env.RUNNER_OS||process.platform,chromeFlags:['--headless=new'],profile:'Default Lighthouse mobile configuration',storage:'Default reset on every audit',release:expected,orders};
const results=[];
let completed=false;
try{
  for(const [browserIndex,order] of orders.entries()){
    const chrome=await launcher.launch({chromePath:process.env.CHROME_PATH||undefined,chromeFlags:method.chromeFlags,handleSIGINT:true});
    try{
      for(const [position,site] of order.entries()){
        await assertRelease();
        const name=`browser-${browserIndex+1}--${position+1}-${site}`;
        const result=await lighthouse(sites[site],{port:chrome.port,logLevel:'error',output:['json','html'],onlyCategories:['performance','accessibility','best-practices','seo']});
        if(!result||result.lhr.runtimeError)throw Error('Lighthouse failed: '+name);
        await fs.writeFile(path.join(output,name+'.report.json'),JSON.stringify(result.lhr));
        await fs.writeFile(path.join(output,name+'.report.html'),result.report[1]);
        await fs.writeFile(path.join(output,name+'.trace.json'),JSON.stringify(result.artifacts.Trace));
        const audits=result.lhr.audits;
        const row={browser:browserIndex+1,position:position+1,site,url:sites[site],report:name+'.report.html',trace:name+'.trace.json',scores:Object.fromEntries(Object.entries(result.lhr.categories).map(([k,v])=>[k,Math.round(v.score*100)])),lcp:audits['largest-contentful-paint'].numericValue,tbt:audits['total-blocking-time'].numericValue,benchmark:result.lhr.environment.benchmarkIndex,browserScripts:audits['network-requests'].details.items.filter(r=>r.resourceType==='Script').map(r=>r.url),fetchTime:result.lhr.fetchTime};
        if(site==='wrench'&&row.browserScripts.length)throw Error('Unexpected browser script');
        results.push(row);
        await fs.writeFile(path.join(output,'progress.json'),JSON.stringify({method,results},null,2));
        console.log(JSON.stringify(row));
      }
    }finally{
      await chrome.kill();
    }
  }
  await assertRelease();
  completed=results.length===12;
}finally{
  await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({complete:completed,method,results},null,2));
  const rows=results.map(r=>`<tr><td>${r.browser}</td><td>${r.position}</td><td><a href="${r.url}">${r.site}</a></td><td>${r.scores.performance}</td><td>${r.tbt.toFixed(1)}</td><td>${r.benchmark}</td><td><a href="${r.report}">HTML</a></td></tr>`).join('');
  await fs.writeFile(path.join(output,'report.html'),`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Browser startup comparison</title><style>body{font:16px/1.6 system-ui;margin:32px}table{border-collapse:collapse}td,th{padding:10px;border:1px solid #ccc}</style><h1>Browser startup comparison</h1><p>Three fresh Chrome processes. Each site measured first once, with the first site repeated last. Default mobile Lighthouse, default storage reset. Every result retained, without warm-up or score-based retries.</p><p>WrenchClue release: ${expected}. Completed: ${completed}.</p><table><tr><th>Browser</th><th>Position</th><th>Site</th><th>Performance</th><th>TBT ms</th><th>CPU benchmark</th><th>Report</th></tr>${rows}</table></html>`);
}
if(!completed)throw Error('Incomplete startup comparison');
console.log(JSON.stringify({complete:true,audits:results.length,output}));
process.exit(0);
