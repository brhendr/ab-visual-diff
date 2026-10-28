# Variant Hunter — Screenshot MVP

A deliberately minimal, local A/B-test investigation tool. It opens a page as independent browser visitors and saves screenshots. It **does not** claim to detect tests automatically.

## Start

From the `variant-hunter` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m streamlit run app.py
```

## Update

```bash
git pull
python -m streamlit run app.py
```

## Use

1. Start with **3 visits** and **Watch browser while scanning** enabled if you have seen blank screenshots.
2. Check the Captured, Blank, and Failed counts. Blank captures are retried and surfaced, not silently treated as valid.
3. Run **10 or 20 visits** once capture succeeds.
4. Compare any two successful screenshots or export the evidence ZIP.

## Important behavior

- Each visit has fresh cookies and browser storage via a new Playwright context, but **shares the same public IP**.
- The app makes no determination that different screenshots represent an A/B test.
- Click-to-accept consent is opt-in, since it can affect which scripts run.
- Video backgrounds and other dynamic content can produce differences. The MVP does not mask or remove them.
- Saved scans are stored in `runs/` (ignored by Git).
- This tool is not a proxy for testing platform assignment or experiment eligibility. Test discovery is not guaranteed.

## Troubleshooting

If screenshots are blank, choose **Watch browser while scanning** and see if the page shows bot protection, a consent wall, client-side rendering issues, or a navigation redirect. Capture logs explain which visits failed and why. Try a longer render wait. A non-white error or loading page may still need manual inspection.

The old DOM-analysis module has been removed from the MVP.
