# Variant Hunter

Local visual A/B-test discovery using Streamlit and Playwright. This is the Python scanner, separate from the JavaScript prototype in the repository root.

## Installation

From the repository root:

```bash
cd variant-hunter
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
python3 -m streamlit run app.py
```

## Updating

From the repository root run `git pull`, then restart Streamlit. Scan evidence remains under `variant-hunter/runs/` and is intentionally ignored by Git.

Each visit runs in a new Playwright browser context (fresh cookies and storage), with an optional fresh Chromium process. Screenshots are visually grouped, while visible text, links, images, and element bounding boxes are compared between representative visits. Scan evidence is saved locally for review. Identifying different experiences does **not** prove an experiment exists, and identical captures do **not** rule one out.

Use responsibly on public pages; don't circumvent access controls or aggressively scan websites.
