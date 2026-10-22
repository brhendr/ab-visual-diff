# Variant Hunter — A/B Visual Difference Detector

Prototype web app to discover potential experimentation variants without access to the test scripts.

## What it does

- Opens a target URL in 2–12 **isolated Chromium browser contexts** (fresh cookies and local storage).
- Captures same-viewport screenshots after a configurable settle delay.
- Compares each screenshot to the first and calculates the share of materially changed pixels.
- Offers an overlay highlighting changed pixels in red.
- Runs as a browser-based UI; visitors need **no Python installation**.

## Run locally

Requires Node.js 20+.

```bash
npm install
npx playwright install --with-deps chromium
npm start
```

Open http://localhost:3000.

## Deploy on Railway

Use a new Railway service linked to **this** repository, not the Bidgellan service. Use these commands:

- Build: `npm install && npx playwright install chromium`
- Start: `npm start`

The hosting image must include Chromium's OS dependencies; using a Playwright-compatible Docker image is recommended for reliability. Railway provides `PORT` automatically.

**Security:** Set `DEMO_TOKEN` to a secret value in the deployment's environment variables. The web app prompts for it on a 401 response. Do not leave an unrestricted public screenshot service online. The target-host filter blocks direct private IPs and localhost, but this prototype is **not hardened against SSRF** via DNS rebinding, redirects or secondary resource requests; run it only in a trusted environment until further sandboxing is added.

## Scope / known limitations

- No VPN or IP rotation; experiments targeted by geography or IP may not split.
- Session assignments may be sticky to a user agent or fingerprint even with fresh contexts.
- Dynamic content, ads, animations and consent popups cause false positives.
- Sequential visits (not simultaneous side-by-side windows yet).
- No baseline clustering, persistent history or DOM-diff analysis yet.
- Some sites block automated browsers; screenshots may fail.
- Only viewport screenshots; no scrolling/full-page diffs yet.

## Architecture

Express + Playwright + Sharp. Screenshots are held in process memory for 20 minutes and not written to disk. `/api/scan` permits only one scan at a time.
