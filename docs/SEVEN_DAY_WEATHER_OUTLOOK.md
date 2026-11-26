# JeleBondhu v1.2 — 7-day Marine Weather Outlook

- Open-Meteo Marine and Weather both request `forecast_hours=168` to cover seven future 24-hour periods.
- The Bangla-first `fisher.html` page shows up to seven weather cards: maximum wave height, maximum 10 m wind, minimum visibility, and possible thunderstorm code.
- The existing now / +12 h / +24 h trip analysis is retained. **No seven-day validated PFZ or catch forecast exists.** Today's experimental PAI is not propagated into a 7-day forecast.
- Live favourable trip/caution classes are withdrawn if the estimated return date exceeds the validity of the human-verified BMD bulletin.
- Actual weather source may provide missing variables or a shorter horizon. Missing values display dashes; the last day may be partial and is labelled with its available hours.
- Weather forecast accuracy falls with lead time; provider's model is not an official maritime warning or route safety assessment.
- To use the patch, upload the package contents to the repository and rerun GitHub Actions; never upload a ZIP *as* a GitHub file.
