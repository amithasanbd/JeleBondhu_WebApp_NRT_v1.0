# Fisher mode — design notes

**Users:** small/medium-scale fishers, many with low literacy, patchy or no network offshore, mid-range Android phones.

* **Three taps**: port (anchor icons + Bangla names) → boat (3 silhouettes + range) → time. Choices are remembered.
* **One answer**: a large circle with *shape + colour + word* (✓ green · ! amber · ✕ red · ? grey) so it works for colour-blind users and in sunlight; one Bangla sentence; up to 3 zones with a **rotating arrow, compass word, nautical miles and hours**.
* **Audio**: "Listen" uses the phone's Bangla text-to-speech when installed (hidden/alert if not). Pre-recorded human audio is the better long-term option.
* **Low bandwidth** (measured, compressed): first visit ≈ 30 KB (app shell 23 KB + data 7 KB); later refreshes ≈ 7 KB because the service worker keeps the shell. The full dashboard is ≈ 0.3 MB on first visit (it includes the 137 KB offline bathymetry map), cached afterwards.
* **Offline**: service worker keeps the last verified bundle. The app shows its age; SAFE/CAUTION switch off after 12 h and everything after 30 h.
* **Share/SMS**: "Share" sends a short text; `live/sms.json` has SMS-ready Bangla/English messages (UCS-2, ≈70 characters/segment).
* **Always** shows "check the official BMD warning" and, when unverified, says why no FAVOURABLE is given.
* **Not in this version**: cell-broadcast, USSD, VHF/IVR voice, WhatsApp bot, community reporting — good next steps.

## Field-testing checklist (before any public launch)
1. Review Bangla text with fishers and local officers; replace weak words.
2. Test on 3–5 real phones (Android 8+), low-light and sunlight, with and without data.
3. Walk through ✓ / ! / ✕ / ? scenarios with fishers; check they understand "no advice ≠ safe".
4. Validate provisional vessel limits and port waypoints with boat owners and port authorities.
5. Agree the daily BMD-verification routine and who is responsible when the verifier is unavailable.
