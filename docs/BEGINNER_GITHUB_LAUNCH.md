# JeleBondhu: Very simple GitHub launch guide (26 Nov 2026)

This is the **7-day marine weather outlook upgrade**, not a validated 7-day catch forecast or an official vessel-safety service. The full seven-day weather outlook is on `fisher.html` after a successful real Open-Meteo run. Route/advisory assessments remain limited to departures now, +12 h and +24 h. The frozen thesis PAI model is not integrated.

## A. Check the GitHub files

1. Visit https://github.com/amithasanbd/JeleBondhu_WebApp_NRT_v1.0 and log in.
2. In **Code** switch to `main` and check that `.github/workflows/nrt.yml`, `backend`, `config`, `fisher.html` and `scripts/build_site.py` exist. If hidden `.github` is missing, the ZIP was not uploaded completely.
3. If upgrading from v1.1, **download the full updated ZIP** and extract it. Using GitHub Desktop is easiest: File → Clone repository → choose your JeleBondhu repo; copy all extracted files into the local clone, including `.github`; in GitHub Desktop review changes → Commit to main → Push origin. Do not upload the ZIP itself. The branch and repository remain yours.

## B. Make it publicly visible

4. GitHub repository **Settings → General → Danger Zone → Change repository visibility**. Choose Public if it is not already Public. First check the repo contains no secrets/private files.
5. **Settings → Pages → Build and deployment → Source = GitHub Actions**.
6. **Settings → Actions → General**. Allow actions used by the workflow. Under **Workflow permissions**, use **Read and write permissions** and Save; this job writes the generated `live-data` branch.

## C. Set secret credentials

7. Change your already exposed Copernicus Marine password in the Copernicus Marine account. Do NOT put that password into README, `.yml`, notebooks, commits or issue comments.
8. GitHub **Settings → Secrets and variables → Actions → New repository secret**. Create `CMEMS_USERNAME` with your CMEMS username and `CMEMS_PASSWORD` with the NEW password. Click Add secret for each.

## D. Run the site

9. Open **Actions → NRT advisory bundle + Pages deploy**. Choose **Run workflow** on `main`.
10. Click the newest workflow run. A **green check** means the workflow completed; expand **Run pipeline**, **Validate bundle**, and **Deploy** to review detailed errors and data provenance. A green run can still publish an unavailable forecast; look for actual source timestamps.
11. **Settings → Pages** should show the actual public website address. Usual URL: `https://amithasanbd.github.io/JeleBondhu_WebApp_NRT_v1.0/` and simple view: `/fisher.html`.
12. The scheduled workflow runs every three hours (`17 */3 * * *` in UTC, approximately **00:17, 03:17, 06:17, 09:17, 12:17, 15:17, 18:17 and 21:17 Bangladesh time**). GitHub scheduled events can be delayed and are not guaranteed continuous NRT hosting.

## E. Record the real official BMD bulletin (daily and whenever updated)

13. Read the actual issued BMD marine warning at https://server6.bmd.gov.bd/en/p/Marine-Warning and the fishermen forecast at https://www.bmd.gov.bd/web/en/p/Fishermen-Forecast. Read/download the *bulletin*, not only the webpage.
14. Open **Actions → BMD bulletin update (human-verified) → Run workflow**. Fill in the real classification, verifier name, official `issued_at` datetime including `+06:00`, actual official BMD source URL, validity hours and confirmation phrase `I_CHECKED_BMD` only when checked. If the bulletin does not clearly apply to the entire EEZ, use appropriate area overrides rather than inventing a nationwide no-warning status.
15. Check that this action completed and triggered a new NRT run. When the bulletin expires, the app automatically withholds positive advice. **Do not extend `valid_hours` beyond the bulletin's validity.** If the source is unclear, leave it unverified.

## F. See the seven-day marine outlook

16. On your public website open `/fisher.html`. Select a port and vessel. The original near-term decision shows under the three-step controls; scroll to **Next 7 days: marine weather / আগামী ৭ দিনের সাগরের আবহাওয়া** for day-by-day wave, wind, visibility and thunderstorm information.
17. The seven-day cards appear only when the new code is deployed and marine API retrieval succeeds. Dashes mean unavailable data; no days can be treated as legal trip clearance. The 168-hour Open-Meteo retrieval is configured by `config/pipeline.json` and the Python downloader.
18. For low-network use, open the page once while online, add it to the phone home screen, then revisit later. Cached forecasts can go stale and **cannot receive offshore warnings without a connection**. Do not use the cached page instead of official forecasts or maritime communication equipment.

## G. Common problems and fixes

| What you see | What to do |
|---|---|
| **Run workflow** button missing | Confirm `.github/workflows/nrt.yml` exists on default `main` and Actions are enabled. |
| Pages shows 404 | Set Pages Source to GitHub Actions, run NRT workflow, check green Deploy step and wait for publication. |
| `CMEMS_USERNAME/CMEMS_PASSWORD not set` | Add secrets and rerun. Never paste them in a public issue. |
| `403` or credentials error | Confirm rotated CMEMS login through its own website; check Github secrets, retry. |
| Weather request HTTP 400 | Inspect Open-Meteo variable names and availability in action log. |
| **No reliable advice** or blank live status | Missing/stale BMD verification, missing weather data, rules awaiting review, or QC failure. This is correct fail-closed behavior. |
| Purple **DEMO** label | Synthetic demonstration, **not** real forecasts. Remove `?demo=1` from URL for live mode. |
| 7-day cards missing | You are on v1.1, or new live snapshot did not build. Upload new files and rerun Actions. |
| Green workflow but no live data | Check the log and `live/manifest.json`: a site may deploy without a usable current forecast. |
| No speech in Bangla | Bengali text-to-speech voice availability depends on the device/browser. |

## What remains before real fishing use

- Validate a frozen species-specific predictive model against independent CPUE, with actual per-day forecasted CMEMS ocean variables.
- Calibrate safety thresholds with Bangladesh authorities and fishers; verify every protected-area activity restriction from official gazettes.
- Maintain official BMD monitoring and verify the non-commercial Open-Meteo terms before extending this beyond research demonstrations.

The code package was locally tested, but GitHub Pages status and external API access were not checked from this environment.
