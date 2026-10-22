import express from "express";
import { chromium } from "playwright";
import sharp from "sharp";
import dns from "node:dns/promises";
import net from "node:net";
import { randomUUID } from "node:crypto";

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "16kb" }));
app.use(express.static("public"));
const port = Number(process.env.PORT || 3000);
const token = process.env.DEMO_TOKEN || "";
const images = new Map();
const MAX_VISITS = 12;
let running = false;

function isPrivateIP(ip) {
  if (net.isIP(ip) === 4) {
    const [a,b] = ip.split(".").map(Number);
    return a === 0 || a === 10 || a === 127 || a === 169 && b === 254 ||
      a === 172 && b >= 16 && b <= 31 || a === 192 && b === 168 ||
      a >= 224 || a === 100 && b >= 64 && b <= 127;
  }
  const normalized = ip.toLowerCase();
  return normalized === "::1" || normalized === "::" || normalized.startsWith("fc") ||
    normalized.startsWith("fd") || normalized.startsWith("fe8") ||
    normalized.startsWith("fe9") || normalized.startsWith("fea") ||
    normalized.startsWith("feb") || normalized.startsWith("::ffff:");
}
async function validateURL(text) {
  const u = new URL(text);
  if (!["http:", "https:"].includes(u.protocol)) throw new Error("Only HTTP(S) URLs are supported.");
  if (u.username || u.password) throw new Error("URLs with credentials are not supported.");
  if (u.hostname === "localhost" || u.hostname.endsWith(".localhost")) throw new Error("Local hosts are blocked.");
  const ips = await dns.lookup(u.hostname, { all: true });
  if (!ips.length || ips.some(({address}) => isPrivateIP(address))) throw new Error("Private/internal targets are blocked.");
  return u.href;
}
function authorize(req,res,next) {
  if (token && req.header("x-demo-token") !== token) return res.status(401).json({ error: "Invalid demo access token." });
  next();
}
function store(buffer) {
  const id = randomUUID();
  images.set(id, { buffer, at: Date.now() });
  return "/api/image/" + id;
}
setInterval(() => {
  const cutoff = Date.now() - 20 * 60 * 1000;
  for (const [id, item] of images) if (item.at < cutoff) images.delete(id);
}, 60_000).unref();

app.get("/api/status", (_,res) => res.json({ready:true, protected:!!token, busy:running}));
app.get("/api/image/:id", (req,res) => {
  const item = images.get(req.params.id);
  if (!item) return res.status(404).end();
  res.type("png").set("Cache-Control","no-store").send(item.buffer);
});

app.post("/api/scan", authorize, async (req,res) => {
  if (running) return res.status(429).json({error:"A scan is already running."});
  const count = Math.min(MAX_VISITS, Math.max(2, Number.parseInt(req.body.visits,10) || 6));
  const width = Math.min(1600, Math.max(375, Number.parseInt(req.body.width,10) || 1280));
  const height = Math.min(1200, Math.max(400, Number.parseInt(req.body.height,10) || 800));
  const waitMs = Math.min(5000, Math.max(0, Number.parseInt(req.body.waitMs,10) || 1500));
  let url;
  try { url = await validateURL(String(req.body.url || "")); }
  catch(e) { return res.status(400).json({error:e.message}); }
  running = true;
  let browser;
  try {
    browser = await chromium.launch({ headless:true, args:["--no-sandbox"] });
    const captures = [];
    for (let i=0;i<count;i++) {
      // Isolated, cookie-free contexts simulate independent first visits.
      const context = await browser.newContext({
        viewport:{width,height}, deviceScaleFactor:1,
        locale:"en-US", colorScheme:"light", serviceWorkers:"block"
      });
      const page = await context.newPage();
      const started = Date.now();
      try {
        // Reject navigation redirects to internal hosts too.
        page.on("request", request => {
          // Request-level blocking is configured below via context.route.
        });
        await context.route("**/*", async route => {
          try {
            const requestURL = new URL(route.request().url());
            if (!["http:","https:"].includes(requestURL.protocol)) return route.abort();
            // Block common localhost/private-network redirects and requests.
            if (requestURL.hostname === "localhost" || requestURL.hostname.endsWith(".localhost") ||
                net.isIP(requestURL.hostname) && isPrivateIP(requestURL.hostname)) return route.abort();
            await route.continue();
          } catch { await route.abort(); }
        });
        await page.goto(url,{waitUntil:"domcontentloaded", timeout:20_000});
        await page.waitForTimeout(waitMs);
        const image = await page.screenshot({type:"png", animations:"disabled", fullPage:false, timeout:15_000});
        captures.push({visit:i+1, image, url:page.url(), ms:Date.now()-started});
      } catch(e) { captures.push({visit:i+1, error:e.message}); }
      finally { await context.close(); }
    }
    const ok = captures.filter(x=>x.image);
    if(ok.length < 2) throw new Error("Could not capture two successful visits. The site may block automation.");
    const base = ok[0];
    const comparisons = [];
    const a = await sharp(base.image).removeAlpha().raw().toBuffer();
    for(const item of ok) {
      const b = await sharp(item.image).removeAlpha().raw().toBuffer();
      let changed = 0;
      const mask = Buffer.alloc(width*height*4);
      for (let i=0;i<width*height;i++) {
        const j=i*3;
        const delta = Math.max(Math.abs(a[j]-b[j]),Math.abs(a[j+1]-b[j+1]),Math.abs(a[j+2]-b[j+2]));
        if(delta>35){changed++;mask[i*4]=255;mask[i*4+3]=185;}
      }
      const diff = await sharp(mask,{raw:{width,height,channels:4}}).png().toBuffer();
      comparisons.push({ visit:item.visit, url:item.url, ms:item.ms,
        differencePercent:Math.round(changed/(width*height)*10000)/100,
        screenshot:store(item.image), diff:store(diff)
      });
    }
    res.json({ width,height, baselineVisit:base.visit, comparisons, errors:captures.filter(x=>x.error).map(x=>({visit:x.visit,error:x.error})) });
  } catch(e) { res.status(500).json({error:e.message}); }
  finally { if(browser) await browser.close().catch(()=>{}); running=false; }
});
app.listen(port, "0.0.0.0", () => console.log("Visual Diff demo listening on "+port));
