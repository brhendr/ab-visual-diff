"""Variant Hunter MVP — independently capture pages and manually compare screenshots."""
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
RUNS.mkdir(exist_ok=True)

st.set_page_config(page_title="Variant Hunter", page_icon="🔎", layout="wide")
st.title("Variant Hunter")
st.caption("Independent visits. Real screenshots. No guesses about which experiences are A/B tests.")


def normalize_url(text):
    text = text.strip()
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    url = urlparse(text)
    if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password:
        raise ValueError("Enter a public http(s) website URL.")
    return text


def blank_image(image_path):
    """Flag mostly solid white pages; never silently classify them as successful."""
    with Image.open(image_path) as im:
        sample = im.convert("RGB").resize((120, 80))
        stat = ImageStat.Stat(sample)
        mean = stat.mean
        deviation = stat.stddev
    return all(channel > 245 for channel in mean) and max(deviation) < 12


def capture(browser, url, index, folder, delay, width, height, accept_consent):
    record = {"visit": index, "status": "failed", "attempts": []}
    context = browser.new_context(viewport={"width": width, "height": height},
                                  device_scale_factor=1, color_scheme="light")
    page = context.new_page()
    page.set_default_timeout(12000)
    try:
        # Navigation errors should not suppress evidence: an error page is useful to see.
        try:
            response = page.goto(url, wait_until="commit", timeout=30000)
            record["http_status"] = response.status if response else None
        except Exception as exc:
            record["navigation_error"] = str(exc)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(int(delay * 1000))
        if accept_consent:
            for name in ("Accept All Cookies", "Accept all cookies", "Accept All",
                         "Allow all", "Accept all", "I Accept"):
                try:
                    button = page.get_by_role("button", name=name, exact=True).first
                    if button.count() and button.is_visible():
                        button.click(timeout=1500)
                        page.wait_for_timeout(1000)
                        record["consent_clicked"] = name
                        break
                except Exception:
                    continue

        file_name = f"visit_{index:03}.png"
        image_path = folder / file_name
        # Do not ask Playwright to wait for animations to finish. Dynamic sites
        # can otherwise time out before we save any screenshot at all.
        for attempt in (1, 2):
            try:
                page.screenshot(path=str(image_path), full_page=False,
                                animations="allow", timeout=30000)
                record["image"] = file_name
                record["blank"] = blank_image(image_path)
                record["status"] = "blocked" if record.get("http_status") == 403 else ("blank" if record["blank"] else "captured")
                record["final_url"] = page.url
                break
            except Exception as exc:
                record["attempts"].append({"attempt": attempt, "error": str(exc)})
                if attempt == 1:
                    page.wait_for_timeout(2000)

        if "image" not in record:
            # Capture a fallback through Chromium's CDP, bypassing Playwright's
            # screenshot stabilization and animation handling.
            try:
                import base64
                cdp = context.new_cdp_session(page)
                payload = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                image_path.write_bytes(base64.b64decode(payload["data"]))
                record["image"] = file_name
                record["blank"] = blank_image(image_path)
                record["status"] = "blank" if record["blank"] else "captured"
                record["capture_method"] = "cdp_fallback"
            except Exception as exc:
                record["fallback_error"] = str(exc)
        return record
    finally:
        context.close()

