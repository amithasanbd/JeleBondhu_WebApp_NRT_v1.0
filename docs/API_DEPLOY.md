# Optional API/server deployment

The operational-style backend already runs as a **scheduled batch pipeline** in GitHub Actions. GitHub Pages hosts **static snapshots**, not a Python server.

For an institution-hosted read-only HTTP API, use the *same verified snapshot bundle*:

```bash
pip install -r backend/requirements-api.txt
python scripts/build_site.py --out dist/site --live dist/live --demo data/demo
PYTHONPATH=backend JB_SITE_DIR=dist/site uvicorn jelebondhu.api:app --host 127.0.0.1 --port 8000
```

For a public server behind HTTPS, use a reverse proxy (such as Caddy or Nginx), TLS, a supervised process and traffic limits. Set `JB_SITE_DIR` to the **absolute** directory containing the built website. Do **not** mount Google Drive or place CMEMS credentials within that public directory.

Read-only routes:

- `GET /api/health`: 200 for current snapshot, 503 for missing/stale/expired snapshot.
- `GET /api/manifest`: manifest and freshness, provided a QC-passed live snapshot exists.
- `GET /api/cells`: environmental station arrays (versioned + hashed).
- `GET /api/advisory/{vessel}/{port}?departure=0`: selected precomputed advisory, with stale positive classes withdrawn.
- `GET /api/docs`: FastAPI documentation (optional).

The API checks the snapshot manifest and SHA-256 file integrity. No API endpoint computes a new weather forecast or overrides BMD. API responses are explicitly research-only. There is no public write or credential handling API. The web application's offline functionality remains supported by its static files and service worker.

For production-scale use, add: authentication for administrative edits; public API rate limiting; logs, error monitoring, TLS; official data-sharing agreements; locally calibrated vessel thresholds; qualified institutional oversight; observed forecast skill; legally approved zone restrictions; prospective catch validation.
