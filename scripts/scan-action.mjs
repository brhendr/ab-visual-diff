import {chromium} from 'playwright';
import sharp from 'sharp';
import fs from 'node:fs/promises';
import dns from 'node:dns/promises';
import net from 'node:net';
const dir='report';await fs.mkdir(dir,{recursive:true});
const target=process.env.SCAN_URL||'https://example.com';
const visits=Math.min(12,Math.max(2,Number(process.env.SCAN_VISITS)||6));
const isPrivate=(ip)=>{
 if(net.isIP(ip)===4){const [a,b]=ip.split('.').map(Number);return a===0||a===10||a===127||a===169&&b===254||a===172&&b>=16&&b<=31||a===192&&b===168||a===100&&b>=64&&b<=127||a>=224;}
 const s=ip.toLowerCase();return s==='::'||s==='::1'||s.startsWith('fc')||s.startsWith('fd')||s.startsWith('fe8')||s.startsWith('fe9')||s.startsWith('fea')||s.startsWith('feb')||s.startsWith('::ffff:');
};
async function check(input){const u=new URL(input);if(u.protocol!=='https:'||u.username||u.password||u.hostname==='localhost'||u.hostname.endsWith('.localhost'))throw Error('Only public HTTPS URLs are allowed');const addresses=await dns.lookup(u.hostname,{all:true});if(!addresses.length||addresses.some(a=>isPrivate(a.address)))throw Error('Internal addresses are blocked');return u.href;}
const url=await check(target);
let browser;
const captures=[];
try{
 browser=await chromium.launch({headless:true});
 for(let i=0;i<visits;i++){
  const context=await browser.newContext({viewport:{width:1280,height:800},deviceScaleFactor:1,serviceWorkers:'block'});
  try{
   await context.route('**/*',async route=>{try{const u=new URL(route.request().url());if(u.protocol!=='https:')return route.abort();await check(u.href);await route.continue()}catch{return route.abort()}});
   const page=await context.newPage();await page.goto(url,{waitUntil:'domcontentloaded',timeout:25000});await page.waitForTimeout(1800);
   const img=await page.screenshot({animations:'disabled',type:'png'});
   const name='visit-'+(i+1)+'.png';await fs.writeFile(dir+'/'+name,img);
   captures.push({visit:i+1,name,img,actual:page.url()});
  }catch(e){captures.push({visit:i+1,error:String(e.message)})}finally{await context.close()}
 }
}finally{if(browser)await browser.close()}
const ok=captures.filter(c=>c.img);
if(ok.length<2)throw Error('Fewer than two visits succeeded.');
const baseline=await sharp(ok[0].img).removeAlpha().raw().toBuffer();
for(const c of ok){
 const other=await sharp(c.img).removeAlpha().raw().toBuffer();
 const mask=Buffer.alloc(1280*800*4);let changed=0;
 for(let i=0;i<1280*800;i++){const j=i*3;const delta=Math.max(Math.abs(baseline[j]-other[j]),Math.abs(baseline[j+1]-other[j+1]),Math.abs(baseline[j+2]-other[j+2]));if(delta>35){changed++;mask[i*4]=255;mask[i*4+3]=185}}
 c.percent=(100*changed/(1280*800)).toFixed(2);
 c.diff='diff-'+c.visit+'.png';await fs.writeFile(dir+'/'+c.diff,await sharp(mask,{raw:{width:1280,height:800,channels:4}}).png().toBuffer());
}
const esc=s=>String(s).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const html=`<!doctype html><html><meta charset="utf-8"><title>Variant Hunter Report</title><style>body{font:16px system-ui;background:#101827;color:white;margin:30px}h1{margin-bottom:0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}.card{background:#1e293b;padding:16px;border-radius:12px}img{width:100%}small{color:#cbd5e1}</style><h1>Variant Hunter</h1><p>URL: ${esc(url)} · ${visits} isolated visits · ${ok.length} successful</p><small>Red overlays mark pixels different from visit ${ok[0].visit}. Dynamic content can cause false positives.</small><div class="grid">${captures.map(c=>c.error?`<div class="card">Visit ${c.visit}: ${esc(c.error)}</div>`:`<div class="card"><h2>Visit ${c.visit} · ${c.percent}% different</h2><img src="${c.name}"><h3>Difference mask</h3><img src="${c.diff}"></div>`).join('')}</div></html>`;
await fs.writeFile(dir+'/index.html',html);
console.log('Report created: report/index.html');
