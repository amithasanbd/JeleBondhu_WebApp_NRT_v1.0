# Deployment (GitHub + GitHub Pages + Actions)

## 0 · First: rotate the leaked password
The Copernicus Marine password was pasted into a chat message. Treat it as compromised: change it at the Copernicus Marine account page **before** adding it as a secret.
Also set the Google Drive link that was "anyone can edit" to *view only* or restricted.

## 1 · Create the repository
```bash
cd jelebondhu          # this folder
git init -b main && git add . && git commit -m "JeleBondhu NRT prototype"
git remote add origin https://github.com/<you>/<repo>.git && git push -u origin main
```
`data/raw/` is git-ignored: large source files (GEBCO, shapefile zips, workbooks) stay on your machine / Drive.

## 2 · Enable Pages and secrets
* *Settings → Pages → Build and deployment → Source = **GitHub Actions***.
* *Settings → Secrets and variables → Actions → New repository secret*: `CMEMS_USERNAME`, `CMEMS_PASSWORD`.
* *Settings → Actions → General → Workflow permissions = Read and write*.

## 3 · First run
*Actions → "NRT advisory bundle + Pages deploy" → Run workflow*.
* The public workflow always runs **live** ingestion; synthetic data is never deployed into `live/`.
* For an explicitly labelled offline demonstration, run the local demo command in the README, or open the built site with `?demo=1` (synthetic data remain under `demo/`).
* The live workflow pulls CMEMS + Open-Meteo. If weather data cannot be fetched the run **fails the QC gate** and the previous bundle is carried forward (it ages and is down-graded automatically).
The site appears at `https://<you>.github.io/<repo>/fisher.html`.

## 4 · Daily human step: record the official BMD warning
There is no machine-readable BMD API, so the app never infers "no warning" from a web page.
1. Read https://server6.bmd.gov.bd/en/p/Marine-Warning and https://www.bmd.gov.bd/web/en/p/Fishermen-Forecast.
2. *Actions → "BMD bulletin update" → Run workflow*: supply the official **issue time and exact BMD source URL**, classification (none / cautionary / warning / great_danger), verifier name, hours valid and optional area overrides. Enter `I_CHECKED_BMD` in the confirmation field only after reviewing the dated bulletin. Defaulting to a no-warning record without checking is prohibited.
3. The record **expires after 24 h** (config `bmd.max_verification_age_h`). While it is unverified, **no FAVOURABLE or CAUTION advice is issued**; NO-GO and NO ADVICE still are.
The verifier name is shown publicly in the Data panel.

## 5 · Keeping rules current (hot-updatable)
Edit `data/regulatory/ban_rules_bd.json` when the Government publishes a notice (explicit dated, inclusive ranges, Asia/Dhaka). Never reuse last year's lunar dates.
A year with no approved rule makes the indicative window return NO ADVICE rather than "unrestricted". `review_due` passes → the whole ruleset is treated as stale → NO ADVICE.

## 6 · Optional upgrades
* Run `notebooks/JeleBondhu_Colab_Calibration.ipynb` in Colab Pro to build `data/reference/climatology.npz` (anomaly components).
* Custom domain: Pages settings. SMS: `live/sms.json` holds ready-to-send texts; connect a gateway of your choice (none is wired).

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| Site says "No advisory data has been published yet" | no live bundle: run the workflow once |
| Purple DEMO banner | the bundle was built with `mode=demo` |
| "File failed integrity check" | partial deploy; reload. Persistent = tampering or a broken build |
| Everything NO ADVICE | BMD record unverified/expired, CMEMS credentials missing, or rules stale — see *Data & trace* tab |
