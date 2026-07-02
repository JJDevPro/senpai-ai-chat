---
name: race-projection-skill
description: "AI Coach Race-Projektions-Engine für den Athleten. PFLICHT laden bei jeder Renn-Planung, Zielzeit-/Cutoff-Frage oder Pace-Strategie für ein konkretes Rennen — auch ohne explizites Stichwort. Trigger: Keywords race/Rennen/HM/Halbmarathon/Marathon/cutoff/Besenwagen/Zielzeit/Firmenlauf/Stadtlauf/10km/Pace-Strategie, der Race-Command, anstehender Renntermin. Liefert: 4-Szenarien-Pace-Projektion (Best/Real/Konservativ/Cutoff), Cutoff-Math, Pace-Band-Visualisierung gegen Zielzeit, Decoupling-Quellen-Hierarchie, Kardio-vs-Neuromuskulär-Diagnose. Nutzt Race_Strategie.md + 21km.gpx (aus der privaten Drive personal-folder gepullt). NICHT für normale Lauf-Analyse (dafür run-bundle-skill)."
---

# Race-Projection-Skill v1.1 — Senpai Race-Engine (skriptiert)

> Senpai lädt diese Datei bei Race-/Cutoff-/Zielzeit-Fragen oder dem `Race`-Command.
> **Personal-Module (aus der privaten Drive personal-folder `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` pullen, NICHT mehr aus `modules/`):**
> ```bash
> python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match Race_Strategie.md --out ./data   # → ./data/Race_Strategie.md (Pacing, Strecke)
> python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match 21km.gpx --out ./data            # → ./data/21km.gpx (HM-Geometrie)
> ```
> + Wetter via `weather-runprep-skill`.
> **Body-Comp-Hebel:** jeder kg = +0,025 W/kg + −0,9 kcal/km. Live-Gewicht aus `./data/live.md` (erst pullen: `python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data`).

---

## 1. Rennkalender (Live-Anker aus ./data/live.md prüfen)

> Live-Anker erst pullen: `python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data` → dann `./data/live.md` lesen.

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
```bash
python3 lib/pull_drive.py --sheet 1zhNbm7f2SOeJL0QWGhaDt113R61tmHvi0KZCT1Z0sxU --tab "Trainings" --out ./data/Trainings_v5.csv
python3 .claude/skills/daily-check-skill/scripts/stats.py race_readiness \
  --trainings ./data/Trainings_v5.csv --as-of {heute} \
  --race-event "<Event>" --race-date <YYYY-MM-DD> --race-km <km>   # alles aus ./data/live.md
```
→ `projection.best/real/conservative` (Z2-Pace-Basis × Faktor, TSB-Nudge, MM:SS korrekt gerundet). Das 4. Szenario (🔴 Cutoff/Ziel) = Cutoff-Math aus 2b.

**2b. HM/Long-Race — Buffer-Math (`hm_projection`, run-bundle-§7-Formel skriptiert):**
```bash
python3 .claude/skills/daily-check-skill/scripts/stats.py hm_projection \
  --h1-pace <MM:SS> --decoupling <pct> --temp-c <T> --distance-km 21.1 \
  [--target-time H:MM:SS] [--cutoff-time H:MM:SS] [--sweep-pace MM:SS] \
  [--scenarios szenarien.json]   # Matrix: [{name,h1_pace,decoupling_pct,temp_c},…]
```
→ `H1a = H1 + HitzeTax(3,5 s/km/°C >18°C)` · `H2a = H1a×(1+Dec)` · `Projected = (H1a+H2a)×km/2`, plus **Cutoff-Puffer + Gehpausen-Budget** (`cutoff.walk_budget`: km/Minuten gegen die Sweep-Pace, deterministisch). **Szenarien-Inputs (H1-Paces, Decoupling, Temp) kommen aus `./data/live.md` + `Race_Strategie.md` (Drive) — NIE aus dem Repo.** Decoupling nur aus validen Quellen (§4).

**2c. Pacing-Card (Renntag-Artefakt):**
```bash
python3 .claude/skills/run-bundle-skill/scripts/pacing_card.py \
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
