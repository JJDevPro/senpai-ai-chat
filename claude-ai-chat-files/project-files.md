# Projekt-Wissen: Ziel-Zustand + Umbau-Checkliste

Ziel: **State-Bus statt Datei-Friedhof** — Drive-synchronisierte State-Dateien rein (auto-aktuell, geteilt mit dem Repo-Zwilling), große statische Referenzen raus (stecken jetzt in den Skill-Zips, kosten dort 0 Token bis zum Zugriff). Erwartung: Kapazität fällt deutlich unter die aktuellen ~62 %.

## ✅ REIN — als Drive-synchronisierte Projekt-Dateien (aus dem Ordner „Senpai-AI-Chat“)

| Datei | Rolle |
|---|---|
| `athlete.md` | Identität (Name, Anreden, Medical/Sensor, Equipment, Menschen, Rhythmus) |
| `live.md` | Live-State (SoT-Gewicht/KFA, PRs, HRV/VO2/Pace@Z2-Trend, Race-Kalender, Overrides) |
| `baselines.md` | PR-SSoT + Referenzlinien |
| `learnings.md` | Destillierte Learnings |
| `coaching_cues.md` | Offene/geschlossene Form-Cues |
| `gear.md` | Schuh-km + Segment-Baselines |
| `backlog.md` | Coaching-Backlog |
| `readiness-history.csv` | Tages-Trend-Store (CTL/ATL-Anker) |
| `trend_snapshot.md` | Wochen-/Monats-Rollup |
| `Kraft-Programm.md` | Geräte/Biomechanik-Referenz |
| `Schuhe_Ausruestung.md` | Schuh-/Equipment-Regeln (inkl. Blacklist) |
| `Schlaf_HRV_Baseline.md` | Schlaf-/HRV-Referenz |

> Wichtig: als **Drive-Dateien** hinzufügen (Connector → „aus Drive hinzufügen“), NICHT als statischer Upload — nur dann bleiben sie automatisch aktuell.

## ❌ RAUS aus dem Projekt-Wissen

| Datei | Warum / wo sie jetzt lebt |
|---|---|
| `V3_Protocol.md` | im run-bundle-Zip (`references/`) |
| `Daten_Parsing.md` | im run-bundle-Zip (`references/`) |
| `21km.gpx` | im race-Zip (`assets/`) — 2.545 Zeilen Projekt-Kapazität gespart |
| `Race_Strategie.md` | im race-Zip (`assets/`) |
| `Trainings_v5` (Drive-Sheet) | RAG-lossy + riesig; ersetzt durch den `readiness-history.csv`-Anker. Voll-Replay = Repo-Zwilling |
| `Gesundheitsdaten_v5` (Drive-Sheet) | dito |
| `Historie.md` / `Archiv_Historie.md` | Drive-only; bei Trigger per Connector lesen (2.183 Zeilen gespart) |
| Alte Projekt-Anweisungen v9.0.3 | ersetzt durch `project-instructions.md` |
| Strava-Hilfsdateien (`activity_stream_types`, `athlete_profile`, `supported_sports`) | überflüssig — der Strava-Connector liefert live; Streams sind ohnehin verboten |

## Reihenfolge

1. Erst REIN-Liste hinzufügen (Drive-Sync prüfen: Datei öffnen → aktueller Inhalt?).
2. Dann RAUS-Liste entfernen.
3. Kapazitätsanzeige notieren (vorher/nachher) und beim Smoke-Test-Report mitgeben.
