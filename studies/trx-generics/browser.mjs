// Actual CLI-generated standalone HTML, with native identities compared to its JSON.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir,readFile,writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium,firefox } from 'playwright';
const [directory,output,phase]=process.argv.slice(2);
assert(directory&&output&&['before','after'].includes(phase),'REPORT_DIR OUTPUT_DIR before|after');
await mkdir(output,{recursive:true});
const require=createRequire(import.meta.url),axe=await readFile(require.resolve('axe-core/axe.min.js'),'utf8');
const records=[];
for(const [engine,launcher] of Object.entries({chromium,firefox})){
 const browser=await launcher.launch();
 try{
  for(const [width,theme] of [[1200,'light'],[375,'dark']]){
   const context=await browser.newContext({viewport:{width,height:1000},colorScheme:theme,offline:true});
   try{
    for(const name of ['history','combined']){
     const page=await context.newPage(),errors=[],network=[];
     page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url());});
     await page.addInitScript(()=>{window.reportCsp=[];document.addEventListener('securitypolicyviolation',e=>window.reportCsp.push(e.violatedDirective));});
     await page.goto(pathToFileURL(resolve(directory,`${name}.html`)).href);
     const expected=JSON.parse(await readFile(resolve(directory,`${name}.json`),'utf8'));
     assert.equal(await page.locator('details.row').count(),expected.summary.total_tests);
     const identity=phase==='after'?'NativePairs.Pair<Int32,Double>.Check':'NativePairs.Pair<Int32.Check';
     const row=page.locator('details.row').filter({has:page.locator(`.name-text[title="${identity}"]`)});
     await row.locator('summary').focus();await page.keyboard.press('Enter');assert.equal(await row.getAttribute('open'),'');
     assert.equal(await row.locator('.test-identity').innerText(),identity);
     if(name==='history'){
      assert.equal(await row.locator('.s-fail').count(),6);
      assert.equal(await row.locator('.s-pass').count(),phase==='before'?6:0);
      assert.equal(await row.locator(phase==='before'?'.dot-flaky':'.dot-broken').count(),1);
     }else{
      assert.equal(await row.locator('.s-unknown').count(),phase==='before'?1:0);
      assert.equal(await page.locator('details.warning').count(),phase==='before'?1:0);
     }
     await page.locator('details').evaluateAll(nodes=>nodes.forEach(node=>node.open=true));
     await page.evaluate(()=>document.fonts.ready);
     assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
     assert.equal(await page.locator('script,iframe,object').count(),0);
     await page.evaluate(axe);assert.deepEqual(await page.evaluate(async()=>(await window.axe.run()).violations.map(v=>v.id)),[]);
     assert.deepEqual(errors,[]);assert.deepEqual(network,[]);assert.deepEqual(await page.evaluate(()=>window.reportCsp),[]);
     await page.screenshot({path:resolve(output,`${engine}-${width}-${name}.png`),fullPage:true});
     records.push({engine,width,theme,case:name,tests:expected.summary.total_tests,errors,network,overflow:false,axeViolations:[]});
     await page.close();
    }
   }finally{await context.close();}
  }
 }finally{await browser.close();}
}
await writeFile(resolve(output,'browser.json'),JSON.stringify({phase,scope:'Actual standalone CLI reports offline; native identities, keyboard disclosures, original evidence and JSON/DOM agreement.',records},null,2)+'\n');
console.log(JSON.stringify({phase,views:records.length}));