def scan(url, visits, delay, width, height, accept, show_browser):
    folder = RUNS / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    folder.mkdir(parents=True, exist_ok=True)
    progress = st.progress(0)
    message = st.empty()
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not show_browser)
        try:
            for number in range(1, visits + 1):
                message.write(f"Capturing visit {number} / {visits}")
                try:
                    record = capture(browser, url, number, folder, delay, width, height, accept)
                except Exception as exc:
                    record = {"visit": number, "status": "failed", "error": str(exc), "attempts": []}
                results.append(record)
                progress.progress(number / visits)
                if record.get("http_status") == 403:
                    st.warning("HTTP 403: the site rejected this automated visit. Scan stopped to avoid repeated blocked requests.")
                    break
        finally:
            browser.close()
    report = {"url": url, "created_at": datetime.now(timezone.utc).isoformat(),
              "settings": {"visits": visits, "delay": delay, "width": width, "height": height,
                           "accept_consent": accept, "show_browser": show_browser},
              "results": results}
    (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    message.empty()
    progress.empty()
    return folder


with st.sidebar:
    st.header("Scan")
    url_input = st.text_input("URL", placeholder="https://example.com")
    n = st.slider("Independent visits", 2, 40, 10)
    delay = st.slider("Wait for page to render (seconds)", 2, 12, 5)
    accept = st.checkbox("Click common 'Accept all' consent buttons", value=False,
                         help="This gives consent; leave off unless you want to accept.")
    visible = st.checkbox("Watch browser while scanning", value=False,
                          help="Helpful for seeing why a site renders blank.")
    st.caption("Viewport: 1440 × 900. No clustering or hidden filtering.")
    start = st.button("Capture screenshots", type="primary", use_container_width=True)
    st.divider()
    previous = sorted((p for p in RUNS.iterdir() if (p / "report.json").exists()), reverse=True)
    if previous:
        selected = st.selectbox("Saved runs", previous, format_func=lambda p: p.name)
        if st.button("Open saved run"):
            st.session_state["current_run"] = str(selected)
            st.rerun()

if start:
    try:
        st.session_state["current_run"] = str(scan(normalize_url(url_input), n, delay,
                                                     1440, 900, accept, visible))
    except Exception as exc:
        st.error(f"Scan could not start: {exc}")

current = st.session_state.get("current_run")
if not current:
    st.info("Start with 3 visits against a known page to confirm screenshots render correctly.")
    st.stop()

folder = Path(current)
report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
results = report["results"]
success = [r for r in results if r.get("status") == "captured" and
           r.get("image") and (folder / r["image"]).is_file()]
blank = [r for r in results if r.get("status") == "blank"]
blocked = [r for r in results if r.get("status") == "blocked"]
failed = [r for r in results if r.get("status") == "failed"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Captured", len(success))
c2.metric("Blank", len(blank))
c3.metric("Failed", len(failed))
c4.metric("Blocked (403)", len(blocked))
st.caption(f"URL: {report['url']}")

if blank or failed or blocked:
    with st.expander("Capture problems (including blank screenshots)", expanded=True):
        st.json([r for r in results if r.get("status") != "captured"], expanded=True)
        for r in blank:
            path = folder / r.get("image", "")
            if path.is_file():
                st.image(str(path), caption=f"Blank capture — visit {r['visit']}", width=360)

st.subheader("Every saved screenshot")
images = [r for r in results if r.get("image") and (folder / r["image"]).is_file()]
st.caption(f"{len(images)} image files saved on disk (including blank/error pages).")
if images:
    for i in range(0, len(images), 3):
        cols = st.columns(3)
        for col, record in zip(cols, images[i:i+3]):
            with col:
                st.image(str(folder / record["image"]), use_container_width=True)
                st.caption(f"Visit {record['visit']} — {record['status']}")
else:
    st.warning("No usable screenshots. Try 'Watch browser while scanning' to see what the site actually displays.")

if len(success) >= 2:
    st.subheader("Compare two visits")
    options = [record["visit"] for record in success]
    left, right = st.columns(2)
    with left:
        a = st.selectbox("Left visit", options, index=0)
    with right:
        b = st.selectbox("Right visit", options, index=1)
    lookup = {record["visit"]: record["image"] for record in success}
    left.image(str(folder / lookup[a]), use_container_width=True)
    right.image(str(folder / lookup[b]), use_container_width=True)

output = io.BytesIO()
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for file in folder.iterdir():
        if file.is_file():
            archive.write(file, file.name)
st.download_button("Export screenshots and capture log", output.getvalue(),
                   file_name="variant_hunter_capture.zip", mime="application/zip")
st.caption("Each visit is fresh browser storage but uses the same network IP. No variants are inferred automatically.")
