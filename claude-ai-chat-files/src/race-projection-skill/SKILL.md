---
name: race-projection-skill
description: "Senpais Race-Engine. Trigger: race, Rennen, HM, Halbmarathon, 10km, Zielzeit, cutoff, Besenwagen, Pace-Strategie. 4-Szenarien-Projektion, Cutoff-Math, Pacing-Card."
---


# Race-Projection-Skill v1.1 — Senpai Race-Engine (skriptiert)

## §0-CAI · Laufzeit & Datenbeschaffung (claude.ai)

> Dieses Bundle ist der claude.ai-Zwilling des Repo-Skills — gleiche Engines, gleicher Verdict-Kontrakt (Skripte rechnen, der LLM spricht). Skripte laufen in der Code-Sandbox (Python 3.11). Vorbereitung: `mkdir -p ./data`. Den Skill-Ordner per `ls` unter `/mnt/skills/` finden (Pfade nie blind hardcoden), Skripte als `python3 scripts/<name>.py` aus dem Skill-Ordner aufrufen.

**Datenbeschaffung:**

| Was | Woher |
|---|---|
| Race_Strategie.md · 21km.gpx | im Bundle: `assets/` (beim Export aus Drive eingefroren — bei Race-Strategie-Änderung Re-Export nötig) |
| live.md (Race-Kalender, Countdown, Gewicht) | per Drive-Connector frisch lesen (Zahlen-SSoT) |
| Referenz-Läufe (Decoupling-Quelle) | letzter Run-Report bzw. FIT-Upload (run-bundle-skill) |

**State-Read:** Rohe `.md`-State-Dateien lassen sich in claude.ai NICHT als Drive-synchronisierte Projekt-Dateien anbinden (Sync kann nur Google-native Formate). Regel: statische Kopie im Projekt-Wissen = Grundkontext; bei Zahlen-Relevanz (`live.md`, `baselines.md`, `gear.md`, `readiness-history.csv`) die Datei per Drive-Connector aus „Senpai-AI-Chat“ FRISCH lesen — Connector-Stand schlägt jede statische Kopie.

**Write-Back:** Google-Drive-Connector — die BESTEHENDE Datei im Drive-Ordner „Senpai-AI-Chat“ aktualisieren (nie ein Duplikat anlegen). Fallback bei fehlgeschlagenem Write: kompletten neuen Datei-Inhalt als Code-Fence ausgeben, der User ersetzt ihn in Drive.

**Kernregel:** Roh-Serien (Per-Sekunde/-Minute) erreichen NIE den Kontext — Skripte reduzieren in der Sandbox, gelesen werden nur die kompakten JSON-Aggregate. Roh-Dateien (JSON/FIT/ZIP) NIE per Drive-Connector ziehen (landet im Kontext!) — immer als Chat-Upload anfordern (landet in der Sandbox).

---


> Senpai lädt diese Datei bei Race-/Cutoff-/Zielzeit-Fragen oder dem `Race`-Command.
> **Personal-Module (liegen im Skill-Bundle):** `assets/Race_Strategie.md` (Pacing, Strecke) + `assets/21km.gpx` (HM-Geometrie) — direkt aus `assets/` lesen, kein Pull nötig.
> + Wetter via `weather-runprep-skill`.
> **Body-Comp-Hebel:** jeder kg = +0,025 W/kg + −0,9 kcal/km. Live-Gewicht aus `live.md` (Projekt-Datei — steht im Kontext; für Skript-Inputs bei Bedarf nach `./data/live.md` schreiben).

---

## 1. Rennkalender (Live-Anker aus ./data/live.md prüfen)

> Live-Anker: `live.md` ist Projekt-Datei — Renn-Kalender/Countdown/Status direkt aus dem Kontext lesen (für Skript-Inputs bei Bedarf nach `./data/live.md` schreiben).

| Datum | Event | Distanz | Status |
|---|---|---|---|
| (aus Renn-Kalender, live.md) | HM-Zielrennen | 21 km | Status + letztes Ergebnis aus ./data/live.md |
| (aus Renn-Kalender, live.md) | Firmenlauf | ~6 km | anstehend (Termin aus ./data/live.md) |
| (aus Renn-Kalender, live.md) | Stadtlauf | 10 km | anstehend (Termin aus ./data/live.md) |

> Konkrete Events/Termine/Distanzen/Countdown immer gegen `./data/live.md` abgleichen — Kalender driftet, alle Renn-Spezifika leben in live.md.

---

## 2. 4-Szenarien-Projektion (SKRIPTIERT — der EINZIGE Rechenpfad)

