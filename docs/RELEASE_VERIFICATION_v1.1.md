# JeleBondhu NRT v1.1 — release evidence

**Date:** 26 November 2026 · **Source:** user-uploaded `JeleBondhu_WebApp_NRT_v1.0.zip` · **Target:** GitHub `amithasanbd/JeleBondhu_WebApp_NRT_v1.0`.

## Local verification

- **60 pytest tests passed**: Filter 1/2/3 and regulatory gates; BMD expiration; timestamp/official source verification; API path whitelist and hashed file integrity; fresh/stale status; event handling; complete synthetic bundle validation.
- `python -m jelebondhu.cli validate data/demo`: **passed** (manifest file hashes and schema).
- `python scripts/build_site.py --out dist/site --demo data/demo`: **passed**.
- `node --check` on the frontend scripts and final built service worker: **passed**.
- The local *synthetic* demonstration includes 2,125 analysis stations and 54 representative hazard points; mode is explicitly `demo`.
- **No real live retrieval test was possible:** external network access is unavailable from this sandbox. The remote GitHub repository and GitHub Actions run are not verified. Playwright browser navigation was blocked by the local browser's administrator policy; do not treat this as a browser-verified release.

## Key corrections from the uploaded v1.0

1. Essential hazard missing → UNKNOWN unless a confirmed stop hazard is already present; no misleading nanmin clearance.
2. Thunderstorm code unavailable for a contributing forecast point → UNKNOWN absent a confirmed storm.
3. Return-trip horizon not covered → UNKNOWN, not SAFE.
4. BMD source URL + actual issue time are required; stale/future/unverified records cannot grant positive status.
5. Snapshot advisory freshness is capped by the earliest BMD issue/verification/validity deadline.
6. Synthetic demonstration data cannot enter public `live/` through the GitHub workflow.
7. Mother-Hilsa-specific October 2026 ban no longer implies every species is forbidden; default with unspecified species is NO ADVISORY during the affected dates and explicit Hilsa targeting returns NO-GO.
8. The environmental PAI reconstruction remains EXPERIMENTAL even if climatology is added; the exact thesis model was not supplied.
9. Optional read-only FastAPI service provides hashed static JSON endpoints and stale-status downgrading.
10. Mobile-first service-worker install now precaches core fisher assets and loads heavyweight research layers lazily.
11. GitHub Actions pip-cache dependency paths were corrected for the repository's `backend/` structure.

## Publication gate

Before publishing operationally: rotate credentials; validate a *real* scheduled CMEMS and Open-Meteo run; review BMD bulletin every time its effective period changes; verify GIS legal polygons and annual notices; test on physical fisher phones and offshore network conditions; calibrate vessel thresholds; prospectively test forecasting and catch model; secure government/institutional approval. Do not represent `Safe` or `No-Go` as a formal legal determination.

## Source notes

- Open-Meteo Marine Weather API: https://open-meteo.com/en/docs/marine-weather-api
- Open-Meteo noncommercial terms: https://open-meteo.com/en/terms
- CMEMS Toolbox API: https://help.marine.copernicus.eu/en/articles/8283072-copernicus-marine-toolbox-api-subset
- BMD Marine Warning: https://www.bmd.gov.bd/web/en/p/Marine-Warning
- BMD Fishermen Forecast: https://www.bmd.gov.bd/web/en/p/Fishermen-Forecast
- GitHub Pages Actions workflow: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
