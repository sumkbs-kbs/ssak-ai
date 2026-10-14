import { loadOmowright } from '/Users/mr.k/.codex/plugins/cache/sisyphuslabs/omo/5.1.14/skills/browser/scripts/omowright.mjs';
import { mkdir,readFile,writeFile,appendFile,rm } from 'node:fs/promises';
import path from 'node:path';
import readline from 'node:readline';
const root=path.dirname(new URL(import.meta.url).pathname);
const {omowright}=await loadOmowright();
const profile=path.join(root,'browser-profile');
await mkdir(profile);
await mkdir(path.join(root,'screenshots'));
const browser=await omowright.connectPipe({browserPath:'/Users/mr.k/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell',browserArgs:['--headless','--no-first-run','--disable-background-networking','--disable-component-update','--disable-sync','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1','--window-size=1280,900','--force-device-scale-factor=1','--user-data-dir='+profile],storageRoot:profile,dialogPolicy:{accept:true}});
const ready=JSON.parse(await readFile(path.join(root,'runtime/started.json'),'utf8'));
const base='http://127.0.0.1:'+ready.port;
const secret=(await readFile(path.join(root,'runtime/auth-private/pin.txt'),'utf8')).trim();
let page;
const lines=readline.createInterface({input:process.stdin,terminal:false});
let n=0;
const scrub=value=>JSON.stringify(value).replaceAll(secret,'[redacted PIN]').replace(/[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}/g,'[redacted token]');
const report=async(value)=>{await appendFile(path.join(root,'browser-actions.jsonl'),scrub(value)+'\n');console.log(scrub(value));};
try{
  page=await browser.newTab(base+'/chat');
  await omowright.emulate(page,{width:1280,height:900,deviceScaleFactor:1,mobile:false,hasTouch:false});
  await report({ready:true,base,driver_pid:process.pid,viewport:await page.evaluate(()=>({width:innerWidth,height:innerHeight})),snapshot:omowright.compactSnapshot(await page.snapshot())});
  for await (const line of lines){
    if(!line.trim())continue;
    const command=JSON.parse(line);n++;
    try{
      if(command.action==='stop'){await report({n,action:'stop'});break;}
      if(command.action==='snapshot')await report({n,snapshot:omowright.compactSnapshot(await page.snapshot())});
      else if(command.action==='fill'){
        await page.locator(command.ref).fill(command.pin?secret:command.value);
        await report({n,action:'fill',ref:command.ref,value:command.pin?'[redacted PIN]':command.value});
      }else if(command.action==='click'){
        await page.locator(command.ref).click();await report({n,action:'click',ref:command.ref});
      }else if(command.action==='press'){
        await page.locator(command.ref).press(command.key);await report({n,action:'press',ref:command.ref,key:command.key});
      }else if(command.action==='goto'){
        await page.goto(base+command.path);await report({n,action:'goto',path:command.path});
      }else if(command.action==='viewport'){
        if (!command.mobile) await omowright.emulate(page, null);
        await omowright.emulate(page,{width:command.width,height:command.height,deviceScaleFactor:1,mobile:!!command.mobile,hasTouch:!!command.mobile,...(command.mobile?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',platform:'iPhone'}:{})});
        await report({n,action:'viewport',value:await page.evaluate(()=>({width:innerWidth,height:innerHeight,userAgent:navigator.userAgent}))});
      }else if(command.action==='screenshot'){
        if(!/^[a-z0-9-]+\.png$/.test(command.name))throw Error('Invalid screenshot filename');
        await writeFile(path.join(root,'screenshots',command.name),await page.screenshot());
        await report({n,action:'screenshot',name:command.name,viewport:await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight}))});
      }else if(command.action==='read'){
        const value=await page.evaluate((()=>{return {url:location.href,text:document.body.innerText,tokenPresent:!!sessionStorage.getItem('ag_access_token'),enabledTextareas:[...document.querySelectorAll('textarea')].filter(e=>!e.disabled).length,alerts:[...document.querySelectorAll('[role=alert]')].map(e=>e.innerText)};}));
        await report({n,action:'read',value});
      }else throw Error('Unknown action');
    }catch(error){await report({n,action:command.action,error:String(error)});}
  }
}finally{
  await browser.close();
  lines.close();
  await rm(profile,{recursive:true,force:true});
  await report({closed:true,profile_removed:true});
  process.exit(0);
}