**⛔ Kein Kopfrechnen.** Jede projizierte Zeit/Pace kommt aus den Skripten (Entscheidung #11); der Report übersetzt nur in Persona-Text.

**2a. Kurz-Distanz (≤10 km, Firmenlauf/Stadtlauf/Parkrun-Effort) — `race_readiness`:**
**Trainings-Daten bereitstellen:** `Trainings_v5.csv` als Chat-Upload anfordern (NIE die Roh-Tabelle per Drive-Connector in den Kontext ziehen), Upload-Pfad per `ls` verifizieren, dann `mkdir -p ./data` und die Datei nach `./data/Trainings_v5.csv` kopieren.
```bash
python3 scripts/stats.py race_readiness \
  --trainings ./data/Trainings_v5.csv --as-of {heute} \
  --race-event "<Event>" --race-date <YYYY-MM-DD> --race-km <km>   # alles aus ./data/live.md
```
→ `projection.best/real/conservative` (Z2-Pace-Basis × Faktor, TSB-Nudge, MM:SS korrekt gerundet). Das 4. Szenario (🔴 Cutoff/Ziel) = Cutoff-Math aus 2b.

**2b. HM/Long-Race — Buffer-Math (`hm_projection`, run-bundle-§7-Formel skriptiert):**
```bash
python3 scripts/stats.py hm_projection \
  --h1-pace <MM:SS> --decoupling <pct> --temp-c <T> --distance-km 21.1 \
  [--target-time H:MM:SS] [--cutoff-time H:MM:SS] [--sweep-pace MM:SS] \
  [--scenarios szenarien.json]   # Matrix: [{name,h1_pace,decoupling_pct,temp_c},…]
```
→ `H1a = H1 + HitzeTax(3,5 s/km/°C >18°C)` · `H2a = H1a×(1+Dec)` · `Projected = (H1a+H2a)×km/2`, plus **Cutoff-Puffer + Gehpausen-Budget** (`cutoff.walk_budget`: km/Minuten gegen die Sweep-Pace, deterministisch). **Szenarien-Inputs (H1-Paces, Decoupling, Temp) kommen aus `live.md` (Projekt-Datei) + `assets/Race_Strategie.md` (Skill-Bundle) — NIE raten oder hardcoden.** Decoupling nur aus validen Quellen (§4).

**2c. Pacing-Card (Renntag-Artefakt):**
```bash
python3 scripts/pacing_card.py \
  --race "<Event>" --distance-km <km> --readiness rr.json [--temp-c <T>]
```
→ Even-/Negativ-Split-Tabelle (summiert exakt zur Zielzeit), HF-Phasen-Steuerung, Start-Disziplin, deterministische V3-Hitze-Tax.

**Pflicht-Format im Report** (Zahlen = Skript-Output):

| Szenario | Annahme | Projizierte Zeit | Ø-Pace |
|---|---|---|---|
| 🟢 **Best Case** | `best`-Band bzw. Best-Szenario | … | … |
| 🔵 **Realistisch** | `real`-Band / Realist-Szenario | … | … |
| 🟡 **Konservativ** | `conservative` / Heiß+Müde | … | … |
| 🔴 **Cutoff/Ziel** | Cutoff-Math (2b): Puffer + Gehpausen-Budget | … | … |

---

## 3. Pace-Band-Visualisierung

Bei Trend-Kontext: **Pace-Band-Chart** (Matplotlib, Ampel-Farben) — KM-Achse × Pace, mit horizontalem Cutoff-/Ziel-Band und projizierter Linie pro Szenario. Sarkastische Einordnung Pflicht (Instructions §10). Nur bei echtem Mehrwert, nicht bei Single-Point.

---

## 4. Decoupling-Quellen-Hierarchie (Anti-Halluzination)

Für HM/Long-Race-Projektionen NUR valide Decoupling-Quellen nutzen:
1. **Echter Long Run / Race-Sim** (Endurance, HR-stabil) = bester Prädiktor.
2. **Letzter vergleichbarer Long Run** (Trainings_v5).
3. **NIEMALS** Decoupling aus einem **Intervall-Workout** als HM-Prognose verwenden = Skill-Bruch.

---

## 5. Kardio-vs-Neuromuskulär-Diagnose (Wand-Analyse)

Wenn ein Pace-Einbruch/Run-Walk-Eskalation gemeldet wird:
- **Langsamster KM bei NIEDRIGSTER HR** → neuromuskulär/Foot-Durability/Glykogen, NICHT Kardio-Limit → Taper-fokussiert, KEINE Cutoff-Panik.
- HM-KW26-Lektion (km 17–20): Limit war Füße (rein muskulär), Fueling hielt. Hebel: Posterior-Chain-Kraft, Waden-Resilienz, progressive Long-Run-Volumen, Gewichtsreduktion.
- **Cutoff-Panik NICHT aus neuromuskulärer Ermüdung, Intervall-Decoupling oder methodisch ungültigen Metriken.**

---

## 6. Verdict-Härtegrad nach Countdown

| Abstand zum Race | Ton |
|---|---|
| ≥22 Tage | konstruktiv, Hebel benennen |
| 14–21 Tage | härter, Hebel-Forderungen |
| ≤7 Tage | taper-fokussiert, KEINE neuen Sorgen säen |

---

**Ende race-projection-skill v1.1.** 4 Szenarien AUS DEN SKRIPTEN (`race_readiness`/`hm_projection`/`pacing_card`), Cutoff-Puffer + Gehpausen-Budget deterministisch, Decoupling nur aus validen Quellen, Wand = neuromuskulär ≠ Kardio.

---
> Export-Stand: race-projection-skill v1.1 · senpai-ai-chat@ebb935d · content f97c6330fce6 · generiert von export_claude_ai.py — NICHT von Hand editieren.
