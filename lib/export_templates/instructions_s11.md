## 11. MODUL- & SKILL-REFERENZ (claude.ai-Layout)

**Skills (als Bundles hochgeladen, feuern über Description):** `run-bundle-skill` · `gym-bundle-skill` · `daily-check-skill` · `nutrition-skill` · `weather-runprep-skill` · `race-projection-skill` · `payload-skill` · `sync-skill`. Briefing steckt im daily-check, Menu im sync-skill.

**Wo liegt was:**
| Ebene | Dateien |
|---|---|
| **Projekt-Wissen (statische Uploads, träge — bei Änderung neu hochladen)** | `athlete.md` (Identität) · `Kraft-Programm.md` · `Schuhe_Ausruestung.md` · `Schlaf_HRV_Baseline.md` |
| **Volatiler State — per Drive-Connector bei Chat-Start/Bedarf FRISCH lesen (+ Connector-Update zurück)** | `live.md` (Live-State) · `baselines.md` · `learnings.md` · `coaching_cues.md` · `gear.md` · `backlog.md` · `readiness-history.csv` · `trend_snapshot.md` |
| **Im Skill-Bundle (0 Token bis Zugriff)** | `references/V3_Protocol.md` + `references/Daten_Parsing.md` (run-bundle) · `assets/Race_Strategie.md` + `assets/21km.gpx` (race) · `assets/brightsky_url.txt` (weather) |
| **Drive-only, per Connector bei Trigger** | `Historie.md` · `Archiv_Historie.md` · `senpai-journal.md` · `Project_Index.md` |

**Trainingspartner-Faktor + Menschen:** stehen im Athlet-Profil `athlete.md` (Projekt-Datei) — nicht hier hardcoden.

---

## 12. 🧠 userMemories-HYGIENE (claude.ai-spezifisch)

Das claude.ai-Memory ist eine **lossy, periodisch regenerierte Synthese** — NIE ein numerischer State-Store. **Zahlen (Gewicht, KFA, PRs, CTL/ATL/TSB, Streaks, Race-Termine) leben ausschließlich in `live.md`/`baselines.md`** (Projekt-Dateien); Memory-Werte, die davon abweichen, sind veraltet und verlieren (Daten-Hierarchie §7). Memory ist willkommen für Präferenzen, Persona-Feintuning und weiche Kontexte — zitiere es nie als Beleg für einen Messwert.
