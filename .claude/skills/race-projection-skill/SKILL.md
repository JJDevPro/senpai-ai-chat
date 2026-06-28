---
name: race-projection-skill
description: "AI Coach Race-Projektions-Engine für den Athleten. PFLICHT laden bei jeder Renn-Planung, Zielzeit-/Cutoff-Frage oder Pace-Strategie für ein konkretes Rennen — auch ohne explizites Stichwort. Trigger: Keywords race/Rennen/HM/Halbmarathon/Marathon/cutoff/Besenwagen/Zielzeit/Firmenlauf/Stadtlauf/10km/Pace-Strategie, der Race-Command, anstehender Renntermin. Liefert: 4-Szenarien-Pace-Projektion (Best/Real/Konservativ/Cutoff), Cutoff-Math, Pace-Band-Visualisierung gegen Zielzeit, Decoupling-Quellen-Hierarchie, Kardio-vs-Neuromuskulär-Diagnose. Nutzt Race_Strategie.md + 21km.gpx (aus der privaten Drive personal-folder gepullt). NICHT für normale Lauf-Analyse (dafür run-bundle-skill)."
---

# Race-Projection-Skill v1.0 — Senpai Race-Engine

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

## 2. 4-Szenarien-Projektion (Pflicht-Format)

Aus aktueller Pace@Z2 / Parkrun-Effort + Distanz + Wetter + Streckenprofil:

| Szenario | Annahme | Projizierte Zeit | Ø-Pace |
|---|---|---|---|
| 🟢 **Best Case** | optimale Bedingungen, voller Effort, kein Wand-Event | … | … |
| 🔵 **Realistisch** | erwartbare Bedingungen, Trainingspartner-Faktor, 1–2 strategische Gehpausen | … | … |
| 🟡 **Konservativ** | Hitze/Wind-Penalty, frühe Ermüdung, mehr Gehpausen | … | … |
| 🔴 **Cutoff/Ziel** | Mindestleistung vs Wertungsgrenze | … | … |

**Cutoff-Math:** Ziel-Zeit ÷ Distanz = erforderliche Ø-Pace. Puffer ausweisen (Sekunden/km Reserve gegen Cutoff). Gehpausen-Budget einrechnen (beim Körpergewicht aus dem Profil strategisch korrekt).

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

**Ende race-projection-skill v1.0.** 4 Szenarien, Cutoff-Puffer ausweisen, Decoupling nur aus validen Quellen, Wand = neuromuskulär ≠ Kardio.
