# Projekt-Wissen: Ziel-Zustand + Umbau-Checkliste (v2 — Hybrid-State-Bus)

> **Warum v2:** Rohe `.md`-Dateien aus Drive lassen sich NICHT als synchronisierte
> Projekt-Dateien anbinden („URL-Auflösung fehlgeschlagen“) — der Projekt-Wissen-Sync
> kann nur Google-native Formate (Docs/Sheets). Deshalb: träge Dateien als
> **statischer Upload**, volatiler State per **Drive-Connector-Read bei Chat-Start**
> (so lief das alte Projekt jahrelang — jetzt ist es explizit geregelt).

## ✅ REIN — statische Uploads ins Projekt-Wissen (Datei herunterladen → hochladen)

| Datei | Rolle | Re-Upload nötig |
|---|---|---|
| `athlete.md` | Identität (Name, Anreden, Medical/Sensor, Equipment, Menschen, Rhythmus) | selten (bei Profil-Änderung) |
| `Kraft-Programm.md` | Geräte/Biomechanik-Referenz | selten |
| `Schuhe_Ausruestung.md` | Schuh-/Equipment-Regeln (inkl. Blacklist) | selten |
| `Schlaf_HRV_Baseline.md` | Schlaf-/HRV-Referenz | selten |

> Diese vier ändern sich träge — eine statische Kopie ist als Grundkontext gut genug.
> Die Projekt-Anweisungen sagen Senpai, dass bei Zweifel der Connector-Stand gewinnt.

## 🔄 NICHT hochladen — volatiler State läuft über den Drive-Connector

`live.md` · `baselines.md` · `learnings.md` · `coaching_cues.md` · `gear.md` ·
`backlog.md` · `readiness-history.csv` · `trend_snapshot.md`

Diese Dateien liest Senpai **bei Chat-Start bzw. bei Bedarf frisch per
Google-Drive-Connector** aus dem Ordner „Senpai-AI-Chat“ (Step-0-Reflex, steht in
Anweisungen + Skill-Preambles) und schreibt sie per Connector-Update zurück.
Eine statische Kopie im Projekt-Wissen wäre nach einer Woche eine Zahlen-Lüge —
deshalb bewusst NICHT hochladen. **Voraussetzung: Google-Drive-Connector ist im
Projekt verbunden (im Web einrichten, iOS-Connector-Install ist Beta).**

## ❌ RAUS aus dem Projekt-Wissen (Alt-Bestand)

| Datei | Warum / wo sie jetzt lebt |
|---|---|
| `V3_Protocol.md` | im run-bundle-Zip (`references/`) |
| `Daten_Parsing.md` | im run-bundle-Zip (`references/`) |
| `21km.gpx` | im race-Zip (`assets/`) — 2.545 Zeilen Projekt-Kapazität gespart |
| `Race_Strategie.md` | im race-Zip (`assets/`) |
| `Trainings_v5` (Drive-Sheet) | RAG-lossy + riesig; ersetzt durch den `readiness-history.csv`-Anker (Connector). Voll-Replay = Repo-Zwilling |
| `Gesundheitsdaten_v5` (Drive-Sheet) | dito |
| `Historie.md` / `Archiv_Historie.md` | Drive-only; bei Trigger per Connector lesen (2.183 Zeilen gespart) |
| Alte Projekt-Anweisungen v9.0.3 | ersetzt durch `project-instructions.md` |
| Strava-Hilfsdateien (`activity_stream_types`, `athlete_profile`, `supported_sports`) | überflüssig — der Strava-Connector liefert live; Streams sind ohnehin verboten |

## Reihenfolge

1. Google-Drive-Connector im Projekt verbinden/prüfen (Web) — Smoke-Test S7 gate-t das.
2. Die 4 statischen Uploads hinzufügen (als **Datei-Upload**, nicht als Drive-URL).
3. RAUS-Liste entfernen, neue Projekt-Anweisungen einpasten.
4. Kapazitätsanzeige notieren (vorher/nachher) und beim Smoke-Test-Report mitgeben.
