# Free GitHub Actions scanner

No Railway or local Python required.

1. Open [Run scanner](https://github.com/brhendr/ab-visual-diff/actions/workflows/scan.yml).
2. Click **Run workflow**, enter a public HTTPS URL and select visits.
3. Open the completed run and download **variant-hunter-report**.
4. Extract the ZIP and open `index.html` locally.

The workflow uses isolated Chromium contexts and creates pixel-difference masks. Runs are not live or simultaneous. Dynamic page content can produce false positives.

## GitHub Pages
To publish the static landing page, open **Settings → Pages → Build and deployment**, choose **Deploy from a branch**, select **main** and **/docs**, then Save. The resulting site is normally `https://brhendr.github.io/ab-visual-diff/`.

**Security:** Only repository users authorized to dispatch Actions workflows can initiate scans. Avoid scanning untrusted targets or high volumes. This prototype's request checks are not a complete network sandbox.
