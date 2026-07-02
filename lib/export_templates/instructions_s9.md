## 9. 🧭 TRIGGER-ROUTER

Auf claude.ai gibt es **keine Slash-Commands** — Skills feuern automatisch über ihre Beschreibung. Die Trigger-Phrasen unten stehen wortgleich in den Skill-Descriptions; zieht ein Skill nicht automatisch, **explizit benennen** („nutze run-bundle-skill“). **Step-0-Reflex bleibt:** Wenn ein Trigger Daten braucht, werden sie zuerst beschafft (Upload anfordern / Projekt-Datei lesen / Connector), dann reduziert das Skill-Skript auf Aggregate.

| Trigger | → Skill / Quelle |
|---|---|
| „analysier den Lauf“, „runanalyse“, FIT-/ZIP-Upload eines Laufs, Lauf <24h | **run-bundle-skill** |
| „Gym-Report“, „gymanalyse“, Krafttraining-ZIP, Übungs-Text mit Gewichten | **gym-bundle-skill** |
| Daily Check / „Status“ / „wie war die Nacht“ / Begrüßung ohne Aufgabe / „Briefing“ | **daily-check-skill** |
| „makro“, „essen“, „protein“, „kcal“, „supplement“, „casein“, „wasser“, Gewichts-Update, `Macros` | **nutrition-skill** |
| Trainingstag Mo/Mi/Sa/Do, „lauf/wetter/regen/hitze/pace/schuhe“, Pre-Lauf-Fenster | **weather-runprep-skill** |
| „race“, „HM“, „cutoff“, „Besenwagen“, Renn-Name, Race-Projektion, `Race` | **race-projection-skill** (Race-Strategie + GPX im Bundle) |
| `Payload` / Sonntag-KW-Abschluss | **payload-skill** (bevorzugt im Repo-Zwilling; hier = mobiler Fallback) |
| `Sync` / KW-Start / Driftverdacht / `Menu` / „was kann ich gerade tun“ | **sync-skill** |
| Z2-Steuerung, Flex-Regel, Laufform-Tiefe, Pace@Z2-Methodik | `references/V3_Protocol.md` (run-bundle-Bundle) |
| Schuhwahl, Blasen, Socken, GCT-Monitoring, Equipment-Blacklist | `Schuhe_Ausruestung.md` (Projekt-Datei) |
| Gym-Übungen, Geräte-IDs, Biomechanik | `Kraft-Programm.md` (Projekt-Datei) |
| Schlaf-/HRV-Anomalie, Sensor-Warnung | `Schlaf_HRV_Baseline.md` (Projekt-Datei) |
| Stagnation, Rebound, 10-Jahres-Historie | `Historie.md` + `Archiv_Historie.md` (Drive-Connector bei Trigger) |
| JSON/CSV/FIT-Struktur, Parsing-Frage | `references/Daten_Parsing.md` (run-bundle-Bundle) |
| `Backlog` / „was steht noch offen“ | `backlog.md` (Projekt-Datei) |

**Quick-Commands (inline, kein Skill nötig):** `HRV` · `VO2` · `Roast` · `Coaching` · `Pace@Z2` (**liest den Engine-Wert aus `live.md` — NIE im Kopf aus Läufen rekonstruieren**) · `Schuhe`/`gear` (liest `gear.md` → Schuh-km-Tabelle + Rotations-Ampel) → knapper strukturierter Output mit Ampeln (Sektion 5).
