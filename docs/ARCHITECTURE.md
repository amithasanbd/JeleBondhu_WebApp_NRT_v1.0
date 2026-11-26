# Architecture

```
Copernicus Marine (daily/hourly fields)   Open-Meteo Marine+Forecast (≈54 representative points)   BMD (human-verified record)
          │ sample at 2,125 stations (never up-sampled)      │ IDW to stations & route samples             │ gate
          ▼                                                   ▼                                             ▼
   Filter 1  PAI = Σ W_k·S_k (PFZI,PPI,OHI,1−VI)     Filter 2  S = G_BMD·min(s_phys, clip(M/0.25,0,1))      │
          └──────────────────────────────┬───────────────────────────────┬────────────────────────────────────┘
                                         ▼                               ▼
                         Filter 3  U = G_MPA·G_season·G_zone·(u_buf·u_crowd·u_life)^(1/3)   (closures, MPAs, vessel-zone, IFA)
                                         ▼
                 decision: NO-GO(3) > UNKNOWN(2) > CAUTION(1) > PASS(0)  +  confidence C = min(components)
                                         ▼
          bundle:  manifest.json (SHA-256 of every file) · cells · advisory/{vessel}__{port} · lite/… · hazard · warnings · provenance · sms
                                         ▼  GitHub Actions → orphan branch `live-data` → Pages
                      browser verifies hashes (WebCrypto) → freshness policy → render
```

## Filters (see config/*.json — thresholds live in JSON, not code)
* **Filter 1** — config-driven membership functions (trapezoid / linear / log-linear / inverse-linear), per-cell weight renormalisation (needs ≥ 50 % of weight present), classes from frozen or experimental percentiles. Sub-index weights: PFZI 0.2553, PPI 0.1441, OHI 0.1925, VI 0.4081 (VI enters as 1−VI).
* **Filter 2** — hazard score `s=clip((h_stop−h)/(h_stop−h_safe),0,1)` (visibility reversed); `s_phys=min` over wave, wind, gust, visibility, thunderstorm (WMO 95/96/99 → 0). Round trip `R_T = d_out/v + T_fish + d_ret/v` along port-entry → station great-circle, wet-checked on a fine GEBCO grid; a route that fails the check is shown but **never certified**. Margin `M=(W−R_T)/R_T` where W is the safe window along the position-time schedule.
* **Filter 3** — rules are dated, inclusive, Asia/Dhaka; trips crossing midnight are tested as intervals; missing-year approval, stale ruleset, missing depth, unverified MPA ⇒ UNKNOWN (never "pass").

## Decision & confidence
Priority NO-GO > CAUTION/SAFE > NO ADVICE; BMD unverified blocks SAFE/CAUTION only. Confidence components: environment freshness, completeness, hazard completeness, calibration factor (0.7 while experimental), spatial support, lead time → `C=min`.

## Browser freshness policy (client clock)
`fresh` ≤ 9 h · `aging` ≤ 12 h (banner) · `stale` ≤ 30 h (SAFE/CAUTION switched off, NO-GO kept) · `expired` (everything → NO ADVICE).

## Failure handling
Live weather missing ⇒ QC gate fails ⇒ previous bundle carried forward. CMEMS missing ⇒ SAFE/CAUTION impossible (NO ADVICE), hazards and closures still produce NO-GO. Hash mismatch ⇒ file refused. No live bundle ⇒ "no data yet" (the demo bundle is only reachable with `?demo=1`).

## Bundle files
`manifest.json` (hashes, validity, ports, vessels) · `status.json` · `cells.json` (per-station environment, PAI, drivers) · `advisory/*.json` (class letters, S, U, A, R_T, margin, confidence, reason bitmask per station per departure) · `lite/*.json` (fisher summary) · `hazard.json` · `warnings.json` · `provenance.json` · `reasons.json` (31 codes, EN/BN) · `sms.json`.
