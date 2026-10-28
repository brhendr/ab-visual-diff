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
    # A new context creates fresh cookies/localStorage/sessionStorage each visit.
    context = browser.new_context(viewport={"width": width, "height": height},
                                  device_scale_factor=1, color_scheme="light")
    page = context.new_page()
    page.set_default_timeout(12000)
    try:
        for attempt in range(1, 3):
            attempt_info = {"attempt": attempt}
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                attempt_info["http_status"] = response.status if response else None
                # Some SPAs paint after DOMContentLoaded; waiting for body alone isn't sufficient.
                page.locator("body").wait_for(state="visible", timeout=12000)
                page.wait_for_timeout(int(delay * 1000))
                if accept_consent:
                    for name in ["Accept All Cookies", "Accept all cookies", "Accept All",
                                 "Allow all", "Accept all", "I Accept"]:
                        try:
                            button = page.get_by_role("button", name=name, exact=True).first
                            if button.count() and button.is_visible():
                                button.click(timeout=1500)
                                page.wait_for_timeout(1500)
                                attempt_info["consent"] = name
                                break
                        except Exception:
                            continue
                file_name = f"visit_{index:03}.png"
                image_path = folder / file_name
                page.screenshot(path=str(image_path), full_page=False,
                                animations="disabled", timeout=20000)
                attempt_info["blank"] = blank_image(image_path)
                attempt_info["url"] = page.url
                attempt_info["file"] = file_name
                record["attempts"].append(attempt_info)
                record["image"] = file_name
                record["status"] = "blank" if attempt_info["blank"] else "captured"
                if record["status"] == "captured":
                    return record
                # Retry after longer rendering, retaining the same fresh visitor context.
                page.wait_for_timeout(2500)
            except Exception as exc:
                attempt_info["error"] = str(exc)
                record["attempts"].append(attempt_info)
                record["status"] = "failed"
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
failed = [r for r in results if r.get("status") == "failed"]
c1, c2, c3 = st.columns(3)
c1.metric("Captured", len(success))
c2.metric("Blank", len(blank))
c3.metric("Failed", len(failed))
st.caption(f"URL: {report['url']}")

if blank or failed:
    with st.expander("Capture problems (including blank screenshots)", expanded=not success):
        st.json([r for r in results if r.get("status") != "captured"], expanded=True)
        for r in blank:
            path = folder / r.get("image", "")
            if path.is_file():
                st.image(str(path), caption=f"Blank capture — visit {r['visit']}", width=360)

st.subheader("Every captured visit")
if success:
    for i in range(0, len(success), 3):
        cols = st.columns(3)
        for col, record in zip(cols, success[i:i+3]):
            with col:
                st.image(str(folder / record["image"]), use_container_width=True)
                st.caption(f"Visit {record['visit']}")
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
