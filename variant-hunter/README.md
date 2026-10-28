# Variant Hunter

Local visual A/B-test discovery using Streamlit and Playwright. This is the Python scanner, separate from the JavaScript prototype in the repository root.

## Installation

From the repository root:

```bash
cd variant-hunter
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m streamlit run app.py
```

## Updating

From the repository root run `git pull`, then restart Streamlit. Scan evidence remains under `variant-hunter/runs/` and is intentionally ignored by Git.

Each visit runs in a new Playwright browser context (fresh cookies and storage), with an optional fresh Chromium process. Screenshots are visually grouped, while visible text, links, images, and element bounding boxes are compared between representative visits. Scan evidence is saved locally for review. Identifying different experiences does **not** prove an experiment exists, and identical captures do **not** rule one out.

Use responsibly on public pages; don't circumvent access controls or aggressively scan websites.

## Video and animation handling

The scan setting **Exclude videos and animated GIFs** (on by default) pauses/hides HTML video and GIF content without collapsing the layout. CSS animations can also be disabled. Canvas animations and some embedded frames can remain.

The app no longer uses NumPy or pandas to render scan differences. If your global Python environment has a binary incompatibility, follow the virtual environment setup above to install an isolated environment.
