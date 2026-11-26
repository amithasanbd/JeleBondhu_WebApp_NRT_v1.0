> **Seven-day outlook update (v1.2):** The fisher page now supports seven 24-hour marine-weather summaries from Open-Meteo (`forecast_hours=168`). These are planning weather outlooks, **not seven-day PFZ predictions or vessel clearance**. First-time launch: [Beginner GitHub guide](docs/BEGINNER_GITHUB_LAUNCH.md).

# JeleBondhu · জেলেবন্ধু — Near-Real-Time advisory prototype (Bangladesh EEZ)

*Friend of fishermen. Guided by ocean intelligence.*

A static, offline-capable web app plus a Python backend designed to run every 3 hours on GitHub Actions and publishes a **hash-verified advisory bundle**.
Every advisory passes three **non-compensatory** filters — no filter can make up for another:

| Filter | Question | Output |
|---|---|---|
| **1 · Environmental suitability** | Are ocean conditions favourable for fish? | PAI (0–1) — *relative suitability, not a catch probability* |
| **2 · Safety & return margin** | Can this boat go, fish and get back before weather turns? | S (0–1) from wave, wind, gust, visibility, thunderstorm, return margin, official BMD warning |
| **3 · Sustainability & legal** | Is fishing allowed here, now? | U (0–1) + hard gates: 58-day and 22-day closures, protected areas, vessel-zone rules |

Decision priority: **NO-GO > CAUTION / SAFE > NO ADVICE**. Low data confidence withdraws advice (C < 0.3) or caps it at CAUTION (0.3 ≤ C < 0.5).
**"Safe" is a prototype classification — never a guarantee.**

## Three deployment layers
* **GitHub Pages:** public, static, bandwidth-conscious interface; *no Python execution on GitHub Pages*.
* **GitHub Actions:** scheduled Python downloader/processing engine; outputs a small SHA-256-checked live snapshot. On failed acquisition it never invents a favourable forecast.
* **Optional FastAPI:** `backend/jelebondhu/api.py` adds read-only health, cell and advisory JSON endpoints when hosted on a separate Python server; see [docs/API_DEPLOY.md](docs/API_DEPLOY.md).

## Two front-ends
* `fisher.html` — **fisher mode**: Bangla-first, icon-first, three taps (port → boat → time), one big colour/shape answer, audio read-out, a compact initial download with the larger research dashboard cached on demand, works offline.
* `index.html` — **full dashboard**: offline bathymetry map, layers, three-filter trace per station, weather charts, regulations timeline, evidence and provenance, JSON trace download.

## Try it locally (2 minutes, no credentials)
```bash
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python -m pytest backend/tests -q                         # unit + API + safety checks
PYTHONPATH=backend python -m jelebondhu.cli run --mode demo --out dist/live  # synthetic data, flagged DEMO
python scripts/build_site.py --live dist/live --out dist/site
python -m http.server -d dist/site 8000                                      # open http://localhost:8000/fisher.html
```
Demo output is **synthetic** and carries a permanent purple DEMO banner. Never share it as real advice.

## Put it online (GitHub Pages) → see [docs/DEPLOY.md](docs/DEPLOY.md)
1. Create repo, push this folder. 2. *Settings → Pages → Source: GitHub Actions*. 3. Add rotated credentials as secrets `CMEMS_USERNAME`, `CMEMS_PASSWORD`.
4. *Actions → NRT advisory bundle → Run workflow*. 5. Each day a person records the official BMD warning via *Actions → BMD bulletin update*.

## What is live, what is provisional (please read)
See [docs/SCIENCE_BOUNDARIES.md](docs/SCIENCE_BOUNDARIES.md). In short: Filter 1 is an **experimental reconstruction** until the frozen thesis functions are supplied;
vessel limits and port entry waypoints are **provisional**; the BMD warning is **human-verified** (no machine API); the SoNG MPA geometry is only a bounding rectangle;
the 2020–2025 in-situ workbook shows **no demonstrated agreement with PAI** and has internal inconsistencies (see the app's *Evidence* tab).

## Repository map
```
index.html, fisher.html, sw.js, manifest.webmanifest    front-ends (static)
assets/{css,js,img}                                     UI, offline map, logo/icons
backend/jelebondhu/                                     filters, ingest, decision engine, bundle writer, CLI
backend/tests/                                          pytest suite (manual acceptance checks, safety gates, bundle integrity)
config/                                                 pipeline, vessels, ports, filter definitions, reason codes (hot-editable JSON)
data/regulatory/ban_rules_bd.json                       ban calendar (edit when the Government publishes dates)
data/manual/bmd_bulletin.json                           human-verified BMD record
data/spatial, data/static                               EEZ, IFA, MPAs, fishing grounds, bathymetry grid, 2,125 stations
data/demo/                                              synthetic demo bundle (never shown unless ?demo=1)
scripts/                                                static-data preparation, validation, site build
notebooks/                                              Colab Pro calibration notebook
docs/                                                   deployment, architecture, science boundaries, data sources, fisher mode
```

## Licence / patents
No open-source licence is included on purpose — choose one deliberately. A public repository discloses the methods (equations, weights, thresholds, decision rules);
if a patent filing is planned, get advice **before** making the repository public. See [NOTICE.md](NOTICE.md).

## v1.1 fail-closed fixes (26 Nov 2026)
* Missing ANY essential hazard (wave, wind, gust, visibility, thunderstorm) now makes safety **UNKNOWN**, unless another observed hazard is already at a stop limit. The old `nanmin` logic could falsely imply clearance.
* If the forecast horizon cannot cover the entire return trip, the trip is **UNKNOWN**, not safe.
* GitHub Pages workflow can only publish a **live** run to `live/`, never a synthetic demo in disguise.
* A human BMD bulletin record requires explicit dated issue time and official BMD source URL; expired, future-dated and unsigned records cannot clear safety.
* Optional FastAPI read-only interface checks snapshot hashes and masks stale positive status.
* Frozen research PAI labelling is disabled until the complete independently verified thesis algorithm (not just reference climatology) is incorporated.
* For an existing repository upgrade, see [docs/UPDATE_EXISTING_REPO.md](docs/UPDATE_EXISTING_REPO.md).

**Status:** offline/local verification only. The user must run the workflows on their GitHub repository and confirm source availability. A production maritime safety or validated catch forecasting service requires independent review and approval.
