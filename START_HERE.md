## Seven-day marine outlook (v1.2)

Please follow [**Beginner GitHub launch instructions**](docs/BEGINNER_GITHUB_LAUNCH.md). The seven-day cards are marine weather, not a validated seven-day catch forecast. The original three near-term departure controls remain.

# START HERE — JeleBondhu NRT v1.1 (26 November 2026)

**Repository to upgrade:** https://github.com/amithasanbd/JeleBondhu_WebApp_NRT_v1.0

**Security first:** Rotate the Copernicus Marine credential previously shared in chat. Add only the *new* password in GitHub → Settings → Secrets and variables → Actions. Never put it in the ZIP, notebook, a config file or an issue.

## GitHub upload in five actions

1. Unzip this package. It contains the **root** of the Git repository, including `.github/` and `backend/`. Do not upload the ZIP as a single GitHub file; GitHub does not automatically extract it.
2. In Git Bash, clone the existing repository and make a new branch:
   `git clone https://github.com/amithasanbd/JeleBondhu_WebApp_NRT_v1.0.git` then `cd JeleBondhu_WebApp_NRT_v1.0` then `git switch -c upgrade-nrt-v1.1`.
3. Copy the extracted package's contents into the clone, **including hidden files**. Run tests with:
   `python -m pip install -r backend/requirements-dev.txt` and `PYTHONPATH=backend python -m pytest backend/tests -q` (Git Bash syntax).
4. Commit + push: `git add -A && git commit -m "Upgrade JeleBondhu NRT" && git push -u origin upgrade-nrt-v1.1`. Open and merge the Pull Request into `main` after review.
5. In GitHub Settings → Pages set Source to **GitHub Actions**. Add `CMEMS_USERNAME` and `CMEMS_PASSWORD` as new secrets. Open Actions → **NRT advisory bundle + Pages deploy** → **Run workflow**. Read the logs, then visit the Pages URL shown by GitHub.

**BMD is not automatically cleared:** The BMD bulletin workflow requires an actual issue timestamp, official BMD URL, verifier name, classification and confirmation phrase. Until BMD is verified and current, the application will not issue a positive advisory.

## Preview safely (no data-provider credentials)

```bash
python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python -m pytest backend/tests -q
python scripts/build_site.py --out dist/site --demo data/demo
python -m http.server --directory dist/site 8000
```

Open `http://localhost:8000/fisher.html?demo=1`. A **synthetic demo** is visibly labelled. Without `?demo=1`, the site will show no current advisory until a verified live snapshot is available.

**Windows PowerShell:** replace the `PYTHONPATH=backend` prefix with `$env:PYTHONPATH='backend';` and then run the command.

## What this package is—and is not

It includes a real scheduled Python backend, forecast connectors, offline mobile interface, source-metadata tracking, environmental suitability *screening*, safety/return estimates, fishing-rule filter, BMD manual verification and an optional FastAPI read-only server. GitHub Pages publishes **static snapshots**; it does not host the Python API. Live source retrieval and a successful public GitHub workflow run were not verified in this development environment.

This is an **experimental thesis research prototype**. It is not a certified navigation, regulatory-clearance or fisheries catch-probability service. The 1995–2025 archive was not imported in full; the frozen verified thesis PAI algorithm and independently validated species-specific fishability model have not been incorporated.

Detailed guidance: `README.md`, `docs/UPDATE_EXISTING_REPO.md`, `docs/DEPLOY.md`, `docs/API_DEPLOY.md`, `docs/SCIENCE_BOUNDARIES.md`, and `docs/RELEASE_VERIFICATION_v1.1.md`.
