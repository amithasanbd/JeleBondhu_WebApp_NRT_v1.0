# Upgrade your existing public JeleBondhu repository

Target: `https://github.com/amithasanbd/JeleBondhu_WebApp_NRT_v1.0`

The downloadable ZIP is **source code**, not a GitHub upload by itself. It should be extracted and committed into the existing repository. No repository changes are performed automatically by this package.

## Safest method: a Git branch / Pull Request

1. In your terminal with Git installed, clone your repository:
   ```bash
   git clone https://github.com/amithasanbd/JeleBondhu_WebApp_NRT_v1.0.git
   cd JeleBondhu_WebApp_NRT_v1.0
   git switch -c upgrade-nrt-v1.1
   ```
2. Extract `JeleBondhu_WebApp_NRT_v1.1_GitHubReady.zip` into a temporary folder. Copy **its contents** (not the enclosing folder) into this repository. Keep `.github/workflows` and other hidden files. Review changes with `git diff --stat` and `git status`.
3. Do **not** copy any `.env`, CSV/XLSX raw datasets, secret keys, personal GPS trails or passwords into the repository.
4. Test:
   ```bash
   pip install -r backend/requirements-dev.txt
   PYTHONPATH=backend python -m pytest backend/tests -q
   python scripts/build_site.py --out dist/site --demo data/demo
   ```
5. Commit/push and open a Pull Request into `main`:
   ```bash
   git add -A
   git commit -m "Upgrade JeleBondhu NRT fail-closed safety and API"
   git push -u origin upgrade-nrt-v1.1
   ```
6. In repository settings: **Pages → Source → GitHub Actions**; **Actions → Workflow permissions → Read and write**. Add the *rotated* CMEMS credentials to Actions secrets (`CMEMS_USERNAME`, `CMEMS_PASSWORD`). Do not paste them into workflow YAML.
7. Merge the PR and manually run **NRT advisory bundle + Pages deploy**. Open the Actions log and ensure the bundle reports **mode=live**, actual CMEMS/Open-Meteo source timestamps, and no unexpected QC failures. If the pipeline has no verified inputs, the app must show **NO ADVISORY**.
8. To mark BMD verified, read the original dated BMD bulletin. Run the separate **BMD bulletin update** workflow and supply actual issue time, source URL, classification and your verifier identity. Never default to `none` without checking the official publication.

## Practical constraints

* GitHub Pages hosts the frontend + snapshots, not FastAPI. To expose live read-only JSON APIs over HTTP, deploy the optional API on a separate Python host (see `docs/API_DEPLOY.md`).
* GitHub Actions cron triggers are **not guaranteed** to run at exact times. The web app uses actual timestamps and withdraws expired advice.
* No free-tier ocean or meteorological provider guarantees nautical safety. This application is a research prototype, not an authorized navigation service.
* The 1995–2025 archive is not packed into this public repository; use private Drive/Colab to prepare small versioned model artifacts. The supplied 2020–2025 fisheries data remain unverified for predictive catch claims.
