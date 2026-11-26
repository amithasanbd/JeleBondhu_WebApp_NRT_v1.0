# Science boundaries — what is solid, what is provisional

## Provisional / experimental (must be resolved before any operational use)
| Item | State | Action |
|---|---|---|
| **Filter 1 functions** | The frozen thesis membership functions were not in the supplied files. The app uses a **data-driven reconstruction** (20 components, sub-index weights from the thesis summary), labelled *EXPERIMENTAL* everywhere, confidence ×0.7. Its spatial rank agreement with the thesis 2025 PAI is reported informally in *Data & trace*. | Supply complete frozen thesis functions, independent validation, and implement a tested adapter. The current backend explicitly retains EXPERIMENTAL mode even if `mode=frozen` is requested; a climatology file alone is insufficient. |
| **Vessel thresholds** (wave/wind/gust/visibility, speed, hours, range) | PROVISIONAL generic values in `config/vessels.json`. | Review with fishers, BMD/BIWTA, port authorities; add vessel-specific stability limits. |
| **Port sea-entry waypoints** | Approximate, checked wet on GEBCO. The landing-site→entry leg is not modelled (an offset is added). | Verify with local pilots; add channel routes. |
| **BMD warning** | Human-verified record only; 24 h validity. | Daily workflow; consider an agreement with BMD for a machine feed. |
| **MPAs** | 7 MPAs, only some gazette-verified; SoNG is a bounding rectangle (≈5,645 km² vs 1,738 km² reported); unverified ⇒ NO ADVICE inside. | Load authoritative polygons; set `legal_status`. |
| **Trawler/IFA rule** | `VZ_TRAWLER_IFA` is `pending_verification` ⇒ trawlers in the IFA get NO ADVICE. | Verify clause (Marine Fisheries Act 2020 / Rules 2023) → set `approved`. |
| **Crowding, life-stage** | Not assessed; excluded from U (shown as "not assessed"). | Needs vessel-density (AIS/VMS) and size-at-capture data. |
| **Sanctuary / Sundarbans closures** | Listed under *not yet evaluated*. | Provide official polygons and notices. |
| **Bangla text** | First draft. | Native review with fisher communities; test audio on target phones. |

## What the validation says (honestly)
`scripts/validate_events.py` compares the thesis **seasonal PAI** with the 2020–2025 in-situ workbook, one row per event, with a spatial-block bootstrap:
* Spearman ρ (PAI vs event CPUE) ≈ **−0.03**, 95 % CI ≈ [−0.11, +0.05]; Hilsa-only ρ ≈ +0.00. **No demonstrated agreement.**
* The workbook is **internally inconsistent** for logbook data: fishing hours and effort differ between the 26 species rows of the *same* event; all 26 species have near-equal mean CPUE (CV 1.8 %); SST differs between rows of one event.
* Therefore the null result **cannot be attributed to the PAI alone**. Re-check the workbook against original logbooks before calibrating or claiming skill.
* Never split the 26 species rows randomly for model testing — group by event (DLC_ID).

## Other caveats
* 67 of 2,125 thesis stations are on land / too shallow and are excluded.
* Open-Meteo marine data are model output on a coarse grid; coastal wave/wind errors can be large. Hazards are sampled at ≈54 points and IDW-interpolated; spatial support is part of confidence.
* "Safe" means *model-assessed conditions are favourable*; it is not a safety guarantee. The app does not replace BMD signals, vessel judgement or fisheries law.

* **2026 mother-Hilsa closure is species-specific in the authoritative public notice.** The 3-tap frontend does not ask species/gear; during that ban the general legal gate returns **NO ADVICE**, while backend evaluation with `target_species="hilsa"` returns **NO-GO**. This avoids implying all non-Hilsa fishing is banned or permitted. Confirm any gear-wide orders separately.
