# Data sources, licences, attribution
| Source | Use | Notes |
|---|---|---|
| Copernicus Marine Service (CMEMS) | SST, salinity, currents, MLD, SSH; chlorophyll, NPP, nutrients, O₂, pH | Free account; credentials only as Actions secrets. Dataset IDs in `config/pipeline.json` — verify against the catalogue. Cite "Contains modified Copernicus Marine Service information". |
| Open-Meteo Marine + Forecast API | Waves, wind, gusts, visibility, weather code, 6-day hourly | CC BY 4.0; free tier is for non-commercial use — check terms for production. |
| BMD Marine Warning / Fishermen Forecast pages | Human-verified warning record | No machine API; probe hash is informational only. |
| GEBCO | Bathymetry grid (0.0125°), offline map background, wet-checks | Static, derived by `scripts/prepare_static_data.py`. |
| Thesis PFZ stations | 2,125-station analysis grid, seasonal PAI 2025 | Fields are sampled at stations, never up-sampled. |
| EEZ / IFA shapefiles, MPA list, fishing-ground boxes | Spatial context | IFA MultiPolygon (2 parts) — GEOS validity check still to run. |
| In-situ fisheries 2020–2025, fishing grounds 2022–2024, fisher evidence survey | Validation / context only | Not used to compute live advisories. |
| ONI, IOD | Climate context only | Not used in scores. |
| Ban notices (MoFL) | `data/regulatory/ban_rules_bd.json` | Source URLs listed per rule. |
