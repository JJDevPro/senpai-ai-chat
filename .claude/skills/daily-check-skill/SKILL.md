---
name: daily-check-skill
description: "AI Coach Daily Check für den Athleten — WHOOP-artiges Tages-Dashboard. PFLICHT laden bei: dem dailycheck-Command, Daily Check/Morgen-Check/Status/wie war die Nacht/wie sehen die Werte aus, sowie weichen Triggern wie was geht ab/was steht an/wie läufts/Update und Begrüßung ohne Aufgabe (Hi Senpai/Moin). Liefert: Recovery-Ampel, Schlaf-Score, Gestern-Load (TRIMP + CTL/ATL/TSB), HRV-Feinverlauf (15-Min) + KW-Heatmap, kompakte Makro-Compliance (gestern), KW-Trend, Pre-Lauf-Briefing an Trainingstagen, Heute-Plan, Senpais Urteil. Zieht zwei Tages-JSONs (heute+gestern, Mitternachts-Merge) lokal nach ./data via pull_drive.py und reduziert sie deterministisch per slice_hae_day.py. NICHT bei spezifischen Aufgaben wie Lauf-/Gym-Analyse, Was soll ich essen, oder Einzeldaten-Fragen."
---

# Daily-Check-Skill v0.16 — "Senpai-WHOOP"

> Modul-Datei. Senpai liest sie automatisch beim Daily-Check-Trigger oder per `/dailycheck`.
>
> **Zweck (v0.4 neu definiert):** Der Daily Check ist kein "Wie war die Nacht?" mehr, sondern eine **WHOOP-artige Tages-Übersicht**: *Was hat mein Körper GESTERN geleistet (Load) → wie habe ich darauf REGENERIERT (Schlaf/HRV) → was heißt das für HEUTE (Readiness + Coaching).* Eine echte Tages-Retro mit Tiefe, Trends, persönlicher Bedeutung und Urteil.
>
> **v0.4 Hauptänderungen ggü. v0.3.2:**
> - **Tageszeit-Adaption GEDROPPT.** Keine gedämpften Modi mehr — der Check ist IMMER voll. (der Athlet: "Wenn ich das will, bekomme ich das auch.")
> - **Neue 🎯 Tages-Übersicht (WHOOP-Card):** Recovery-Ampel + Schlaf-Score + Gestern-Load auf einen Blick.
> - **Neue 📆 Gestern-Retro:** voller gestriger Tag (Load, Tages-Herz, Recovery-Link), inkl. **tiefem Trainings-Load: TRIMP + CTL/ATL/TSB** aus `Trainings_v5` (zieht v0.6-Roadmap vor).
> - Ausführliches Output mit Tabellen, Emojis, voller Persona und **SENPAIS URTEIL**.
> - **Beibehalten aus v0.3.2:** Zwei-Datei-Merge (gestern+heute, Schlaf überspannt Mitternacht) + Datei-Disziplin (nur `YYYY-MM-DD`, nie Monats-Aggregat `YYYY-MM`).

-----

## 1. AUSLÖSE-LOGIK

**Harte Trigger (immer Full Daily Check):** `/dailycheck` · "Daily Check" / "Morgen-Check" / "Morgencheck" · "Status" / "Wie sehen die Werte aus?" / "Wie war die Nacht?"

**Weiche Trigger (Daily Check wird Standard-Antwort):** "Was geht ab" · "Was steht an" · "Wie läuft's" · "Update?" · Begrüßung ohne Aufgabe ("Hi Senpai", "Moin"). → Immer voll, keine Dämpfung mehr.

**KEINE Trigger:** Spezifische Aufgaben ("Analysiere meinen Lauf", "Was soll ich essen?") · lokale Datei in `./data` ohne Frage (Datei-/Bundle-Skill greift) · direkte Einzeldaten-Frage ("Wie ist mein VO2Max-Trend?") · Coaching-Folgefragen.

> **🥗 Ernährung IM Daily Check (v0.16):** Der Daily Check enthält selbst einen **kompakten Gestern-Makro-Block** (§7b — Protein-Floor + kcal/Fett/Carbs/Wasser) als vierte gleichwertige Säule (CLAUDE.md §1). Das ist KEIN „Was soll ich essen?"-Trigger — die **Voll-Engine** (Casein, Mittag-12:00, Supplements, Whitelist) bleibt `nutrition-skill` (/makro). Daily = Gestern-Compliance auf einen Blick; /makro = Tiefe.

-----

## 2. WORKFLOW (Pflicht-Reihenfolge)

```
Step 0:  KEIN Tool-Setup nötig — alle Daten kommen lokal via `python3 lib/pull_drive.py` nach
         `./data` + die gebündelten Scripts unter `.claude/skills/daily-check-skill/scripts/`.
         Drive ist read-only SoT (NIE zurückschreiben). Alle Aufrufe vom Repo-Root (CWD).
Step 1a: DATUM (Tag/Wochentag/KW) — NICHT aus API: User-Angabe → sonst Claudes internes Datum.
Step 1b: UHRZEIT (HH:MM): User-Angabe → **`lib/clock.py` (echte VM-Uhr → Europe/Berlin; der SessionStart-Hook druckt sie im 🗺️ HUD)** → `[Zeit n/a]` nur falls Clock-Read scheitert. CLAUDE.md §3. **Kein API, kein Raten.**
Step 2:  Wochentag → Trainingstag (Mo/Mi/Sa/Do)? → Wetterochs-Flag (PROAKTIV — auch wenn Rest empfohlen wird; Wetter ist Entscheidungs-Input).
Step 3:  ISO-KW + Montag dieser KW.
Step 3.5: INPUT-TYP: (a) EIN Multi-Day-Export vorhanden (Range-Datei
         `HealthAutoExport-YYYY-MM-DD-YYYY-MM-DD.json` in `./data`, Span >2 Tage) → MULTI-DAY-Pfad (§3f-bis),
         Steps 4-6 entfallen, weiter bei Step 7. (b) Sonst Standard: zwei Tagesdateien (Steps 4-6, §3f).
         **⛓️ SCOPE-INVARIANTE (nicht verhandelbar): Daily zieht IMMER mind. heute+gestern** — beide Tage gehen in slice_hae_day UND daily_signals (Step 8.5). Fragt der User explizit einen größeren Zeitraum (»diese KW«, »letzte 7 Tage«), wird der Range-Export / mehr Tagesdateien gezogen und alles in Relation gesetzt (§3f-bis). **NIE nur heute** — Single-Day = Vortag-Verlust (Daylight/Audio/Recovery-Link brechen, der 28.06-„3-min"-Glitch). Herkunft: der Skill kam aus claude.ai mit manuellem HAE-Upload (mind. heute+gestern, oft eine ganze KW) und hat stets den vollen Scope ausgelesen.
Step 4:  ZWEI Tages-JSONs nach `./data` ziehen (Muster YYYY-MM-DD, NIE YYYY-MM; §3b):
         ├── HEUTE:   python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-{heute}" --out ./data
         └── GESTERN: python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-{gestern}" --out ./data   ← Gestern wird VOLL ausgewertet
Step 5:  Beide lokalen JSON-Pfade + den Mitternachts-Merge + Ziel-Tag-Slicing in EINEM Aufruf:
         `python3 .claude/skills/daily-check-skill/scripts/slice_hae_day.py <heute_json> [<gestern_json>] --as-of {heute}` → JSON von stdout lesen (§3f).
         [Multi-Day: §3f-bis — EIN Range-File als `<heute_json>`, kein zweites Argument.]
Step 6:  slice_hae_day mergt die minuten-granularen Serien (HRV/HR/SpO2/Atmung) gestern+heute und slict auf die
         Ziel-Nacht (§3f / §3f-bis bei Multi-Day). Kein manuelles base64/json — die JSON-Ausgabe lesen.
Step 7:  sleep_analysis aus der slice_hae_day-JSON (sleepEnd == heute; §3f / §3f-bis bei Multi-Day).
Step 8:  GESTERN-LOAD aus der slice_hae_day-JSON: active_energy (Tagessumme), step_count, physical_effort (Ø/Peak),
         heart_rate (Tages-Ø wach / Peak / Uhrzeit), walking_hr.
         **Plus `load_extra`** (nur wenn vorhanden, §7): `true_tdee_kcal` (Grundumsatz+Aktiv → Energie-Bilanz),
         `exercise_min` + `flights_climbed` (Load-Proxys), `gait.asymmetry_pct`/`gait.double_support_pct`
         (Gang-Trip-Wire — NUR surfacen wenn `flag=True` = erhöht → Verletzungs-/Ermüdungs-Kontext).
         **Multi-Day: slice_hae_day filtert ZWINGEND auf den Vortag** (`day==gestern`), sonst Wochen-/Monats-Summe (§3f-bis).
Step 8.5: TAG-SIGNALE: `python3 .claude/skills/daily-check-skill/scripts/daily_signals.py <heute_json> <gestern_json> --as-of {heute}` (§3i) —
         **BEIDE Tagesdateien übergeben** (heute + gestern) ODER den Multi-Day-Export — daily_signals mergt sie, damit der **Vortag (`daylight`/`audio` `yesterday`) nie verhungert**. `--as-of {heute}` pinnt today/yesterday (PFLICHT, sonst = letzter Tag im Export).
         🛡️ **Vortag-Härtung (Glitch strukturell behoben):** Wird versehentlich NUR die Heute-Datei übergeben und fehlt der Kalender-Vortag, zieht daily_signals ihn via `--data-dir` (Default = Ordner der ersten Datei) selbst aus `./data` nach (`HealthAutoExport-<gestern>.json`) — nicht-fatal, wenn die Datei wirklich fehlt.
         Liefert Tageslicht, Schlaf-Effizienz, Wrist-Temp+Baseline, Audio-Tag-Kontext, VO2max/cardio_recovery-Fallback, Wasser **+ `dietary`** (Makros gestern+heute: Protein/kcal/Fett/Carbs/Ballaststoffe/Zucker/Wasser → §7b Ernährung).
Step 8.6: ⛔ SAFETY-GATE (deterministisch, NICHT verhandelbar — CLAUDE.md §6):
         `python3 .claude/skills/daily-check-skill/scripts/safety_gate.py <slice_json> [--injury] [--opt-out] [--prev-hrv N]`
         `<slice_json>` = die slice_hae_day-Ausgabe (Datei oder '-' via Pipe). Liefert
         `{gate,level,reasons,training_allowed,roast_allowed}`. Das Gate IMMER feuern und
         RESPEKTIEREN: `training_allowed=false` (HRV🔴🔴 <40 + Schlaf <6h) = Training
         STREICHEN, kein Verhandeln — übersteuert Plan-Matrix + Persona. `roast_allowed=false`
         (Verletzung/Opt-out) = Persona aus. `--prev-hrv` (gestern hrv_night.avg) bestätigt
         HRV🔴 als 2-Tage-Deload-Muster. AFib-Burden wird BEWUSST nicht gegated (§6 Medical).
Step 9:  TRAININGS-LOAD TIEF: Trainings_v5 nach CSV ziehen →
         `python3 lib/pull_drive.py --sheet 1zhNbm7f2SOeJL0QWGhaDt113R61tmHvi0KZCT1Z0sxU --tab "Trainings" --out ./data/Trainings_v5.csv` →
         🧮 `banister.compute_from_sheet(raw, as_of=heute)` (§3h) — Dedup + Kalendertag-Zerofill
         + DETERMINISTISCHES CTL/ATL/TSB in EINEM Aufruf. Plus gestrige Session (Typ, Dauer, TRIMP).
         TSB = heutige Readiness (CTL_gestern − ATL_gestern), Zeile via format_block(res).
         Wenn Duplikate entfernt (res['dedup_report']) → Sheet-Hygiene-Warnung in den Output (§5 🏋️-Block).
         Trainings_v5 nicht pullbar → TRIMP aus FIT/qualitativ + Hinweis, KEINE erfundenen Zahlen.
         ⚡ **INKREMENTELL (Snapshot-Beschleuniger, §7):** zuerst die letzte Zeile aus
         `readiness-history.csv` lesen (`readiness_history.last_row`); ist deren `date` == gestern
         UND ctl/atl vorhanden → `banister.compute_incremental(ctl, atl, date, gestern_TRIMP, heute)`
         = EIN EWMA-Schritt statt 126-Tage-Replay (Tokens/Zeit ↓, Ergebnis identisch). **ESCAPE-HATCH
         → volle `compute_from_sheet`** bei: Lücke (letzte Zeile < gestern), fehlendem/leerem Snapshot,
         `warmup_ok`-Zweifel, Anomalie ODER explizitem Deep-Dive. Im Zweifel gewinnt die Vollrechnung.
Step 10: Gesundheitsdaten_v5 nach CSV ziehen →
         `python3 lib/pull_drive.py --sheet 1ENUtb3LS5GgaDDhciBCuyUDqlwJTsjU6n6PTCZuIcDE --out ./data/Gesundheitsdaten_v5.csv` → nur KW-Zeilen (Trend).
Step 10.1: 🟢 HRV-STATUS (Garmin-Klon): 'Tägliche Kennzahlen'-Tab für die 60-Tage-HFV-Historie ziehen →
         `python3 lib/pull_drive.py --sheet 1ENUtb3LS5GgaDDhciBCuyUDqlwJTsjU6n6PTCZuIcDE --tab "Tägliche Kennzahlen" --out ./data/Taegliche_Kennzahlen.csv`
         `python3 .claude/skills/daily-check-skill/scripts/hrv_baseline.py --health-csv ./data/Taegliche_Kennzahlen.csv --as-of {heute}` → `{median,band,status}` (§6.5). LOW_FLOOR = safety_gate.HRV_RED (geteilt).
Step 10.2: 🔋 READINESS (0–100): die SCHON berechneten Aggregate fusionieren (KEIN Re-Compute) —
         `python3 .claude/skills/daily-check-skill/scripts/readiness.py --hrv-baseline <hrv_json|-> --daily <slice_json> --banister <banister_json> --safety-gate <gate_json>` → `{score,band,top_driver,top_limiter,safety_override}`.
         ⛔ Safety-Gate bleibt AUTORITATIV: rotes Gate deckelt den Score auf ≤35 (`safety_override=true`) — übersteuert alles (§13/§16).
Step 10.3: 🔋 BODY BATTERY: `python3 .claude/skills/daily-check-skill/scripts/body_battery.py --slice <slice_json> --hrv <hrv_json> --banister <banister_json> --as-of {heute}` → `{bb_start,bb_end,drained,recharged,status}` (§6.5). Heuristik/Surrogat, klar so labeln.
Step 10.4: 🏃 RUNNING TOLERANCE: `python3 .claude/skills/daily-check-skill/scripts/running_tolerance.py --trainings ./data/Trainings_v5.csv --as-of {heute}` → `{week_km,ceiling_km,acwr,ramp_flag,status}` (Verletzungs-Decke bei 116 kg → §13 Heute-Plan).
Step 10.5: 📈 HISTORY (T12, best-effort, NON-BLOCKING): Tageszeile nach Drive persistieren —
         `python3 .claude/skills/daily-check-skill/scripts/readiness_history.py --as-of {heute} --readiness <readiness_json> --body-battery <bb_json> --banister <banister_json> --hrv-baseline <hrv_json> --daily <slice_json> --signals <signals_json> --tolerance <tolerance_json>`.
         (Die erweiterte Zeile trägt jetzt ctl/atl/hrv_ms/rhr/weight/kfa/vo2/week_km — speist den inkrementellen Banister (Step 9) + den Trend-Snapshot.)
         Fehlt `readiness-history.csv` (noch nicht pre-seeded → `drive-seed/`) → Pre-Seed-Hinweis MELDEN, NICHT blockieren (Skript exitet ≠0, unkritisch für den Check).
Step 10.6: 📅 TREND-SNAPSHOT (PR2, best-effort, NON-BLOCKING): NACH dem History-Write den Woche+Monat-Rollup
         regenerieren + lesen — `python3 .claude/skills/daily-check-skill/scripts/trend_snapshot.py --as-of {heute}`.
         Baut/aktualisiert `trend_snapshot.md` aus `readiness-history.csv` (laufende Woche eingeschlossen) und lädt ihn nach Drive.
         **Der Multi-Wochen-/Monats-KW-Trend (§10) liest jetzt DIESEN Snapshot** — kein erneuter Gesundheitsdaten_v5-Replay
         für die zurückliegenden Wochen. HEUTE bleibt frisch gerechnet (Step 9/10.2). Fehlt der Snapshot/CSV → Pre-Seed-Hinweis
         MELDEN, NICHT blockieren; Fallback = Gesundheitsdaten_v5 wie bisher (Escape-Hatch).
Step 10.7: 📋 BACKLOG (PR3, best-effort, NON-BLOCKING): `backlog.md` aus Drive ziehen
         (`pull_drive.py --match backlog.md --out ./data`). Feuert heute ein **längerfristiges** Signal
         (z. B. Protein-Floor-Fail mehrtägig, HRV-Korridor-Drift, Re-Entry-Lücke) → unter `## Aktiv`/`## Hypothesen`
         ein Item ergänzen (Format = Template; **dedup** gegen Bestand, kein Spam). Wirkt ein offenes Item erledigt
         → nach `## Erledigt` mit Datum. Datei lokal regenerieren + `pull_drive.py --upload --name backlog.md`.
         Fehlt `backlog.md` → Pre-Seed-Hinweis MELDEN, NICHT blockieren. (Abgrenzung: Form-Cues → `coaching_cues.md`.)
Step 11: Wenn Trainingstag (Mo/Mi/Sa/Do, `lib/clock.is_training_day`): **`weather-runprep-skill` automatisch laden + ausführen**
         (voller Workflow: präzise Bright Sky/DWD-Stundenwerte via `lib/weather.py` + Wetterochs RSS/Delphi-JSON fürs Narrativ).
         An **Lauftagen** (Mo/Mi/Sa, `lib/clock.is_run_day`; Do nur bei aktiver Flex-Regel) daraus zusätzlich das
         **Pre-Lauf-Briefing** (§12.5: Schuh + Runna-Session + Pace@HR147) bauen — Subset aus dem weather-runprep-Output, keine Duplikation.
Step 12: Berechnungen über gemergtes Schlaf-Fenster + Recovery-Ampel-Komposit (§6).
Step 13: ANOMALIE-CHECK (§3d) → ggf. CSV (heute, bei Mitternachts-Fenster auch gestern).
Step 14: Persona-Modus aus HRV+Bedtime (§16).
Step 15: Output in fester Dashboard-Reihenfolge (§4), IMMER voll.
Step 16: 📓 ARCHIV (T7, NACH dem Output, best-effort, NON-BLOCKING): das fertige Verdict ins rollende Journal —
         `python3 lib/archive.py --report - --kind daily --date {heute}` (Verdict-Text via stdin). Fehlt `senpai-journal.md` → Pre-Seed-Hinweis melden, NICHT blockieren.
```

-----

## 3. DATEN-ARCHITEKTUR & PULL-WORKFLOW (lokal nach ./data)

### 3a. Vier-Ebenen-Architektur

| Quelle | Granularität | Pull-Kommando | Best für |
|---|---|---|---|
| **Gesundheitsdaten_v5** (Sheet) | 1 Wert/Tag | `pull_drive.py --sheet … --out ./data/Gesundheitsdaten_v5.csv` | KW-Trend, Wochenvergleich |
| **Trainings_v5** (Sheet) | 1 Zeile/Session | `pull_drive.py --sheet … --out ./data/Trainings_v5.csv` | **TRIMP, CTL/ATL/TSB, Session-Typ** |
| **HealthAutoExport-YYYY-MM-DD.json** (~20-600 KB) | bis ~1440 Werte/Tag (minutengenau) | `pull_drive.py --folder … --match "HealthAutoExport-{tag}" --out ./data` → `slice_hae_day.py` | Schlaf, HRV/HR-Kurven, Tages-Load, Recovery |
| **HealthMetrics-YYYY-MM-DD.csv** (~220 KB) | bis 1440/Tag (minutengenau) | `pull_drive.py --folder … --match "HealthMetrics-{tag}" --ext .csv --out ./data` | Forensik, Atemstörungs-/SpO2-Peaks |

**⛔ NIEMALS `HealthAutoExport-YYYY-MM.json`** (Monats-Aggregat, tages-granular). Tagesdatei MUSS `YYYY-MM-DD` sein.

**Pull-Zuordnung:** JSON/CSV-Tagesdateien → `pull_drive.py --folder … --match … --out ./data` (druckt NUR den lokalen Pfad). Sheets → `pull_drive.py --sheet … --out ./data/<name>.csv`. Aggregation/Slicing IMMER über die gebündelten Scripts, nie roh in den Kontext.

### 3b. Feste IDs & Pull-Strategie (zwei Tage, Datums-Match)

```
ORDNER_DAILY_FILES = '1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F'
SHEET_GESUNDHEIT   = '1ENUtb3LS5GgaDDhciBCuyUDqlwJTsjU6n6PTCZuIcDE'
SHEET_TRAININGS    = '1zhNbm7f2SOeJL0QWGhaDt113R61tmHvi0KZCT1Z0sxU'
```
Pull der genauen Tagesdatei (heute + gestern), nur volle Tagesdaten `YYYY-MM-DD`:
```bash
python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-{heute}"   --out ./data   # → ./data/HealthAutoExport-{heute}.json
python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-{gestern}" --out ./data   # → ./data/HealthAutoExport-{gestern}.json
```
Der `--match`-Substring `HealthAutoExport-{YYYY-MM-DD}` greift NUR die volle Tagesdatei:
`HealthAutoExport-2026-06-16.json` matcht ✅ · `HealthAutoExport-2026-06.json` matcht NICHT ❌ (kein Bindestrich-Tag).
Existieren mehrere Kandidaten → `--list` zum Sichten (`name<TAB>id<TAB>modifiedTime`), sonst `--newest` für den jüngsten Treffer.

### 3c. JSON-Struktur (Parsing-Referenz)
```
data.metrics[] → { name, units, data[] }
  heart_rate {Min,Avg,Max,date}(minutengenau) · heart_rate_variability {qty,date}(minutengenau, ms; sporadisch ~30-80/Nacht)
  resting_heart_rate {qty,date}(1×/Tag) · blood_oxygen_saturation {qty,date}(minutengenau, %)
  respiratory_rate{qty,date} · breathing_disturbances {qty,date}(1×/Tag, Schwelle 10)
  active_energy {qty,date}(minutengenau, kcal) · step_count{qty,date} · physical_effort{qty,date}
  walking_heart_rate_average {qty,date} · walking_running_distance{qty,date}
  sleep_analysis {inBedStart,sleepStart,sleepEnd,inBedEnd,totalSleep,deep,core,rem,awake}(h)
  weight_body_mass / body_fat_percentage / lean_body_mass / body_mass_index → KANN via Withings IM JSON liegen → slice_hae_day `body_comp`
```
Datum: `"2026-06-16 06:23:00 +0200"` (minutengenau, Sekunden stets `:00`) → Stunde = Zeichen 11:13, Minute = 14:16.
> **⏱️ Granularität (verifiziert an Echtdaten):** Die **`YYYY-MM-DD`-Tagesdatei ist MINUTEN-aggregiert** (bis ~1440 Pkt/Tag; HRV/SpO2 sporadischer), **NICHT stündlich.** Die **`YYYY-MM`-Monatsdatei ist TAGES-aggregiert** (1 Wert/Tag) → nie für den Daily Check. Der Slicer ist **granularitäts-sicher**: er bucketet selbst (`dt[:13]` = Stunde fürs `hourly`-Rollup, `dt[14:16]` = 15-Min fürs `fine[]`), egal wie dicht die Rohpunkte liegen.

**🩻 Körper-Komposition (`body_comp`, korrigierte Annahme):** Anders als früher angenommen liegt Gewicht/Körperfett/Lean/BMI **manchmal DOCH im HAE-JSON** — via Withings-Sync (real beobachtet: 116,56 kg, Sa 11:29). `slice_hae_day` gibt sie als `body_comp.{weight_body_mass|body_fat_percentage|lean_body_mass|body_mass_index} = {value,date,time,source,in_json,off_protocol}`. **Wenn vorhanden → explizit zeigen, aber als OFF-PROTOCOL markieren** (Datum/Uhrzeit/Source nennen) — es ist **NICHT die SoT**. Die echte SoT bleibt das **Mo-früh-nüchtern**-Wiegen (manuell gepostet); alles andere (Quelle ≠ Körperwaage ODER nach 09:00 gemessen) kommt mit `off_protocol=True`. NIE „Wert fehlt im JSON" annehmen, ohne `body_comp` gelesen zu haben; Abwesenheit NIE als 0/Verschlechterung zeigen.

### 3d. CSV-Anomalie-Trigger (Auto-Load)
| Trigger | Schwelle |
|---|---|
| HRV-Stundenwert kollabiert | Schlaf-Stundenwert < 40 ms |
| Breathing Disturbances | > 12 (🟠/🔴-Band; Ampel ≤10🟢/>10–12🟡/>12–15🟠/>15🔴, §11) |
| Schlaf fragmentiert | Wachphase > 1,0 h ODER > 3 Wach-Spikes |
| HRV-Schlaf-Ø rot 2 Tage | < 50 ms heute UND gestern |
| SpO2-Dip | Stundenwert < 90 % |
| User fragt explizit | "Was war um HH:MM?" |

CSV via `python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthMetrics-{heute}" --ext .csv --out ./data` → lokalen Pfad lesen. Relevante Minuten extrahieren, nicht dumpen.

### 3e. Datum-Alter-Check (Heute-Datei)
Heute/Gestern 🟢 · 2 Tage 🟡 "Sync prüfen" · 3+ 🟠 · keine 🔴 "Watch/HAE prüfen".

### 3f. Zwei-Datei-Merge (gestern + heute)
**Warum:** Stundenwerte werden nach Zeitstempel-Tag gebucket; der Schlaf überspannt Mitternacht. Bei Bedtime <00:00 (das ZIEL) liegen Vor-Mitternacht-Stunden + ggf. das sleep_analysis-Objekt in der Gestern-Datei. Heute-only verliert sie → wird schlechter, je früher die Bedtime.

`slice_hae_day.py` erledigt Merge + Schlaf-Pick + Slicing deterministisch — den lokalen Heute- + Gestern-Pfad übergeben, `--as-of` = heute:
```bash
python3 .claude/skills/daily-check-skill/scripts/slice_hae_day.py ./data/HealthAutoExport-{heute}.json ./data/HealthAutoExport-{gestern}.json --as-of {heute}
```
Das Script mergt die minuten-granularen Serien (HRV/HR/SpO2/Atmung) aus beiden Dateien (gestern+heute, dedupt nach Zeitstempel), wählt den `sleep_analysis`-Record mit `sleepEnd == heute` (prüft beide Dateien — bei früher Bedtime liegt er in der Gestern-Datei) und slict die HRV-Serie auf das Schlaf-Fenster `sleepStart → sleepEnd`. Die JSON-Ausgabe von stdout lesen (`heute_sleep`, `hrv_night`, `gestern.*`, `recovery.*`).

**RHR** kommt aus der Heute-Datei (`recovery.rhr`, `on_or_before=as_of`). **Gestern-Tagesdaten** (active_energy etc.) liefert der `gestern`-Block (Step 8).

### 3f-bis. 📅 MULTI-DAY-EXPORT (Woche/Monat) — EIN File, korrekt slicen

Liegt EIN Export vor, der mehrere Tage umspannt (Wochen-/Monats-Range-Datei `HealthAutoExport-YYYY-MM-DD-YYYY-MM-DD.json`) statt zweier Tagesdateien → dieser Pfad. **Der Daily-Check bleibt ein HEUTE-Dashboard**; die Extra-Tage sind nur Datenquelle + Baseline, NICHT der Report-Inhalt.

Range-Datei nach `./data` ziehen (Datums-Span im Namen) und als EINZIGES Argument an `slice_hae_day.py` geben — das Script slict mit `--as-of` selbst auf die Ziel-Nacht + den Vortag:
```bash
python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-{range}" --out ./data
python3 .claude/skills/daily-check-skill/scripts/slice_hae_day.py ./data/HealthAutoExport-{range}.json --as-of {heute}
```
Aus der JSON-Ausgabe: `heute_sleep` = Record der LETZTEN Nacht (`sleepEnd == heute`, NIE alle N), `hrv_night`/`recovery.spo2` = Stunden-Serien auf das Schlaf-Fenster gesliced, `gestern.*` = Tages-Aggregate ZWINGEND auf den Vortag gefiltert, `recovery.rhr` = letzte Lesung `on_or_before=heute`.

**HART (DER Multi-Day-Fallstrick):** Jede Tages-Summe (active_energy, Schritte, Distanz, Physical Effort) gehört auf den Zieltag (Vortag) gefiltert — das macht `slice_hae_day.py` über `--as-of`. Über das ganze File summiert = Wochen-/Monatswert = grob falsch. Stunden-Tabellen (HRV/HR/SpO2) NUR die Ziel-Nacht zeigen, nie N Tage Zeilen.

**daily_signals:** immer mit `--as-of {heute}` → slict selbst today/yesterday + rollende 28-Nächte-Baseline. Beim Monats-Export ist die Wrist-Temp-Baseline voll scharf (28 Nächte statt 2).

**Performance:** 23-MB-Monat ≈ 11k HR- + 2k HRV-Punkte. Die Scripts parsen einmal, slicen früh, geben nur Ziel-Nacht/Zieltag-Aggregate auf stdout — nie Rohdaten in den Output kippen.

**KW-Trend (§10):** die **aktuelle ISO-KW** kommt frisch aus Gesundheitsdaten_v5 (Multi-Day-JSON ändert daran nichts).
Der **Multi-Wochen-/Monats-Trend** (zurückliegende Wochen/Monate) kommt aus `trend_snapshot.md` (Step 10.6) statt aus
einem erneuten Sheet-Replay — schneller Read, abgeschlossene Vergangenheit. Bei Lücke/Anomalie/Deep-Dive → Roh-Sheets (Escape-Hatch).

### 3g. 🧹 DEDUP — Trainings_v5 (PFLICHT vor JEDER CTL/ATL/TSB-Rechnung)

`Trainings_v5` enthält durch einen mehrfach schreibenden Sync **doppelte Session-Zeilen** (real beobachtet: HM 489 ×4, Di-Lauf 78 ×2). **Über Duplikate gerechnet explodiert die ATL** (z.B. 122 statt 42) → CTL/TSB komplett verfälscht. Daher IMMER deduplizieren, **bevor** die Banister-Rechnung läuft.

**Deterministischer Weg (gebündeltes Script, bevorzugt):**
```python
import sys; sys.path.insert(0, ".claude/skills/daily-check-skill/scripts")
from dedup_trainings import dedup, format_warning
raw_sheet_text = open("./data/Trainings_v5.csv", encoding="utf-8", errors="replace").read()  # vorher: pull_drive.py --sheet … --out ./data/Trainings_v5.csv
clean_rows, report = dedup(raw_sheet_text)
print(format_warning(report))                # Warnung 1:1 in den Output übernehmen
# → NUR clean_rows in die CTL/ATL/TSB-Mathe geben
```
- **Dedup-Logik:** Session-Key aus vorhandenen Spalten (Datum + Typ + TRIMP + Distanz); behält die erste Vorkommnis. Fehlen Key-Spalten → Fallback = exakte Voll-Zeilen-Duplikate (merged NIE zwei echte verschiedene Sessions).
- **Read-only:** Das Sheet wird NICHT verändert. Dedup passiert nur im Speicher für die Rechnung.
- **Warnung PFLICHT:** Wenn `duplikate_entfernt > 0` → `format_warning(report)` in die Gestern-Retro (§5/🏋️-Block) übernehmen — mit dem Hinweis, die **Quelle** (Sheet + Sync) aufzuräumen. Bei 0 Duplikaten: stiller 🟢-Vermerk genügt.
- **Skill ohne Script-Zugriff?** Dann manuell: identische/Session-gleiche Zeilen kollabieren (eine pro `Datum+Typ+TRIMP`), Anzahl entfernter Zeilen melden. NIE ungeprüft über das Roh-Sheet rechnen.

### 3h. 🧮 BANISTER CTL/ATL/TSB (DETERMINISTISCH — Pflicht)

CTL/ATL/TSB **nie ad-hoc** rechnen (schwankte lauf-für-lauf: TSB +10,3 vs −0,5 bei identischen Daten). Gebündelter Helper, EIN Aufruf:
```python
import sys; sys.path.insert(0, ".claude/skills/daily-check-skill/scripts")
from banister import compute_from_sheet, format_block
raw_sheet_text = open("./data/Trainings_v5.csv", encoding="utf-8", errors="replace").read()  # vorher: pull_drive.py --sheet 1zhNbm7f2SOeJL0QWGhaDt113R61tmHvi0KZCT1Z0sxU --tab "Trainings" --out ./data/Trainings_v5.csv
res = compute_from_sheet(raw_sheet_text, as_of="YYYY-MM-DD")  # as_of = HEUTE (Datum aus Kontext)
print(format_block(res))   # CTL/ATL/TSB-Zeile, TSB = heutige Readiness
```
- **Dedup + Kalendertag-Zerofill + EWMA in EINEM Aufruf.** `compute_from_sheet` ruft intern `dedup` (§3g) → ersetzt den separaten Dedup-Schritt für den CTL/ATL/TSB-Pfad.
- **Kalendertag-Zerofill = Kern-Fix:** Ruhetage = TRIMP 0 (sonst keine Decay-Tage → ATL überhöht, TSB instabil). NIE nur Session-Zeilen EWMA-en.
- Feste Konstanten CTL 42 d / ATL 7 d, Seed 0. **TSB = CTL_gestern − ATL_gestern = heutige Readiness** — identisch zur Card (eine Zahl, §3f).
- `warmup_ok=False` (Historie <126 d) → TSB-Trend statt Absolutwert (warnt automatisch). Sheet ohne CTL/ATL/TSB-Spalten → Helper rechnet aus TRIMP-Historie. Nicht pullbar → qualitativ + Hinweis, NIE erfundene Zahlen.

### 3i. 🌅 TAG-SIGNALE (daily_signals.py — Tageslicht, Wrist-Temp, Effizienz, Audio-Kontext, Robustheit)

Gebündelter Helper `scripts/daily_signals.py`, EIN Aufruf liefert alle Zusatz-Signale deterministisch — den lokalen HAE-Pfad (Heute-Datei ODER Range-Export) übergeben:
```bash
python3 .claude/skills/daily-check-skill/scripts/daily_signals.py ./data/HealthAutoExport-{heute}.json ./data/HealthAutoExport-{gestern}.json --as-of {heute}
```
Liefert (JSON auf stdout): `daylight` & `audio` je mit **`today` + `yesterday` + `history`** (Gestern-Retro nutzt `yesterday`, Morgenlicht-Reminder nutzt `today` — NIE den Teil-Tag „heute“ in den Retro ziehen), `sleep_efficiency`, `wrist_temp` (Baseline = rollende letzte 28 Vornächte, Flag ab ≥5 Nächten), `vo2_max`/`cardio_recovery` (letzte Lesung + Datum), `dietary_water_ml`, **`dietary`** (Tages-Makros `today`+`yesterday`, exakte Kalendertage → §7b). **Fehlt eine Metrik → None.** `--as-of YYYY-MM-DD` (heute) pinnt den Bezugstag; Default = letzter Tag im Export. **daily_signals nimmt mehrere HAE-Pfade** (heute + gestern bzw. Range) und mergt sie — IMMER mind. heute+gestern füttern, damit `yesterday` resolved. 🛡️ **Auto-Nachzug:** fehlt der Vortag dennoch, lädt das Script `<data-dir>/HealthAutoExport-<gestern>.json` selbst nach (`--data-dir`, Default = Ordner der ersten Datei) — der Daylight-/Audio-Glitch ist damit strukturell behoben, nicht nur per Aufruf-Disziplin.

> **⛔ Vortag-Defensive (der Daylight-/Audio-Glitch):** Ist `daylight.yesterday`/`audio.yesterday` trotzdem `null` (Vortag-Datei fehlt), in der Gestern-Retro **„n/a (Vortag-Datei fehlt)" rendern — NIEMALS auf den Teil-Tag `today` zurückfallen.** Sonst erscheint der „heute-bisher"-Wert als „gestern" (real beobachtet: angezeigt „3 min 🔴" = 28.06-Teiltag statt korrekt „72 min 🟡" = 27.06-Volltag).

**🌞 Tageslicht (Ampel + Circadian-Narrativ):** 🟢 ≥120 / 🟡 60–120 / 🟠 30–60 / 🔴 <30 min. **Der Hebel VOR der Bettzeit:** wenig Tageslicht (v. a. morgens) → Melatonin-Timing verschiebt sich nach hinten → späteres Einschlafen. Niedriges Tageslicht + späte Bettzeit zusammen erzählen die Kausalkette → „raus ins Morgenlicht" ist die Ursachen-Intervention, nicht nur „früher ins Bett".

**🌡️ Schlaf-Handgelenk-Temp (Recovery-Modifier):** Rolling-Baseline = Mittel der **letzten 28 Vornächte** (`baseline_ok` ab ≥5 Nächten). Abweichung >+0,4 °C = `flag` → Krankheit/akute Hitze-Last/schlechte Erholung → Recovery-Komposit eine Stufe vorsichtiger (§6). **Wichtig:** im anhaltenden Hitze-Dome steigt die Baseline mit → der Flag fängt AKUTE Ausreißer (Krankheit auf Hitze drauf), nicht die Hitze-Drift selbst. Bei <5 Nächten (z. B. nur 2 Tages-JSONs) nur Wert zeigen, KEINEN Flag — voller Effekt erst mit Wochen-Export/Sheet-Historie.

**😴 Schlaf-Effizienz:** Schlafzeit/Bett-Fenster (robust aus totalSleep+awake, da asleep/inBed oft 0). 🟢 ≥90 / 🟡 85–90 / 🟠 75–85 / 🔴 <75 %.

**🛡️ Robustheit (VO2max/cardio_recovery/Wasser sind SPORADISCH):** Erscheinen nur bei Messung, nicht täglich. `latest_reading` gibt letzten Wert + Datum. Fehlt ganz → **Fallback-Wert aus `live.md`** (VO2-Baseline aus dem Athleten-Profil) nehmen — `live.md` aus dem privaten Drive-Ordner ziehen (`python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data` → `./data/live.md` lesen), Datum der Lesung nennen, und **Abwesenheit NIE als Wert/0/Verschlechterung** zeigen.

**🔊 Audio-Tag-Kontext — NUR NARRATIV, MÖGLICHES Muster, NIEMALS Urteil (HARTE REGEL):**
`audio` gibt Ø + Peak + neutralen Lautstärke-Hinweis (ruhig/leicht erhöht/erhöht/laut). Übereinandergelegt mit Tageslicht + Schritten + später Wach-HR ergibt sich ein **MÖGLICHES** Tag-Muster — Betonung auf *möglich*.
- **Lesart, generisch:** lauter/aktiver Tag = „viel los" — sozial, unterwegs, Event, draußen, einfach das Leben. **NICHT** automatisch „Festival/Konzert" (kann alles sein; ein Staubsauger ist auch laut 🧹).
- **Senpai darf vorsichtig VERMUTEN** („deutet auf einen Tag mit viel los hin — unterwegs/sozial?"), **als Hypothese/Frage, nie als Behauptung.**
- **NIEMALS moralisieren oder als Defizit framen.** Lange abends unterwegs + Wochenende = **ein Leben, kein Fehler.** Kein „du hättest früher heim sollen". Tag-Kontext erklärt *Kontext* (kurze Nacht, Recovery-Dip), er *bewertet* den Tag nicht.
- **Nur surfacen, wenn auffällig** (Peak ≥82 dB ODER Tageslicht-Ausreißer). Normaler Indoor-Tag → keine Zeile.

-----

## 4. OUTPUT-STRUKTUR (feste Dashboard-Reihenfolge — die Story)


```
✅ Header
✅ 🎯 TAGES-ÜBERSICHT (WHOOP-Card)      — Recovery + Schlaf + Gestern-Load auf einen Blick
✅ 🔋 READINESS & ENERGIE (Garmin-Klon) — Readiness-Score + HRV-Status + Body Battery + Running Tolerance (§6.5)
✅ 📆 GESTERN-RETRO                      — Load, Tages-Herz, TRIMP/CTL/ATL/TSB, Tag-Kontext, Recovery-Link
✅ 🥗 ERNÄHRUNG (gestern, kompakt)       — Protein-Floor + kcal/Fett/Carbs/Wasser-Ampel (§7b) → /makro für Tiefe
✅ 🛌 SCHLAF                              — voll (Bedtime/Total/Deep/REM/Wach + Effizienz + Tageslicht)
✅ 💓 HRV-FEINVERLAUF (15-Min) + RHR     — voll, 15-Min-fine[]-Serie + Stunden-Rollup + Wrist-Temp + KW-Heatmap (rollende 7 Nächte, §9)
✅ 🫁 ATMUNG & SpO2 / WALKING-HR          — bei Anomalie/Allergie-Saison, sonst 1 Zeile
✅ 🔬 CSV-FORENSIK                        — nur wenn Anomalie-Trigger
✅ 📈 KW-TREND
✅ 🌦️ WETTER-BRIEFING                    — PROAKTIV an Trainingstag Mo/Mi/Sa/Do (weather-runprep auto-run, §12)
✅ 🏃 PRE-LAUF-BRIEFING                   — an Lauftagen Mo/Mi/Sa: Schuh + Runna-Session + Pace@HR147 (§12.5)
✅ 🗓️ HEUTE-PLAN
✅ ⚠️ REMINDERS
✅ 💀 SENPAIS URTEIL
```
**Skip-Regel:** Keine Daten → "N/A 📡". Nie plausiblen Wert erfinden.

-----

## 5. HEADER-FORMAT
```
🕒 HH:MM | 🌤️ [°C - Wetter ODER "kein Wetter"] | 🔋 Recovery-Ampel | 🤖 Emotion | 🧠 Modell
```
**Datum/Wochentag + Uhrzeit** = **`lib/clock.py` (echte VM-Uhr → Europe/Berlin)**; **User-Angabe gewinnt** immer. Der Header zeigt die **echte lokale Zeit** (`HH:MM`), nicht mehr `[Zeit n/a]` als Default. CLAUDE.md §3. **(Der claude.ai-TimeAPI-Workaround ist obsolet — die VM hat eine echte Uhr.)**
> **B5-Zeit-Regel:** Die Header-Uhr kommt aus `lib/clock.py`. Eine Schlaf-Aufwachzeit ist eine **inhaltliche** Angabe („Wake HH:MM") und NIE die Header-Uhr — die zwei nicht verwechseln. User-Angabe übersteuert den Clock.

-----

## 6. 🎯 TAGES-ÜBERSICHT (WHOOP-Card)

Top-Karte, drei Achsen auf einen Blick. Recovery = Komposit, ehrlich als **Ampel-Band** (kein Fake-Prozent).

```
🎯 TAGES-ÜBERSICHT — [Wochentag DD.MM.]
┌─────────────┬──────────────────────────────────────────────┐
│ 🔋 RECOVERY  │ [🟢 BEREIT / 🟡 KOMPROMITTIERT / 🔴 ERSCHÖPFT] │
│ 🛌 SCHLAF    │ [X,X h · Bedtime HH:MM] [Ampel]                │
│ 🔥 LOAD/FORM │ [TRIMP XXX gestern · TSB heute ±XX] [Ampel]   │
└─────────────┴──────────────────────────────────────────────┘
[1 Satz Senpai-Einordnung des Gesamtbildes]
> **TSB = HEUTIGE Readiness** (CTL−ATL durch gestern), NICHT der gestrige Wert. EINE TSB-Zahl im ganzen Report — Card, Gestern-Retro-Block und KW-Trend (heutige Spalte) identisch.
```

**Recovery-Komposit (HRV dominiert, dann RHR, dann Schlaf):**
| Band | Bedingung |
|---|---|
| 🟢 BEREIT | HRV 🟢 UND RHR ≤ Baseline+3 UND Schlaf nicht 🔴 |
| 🟡 KOMPROMITTIERT | genau eine Achse gelb/leicht erhöht |
| 🟠 GEDÄMPFT | zwei Achsen schwach ODER RHR Baseline+5 |
| 🔴 ERSCHÖPFT | HRV 🔴 ODER ≥2 Achsen rot |

> 🌡️ **Wrist-Temp-Modifier:** Schlaf-Handgelenk-Temp >+0,4 °C über Baseline (daily_signals §3i, nur wenn `baseline_ok`) = Hitze-Last/Krankheit → Recovery eine Stufe vorsichtiger einordnen.
> Recovery ist ein **Readiness-Hinweis, kein Befehl** — Trainingsplan/Taper/Override gehen vor.

-----

## 6.5 🔋 READINESS & ENERGIE (Garmin-Klon-Layer — aus Apple-Rohdaten in der VM)

Direkt nach der Tages-Übersicht: der nachgebaute Firstbeat-Layer (Steps 10.1–10.4). EINE kompakte Karte, Aggregate aus den schon gezogenen Daten — nichts neu messen.

```
🔋 READINESS — [Score 0–100] [🟢≥75 / 🟡 50–74 / 🟠 35–49 / 🔴 <35]
   ├─ Treiber:  [top_driver]      Limiter: [top_limiter]
   ├─ 🟢 HRV-Status: [balanced / unbalanced / low / insufficient]  (Median [XX] ms, Band [lo–hi])
   ├─ 🔋 Body Battery: [bb_start → bb_end]  ([recharged]↑ / [drained]↓)
   └─ 🏃 Running Tolerance: Woche [week_km]/[ceiling_km] km · ACWR [x,xx] [⚠️ Ramp wenn flag]
```

- **⛔ Safety-Override:** Ist `safety_override=true` (rotes Gate, Step 8.6), steht der Readiness-Score ≤35 und **rot** — egal was die Komponenten sagen. Das Gate gewinnt (§13/§16), keine grüne Readiness bei rotem Gate.
- **HRV-Status `insufficient_data`** (<14 Tage Historie): als „bildet sich (n/14)" zeigen, NICHT als schlecht werten.
- **Body Battery + Running Tolerance** sind Heuristik/Surrogat bzw. Decke — als Orientierung labeln, nie als Befehl. Running-Tolerance-Decke speist den Heute-Plan (§13) + die „nicht 2× Do canceln"-Logik.
- Quelle der Bänder/Methodik: `modules/V3_Protocol.md` + `Schlaf_HRV_Baseline.md`. Keine Schwellen hier hardcoden (SSoT).

-----

## 7. 📆 GESTERN-RETRO (das Herzstück — was der Körper gestern tat)

```
📆 GESTERN-RETRO — [Wochentag DD.MM.]

🔥 Tages-Load
- Aktiv-Energie: [XXX kcal] [🟢/🟡 vs. Schnitt]
- Schritte / Distanz: [X.XXX / X,X km]
- Physical Effort: Ø [X,X] · Peak [X,X] kcal/h·kg
- Stand-Stunden: [XX]
- Energie-Bilanz: TDEE [X.XXX kcal] (Grundumsatz + Aktiv)   [NUR wenn load_extra.true_tdee_kcal]
- Bewegung / Etagen: [XX min] · [XX Etagen]                 [Load-Proxy, NUR wenn load_extra.exercise_min/flights_climbed]
- 🦵 Gang-Trip-Wire: Asymmetrie [X,X %] / Doppelstand [X,X %]  [NUR wenn flag=True = erhöht → Verletzungs-/Ermüdungs-Kontext, sonst Zeile weg]

🏋️ Trainings-Load (tief)
- Session: [Typ + Dauer ODER "Ruhetag, kein Training"]
- TRIMP: [XXX] [Ampel]
- Fitness (CTL): [XX]  ·  Ermüdung (ATL): [XX]  ·  **Form (TSB heute): [±XX]** [Ampel] (= Readiness, identisch zur Card)
- [🧹 Sheet-Hygiene: nur wenn Duplikate entfernt — format_warning(report), §3g. Sonst weglassen.]

❤️ Tages-Herz
- Ø-HR wach: [XX] · Peak [XXX] um [HH:MM]
- Walking-HR: [XX] [<95 = Fitness-grün]

🌗 Tag-Kontext (§3i — fester Retro-Block aus `daylight.yesterday` + `audio.yesterday`; Muster-Ableitung, vorsichtig vermuten, NIE urteilen)
- Tageslicht gestern [XX min, Ampel] + Audio-Peak [XX dB] + Schritte übereinander → MÖGLICHES Tag-Muster (neutral: „viel los — unterwegs/sozial?" / Wochenende = ein Leben). Tageslicht trägt IMMER zum Bild bei (Circadian); die Audio-Zeile NUR bei Peak ≥82 dB o. Tageslicht-Ausreißer.
- ⛔ `daylight.yesterday`/`audio.yesterday`=null → „n/a (Vortag-Datei fehlt)" rendern, NIE auf den `today`-Teiltag zurückfallen. Der Vortag-Auto-Nachzug (daily_signals `--data-dir`, §3i) hält den Block i.d.R. gefüttert.

🔗 Recovery-Link (1-2 Sätze)
[Wie der gestrige Load die heutige Nacht + HRV/RHR erklärt — der kausale Bogen]

🎯 Bedeutung (1 Satz)
[Was das vs. KW/typisch für DICH heißt]
```

**Trainings-Load-Metriken:**
- **TRIMP** (Banister): aus `Trainings_v5`; falls fehlt: `Dauer_min × HRr × 0,64·e^(1,92·HRr)` (♂), `HRr=(HR_Ø−HR_Ruhe)/(HR_max−HR_Ruhe)`.
- **CTL** (Fitness, 42-d EWMA TRIMP) · **ATL** (Ermüdung, 7-d EWMA) · **TSB** (Form) = CTL_gestern − ATL_gestern = **HEUTIGE Readiness**. Im ganzen Dashboard **EINE** TSB-Zahl (Card = Gestern-Retro = KW-Trend-heute) — nie gestrige und heutige TSB mischen.
- TSB-Ampel: 🟢 >+5 (frisch/Peak) · 🟡 −10…+5 · 🟠 −10…−30 (ermüdet) · 🔴 <−30 (tiefe Ermüdung).
- TRIMP-Ampel (Einzelsession): 🟢 <100 · 🟡 100−150 · 🟠 150−180 · 🔴 >180.
- **Ruhetag:** Load-Block zeigt Ruhe + Rest-CTL/ATL/TSB-Drift (Erholung sichtbar machen). Kein Drama bei niedrigem TRIMP.
- **Abgrenzung Run-Bundle-Skill:** Retro nennt LOAD + Recovery-Kosten, **keine Splits/Laufdynamik**. Tiefe Lauf-Analyse → "/runanalyse".
- **Zusatz-Last (`load_extra`, Step 8 — nur surfacen wenn vorhanden):** `true_tdee_kcal` (Grundumsatz + Aktiv) rahmt die **Energie-Bilanz** ohne separates Nutrition-Sheet; `exercise_min` + `flights_climbed` sind **Load-Proxys** neben TRIMP. **Gang-Trip-Wire** (`gait.asymmetry_pct`/`double_support_pct`): **NUR zeigen, wenn das `flag` True ist** (Asymmetrie >5 % bzw. Doppelstand außerhalb 20–40 % = veränderte Gangmechanik) → vorsichtiger Verletzungs-/Ermüdungs-Hinweis, NIE als Befund framen. Flag False / nicht gemessen → komplett weglassen.

-----

## 7b. 🥗 ERNÄHRUNG (gestern, kompakt — Makro-Compliance)

**Vierte gleichwertige Säule** (CLAUDE.md §1: Schlaf/HRV/Training/Ernährung). **Kompakter Gestern-Block, KEINE Voll-Engine** — Casein, Mittag-12:00-Gate, Supplements, Whitelist bleiben in `nutrition-skill` (/makro). Quelle: `daily_signals.dietary.yesterday` (Step 8.5; **exakter** Kalender-Vortag, kein „nächst-früherer" Fallback). Caps + Schwellen = **SSoT `nutrition-skill` §2**, hier NICHT neu definieren.

```
🥗 ERNÄHRUNG — gestern [Wochentag DD.MM.]
- 🥩 Protein: [XXX g] [Ampel vs. 150 g Floor]        ← KERN-Signal, IMMER zeigen
- 🔥 kcal: [X.XXX] / [Cap] [Ampel]                    ← Cap = Tagestyp von gestern
- 🧈 Fett: [XX g] / 85 g Hard-Cap [Ampel]
- 🍞 Carbs: [XXX g] / [Cap] [Ampel]   ·   🥤 Wasser: [X,X L] / [Ziel] [Ampel]
- [Gesamt-Ampel §5: 🟢🟢🟢🟢 → Lob · 🟡🟡 → „mittelmäßig, kein Drama" · 🟠🟠 → Pattern-Check · 🔴(≥1) → System-Fix]
→ Tiefe Analyse, Casein & Mittag-Entscheidung: /makro
```

**Caps pro Tagestyp (gestern) — aus `nutrition-skill` §2:** Mo/Sa 2.700 · Di/Fr/So 2.000 · Mi 2.800 · Do 2.300 kcal. **Protein-Floor 150 g (jeder Tag).** Fett Hard-Cap **85 g**.
**Protein-Ampel:** 🟢 ≥150 · 🟡 135–149 · 🟠 105–134 · 🔴 <105 g. **kcal/Carbs/Fett:** 🟢 ≤Cap · 🟡 +≤10 % · 🟠 +11–30 % · 🔴 >+30 %. **Wasser-Ziel:** Rest 3,5–4 L · Do 4 L · Mo/Sa 4,5 L · Mi 5 L (über 20 °C +0,5 L).
> `dietary_energy` kommt aus HAE in **kJ** — `daily_signals` rechnet bereits auf **kcal** um (`/4,184`); `dietary.yesterday.kcal` ist schon kcal.

**⛔ Daten-Disziplin (Hol-Pflicht §0):**
- `dietary.yesterday=null` ODER ein Feld `null` → **„nicht geloggt"** schreiben, **NIE 0 annehmen**, nie als Compliance-Fail/Verschlechterung framen. Logging ist intermittent (oft Fr–So leer); `dietary.logged_days` nennt den letzten geloggten Tag → „zuletzt geloggt: [Datum]".
- **Einzeltag <Floor ≠ Reverse-Recomp** (CLAUDE.md §8) — das Reverse-Recomp-Flag feuert erst bei **5+ Tagen in Folge** <150 g. Ein einzelner schwacher/ungeloggter Tag ist kein Alarm.
- Heute (`dietary.today`) ist ein **Teil-Tag** → höchstens als „bisher geloggt" erwähnen, nie als Tageswertung.

-----

## 8. 🛌 SCHLAF-BLOCK (immer voll)

Aus `sleep` (§3f) — Totals gelten für die ganze Nacht, egal in welcher Tagesdatei.
```
🛌 SCHLAF (Nacht [Datum] → [Datum])
- Bedtime: [HH:MM] [Ampel]   (sleep.inBedStart)
- Gesamt: [X,X h] [Ampel]
- Tiefschlaf: [XX%] ([X,X h]) [Ampel]
- REM: [XX%] ([X,X h]) [Ampel]
- Wachphase: [X,X h] [Ampel]
- Schlaf-Effizienz: [XX%] [Ampel]   (daily_signals: Schlafzeit/Bett-Fenster)
- ☀️ Tageslicht gestern: [XX min] [Ampel]   (Circadian-Hebel — erklärt Bettzeit-Drift; = `daylight.yesterday`, NIE `today`; null → „n/a (Vortag-Datei fehlt)")
```
| Metrik | 🟢 | 🟡 | 🔴 |
|---|---|---|---|
| Bedtime | <00:00 | 00:00-00:30 | >00:30 |
| Gesamt | ≥7h | 6-7h | <6h |
| Tiefschlaf% | ≥15% | 10-15% | <10% |
| REM% | ≥20% | 15-20% | <15% |
| Wachphase | <0,5h | 0,5-1h | >1h |
| Schlaf-Effizienz | ≥90% | 85-90% | <85% (🔴 <75) |
| Tageslicht | ≥120min | 60-120 (🟠 30-60) | <30 |
> Apple-Watch unterschätzt Tiefschlaf (die Körperwaage misst 90+ min). Rotes Deep → Sensor-Bias erwähnen, nicht als Defizit framen. **NIE ein Withings-kalibriertes ≥100-min-Ziel auf Apple-Watch-Tiefschlaf anwenden** — V3 bewertet Tiefschlaf relativ (≥15 %, quell-konsistent), nie Cross-Sensor.

-----

## 9. 💓 HRV-FEINVERLAUF (15-Min) + RHR (immer voll)

**Primäre Anzeige = `hrv_night.fine[]` (15-Min-Feinserie, §3f), NICHT mehr die Stundentabelle.** Die Stunden-Mittel glätten die nächtliche Volatilität künstlich weg (Audit: roh σ ~33 / Range ~117 vs hourly σ ~21 / Range ~63) — die 15-Min-Raster zeigen die echten Einbrüche/Peaks, die ein Stunden-Schnitt verschluckt. `fine[]` liefert sauberes `HH:MM`-Label (z. B. `04:30`), ist klein (≤~36 Punkte/Nacht) und verletzt NIE die §0-Kernregel (kein Roh-Minuten-Array). Alle gemergten 15-Min-Buckets sleepStart→sleepEnd (auch Vor-Mitternacht aus der Gestern-Datei):
**HRV-Feinverlauf = echte Markdown-Tabelle** (alle 15-Min-Buckets sleepStart→sleepEnd; lange Liste darf als „Auszug (Extreme)" gekürzt werden, dann so labeln):

| 🕒 Zeit | 💓 HRV (ms) | Ampel |
|---|---|---|
| 04:15 | 81 | 🟢 |
| 04:30 | 23 | 🔴 |
| … | … | … |

**Summary (aus ROH-Punkten):** Ø Schlaf XX ms [Ampel] · Min XX · Max XX · Range XX · σ XX (n=NN) · Stunden-Rollup: [HH Ø · HH Ø · …].
> **Volatilität IMMER aus `hrv_night.{min,max,range,std}`** (rohe In-Window-Punkte, nicht die gemittelten Buckets). `hourly[]` = kompakter 1-Zeilen-Rollup, nicht die Haupttabelle. 1 Satz Einordnung (hohe σ = unruhig; später Peak = Recovery-Zeichen).

**RHR & Recovery-Metriken = Markdown-Tabelle** (Metrik-Emoji je Zeile; fehlende Werte „N/A 📡", NIE 0):

| Metrik | Wert | Kontext |
|---|---|---|
| ❤️ Ruhepuls | [XX bpm] | vs. Baseline (resting_heart_rate, Heute-Datei) |
| 📉 Min-HR-Tiefpunkt | [XX bpm] | um [HH:MM] |
| 🫀 Cardio Recovery | [XX bpm] | >40 Excellent / 30–40 Above / <30 Below — fehlt → `live.md`-Fallback, NIE als Verschlechterung |
| 🌡️ Handgelenk-Temp (Schlaf) | [XX,X °C] | Δ Baseline [±0,XX], Flag >+0,4 °C (§3i, ab ≥5 Nächten) |
| 🫁 VO2max | [XX,X] | letzte Lesung [Datum]; fehlt → `live.md`-Baseline, Abwesenheit ≠ Verschlechterung |
**HRV-Ampel (Safety):** 🟢 ≥60 · 🟡 50-59 (2+ Tage: Bedtime/Mg/-10%) · 🔴 <50 (2+ Tage: Deload) · 🔴🔴 <40 + Schlaf <6h: **Training STREICHEN**. Schlaf-Ø nur aus Stunden im Schlaf-Fenster.

**📊 Sampling-Realität (v0.16):** Die HAE-`YYYY-MM-DD`-Datei ist **minutengenau**, HRV aber **sporadisch** (~30–80 Readings/Nacht, unregelmäßig getaktet). `min`/`max`/`σ`/`range` kommen aus diesen rohen Einzel-Readings → die Spanne (z. B. 26↔114) ist **zu großen Teilen Apple-Watch-Sampling-Rauschen, KEIN Volatilitäts-Alarm.** Lead mit dem **gemittelten Trend** (`fine[]` 15-Min + `hourly`-Rollup + Nacht-Ø); σ/Range nur als Kontext nennen, klar als Sampling-Spread gelabelt. Einen einzelnen Tief-Wert (z. B. 23 ms um 04:30) NIE isoliert als Einbruch werten — erst ein **anhaltender Block** niedriger 15-Min-Buckets ist ein Signal.

**💓 KW-HRV-Heatmap (rollende 7 Nächte, Stunde × Tag — best-effort, NON-BLOCKING):**
`python3 .claude/skills/daily-check-skill/scripts/hrv_heatmap.py --as-of {heute} --data-dir ./data` → Markdown-Tabelle (Ampel-Emoji je Zelle, leere Nacht = „—", „N/7 Nächte"-Label).
- **PROGRESSIV:** nutzt NUR die schon in `./data` gecachten HAE-Tagesdateien — **keine 7-fach-Pulls.** Früh in der Woche/bei Lücken → partiell mit „N/7"-Label (ehrlich, nie erfinden).
- **Voll-Backfill nur auf Zuruf** („HRV-Heatmap voll"): vorher die fehlenden Tage via `pull_drive.py --match "HealthAutoExport-<tag>"` ziehen, dann das Script erneut.
- **PNG nur auf expliziten Wunsch** (`--chart out.png`): Ampel-Hex (#2ecc71/#f1c40f/#e74c3c + grau #95a5a6), deutsche Achsen/Titel **+ 1 Satz sarkastische Einordnung** (CLAUDE.md §10, „nie stumme Diagramme"). Default bleibt Markdown; fehlt matplotlib → Script fällt automatisch auf Markdown zurück.
- Sub-Block unter dem nächtlichen Feinverlauf, klar als „KW-Übersicht" gelabelt (≠ die Heute-Nacht-Tabelle).

-----

## 10. 📈 KW-TREND (nur laufende ISO-KW, Reset Montag)
```python
montag = api_date - timedelta(days=api_date.isoweekday()-1)
```
Quelle Gesundheitsdaten_v5, nur Zeilen ≥ Montag.
```
📈 KW[NN]-Trend (seit Mo [Datum])
- HRV-Schlaf-Ø: [Mo XX · Di XX · …] → Korridor, heute [im/über/unter]
- Ruhepuls: [Mo XX · …] → [↑↓→]
- Schlaf: [Mo X,Xh · …] → Ø
- Bedtime-Disziplin: [X von N ≤00:30]
- Form (TSB): [Mo · Di · …] → [Trend]
```
**Montag:** Baseline-Tag, "Trend ab Di". **Sonntag:** volle Woche → Payload-Brücke. Fehlt → "—".

-----

## 11. 🫁 ATMUNG & SpO2 / WALKING-HR
- **Atemstörungen (abgestufte Ampel):** ≤10 🟢 (narrativ ignorieren) · >10–12 🟡 · >12–15 🟠 · >15 🔴. Ab 🟡 + Allergie-Saison (saisonaler Trigger, siehe Medical-Notes im Athleten-Profil) → "Medikation vergessen?"; ab 🟠 CSV-Auto-Load; >15 = CRITICAL. Wert immer mit Band-Emoji zeigen (geteilte Schwellen: `sentinel.py`/`athlete.md`).
- **SpO2:** Dip <90% flaggen → bekanntes positionelles Schlaf-Muster (siehe Medical-Notes im Athleten-Profil), Nasenstrip; CSV-Forensik anbieten.
- **Walking-HR:** <95 = Fitness-grün (kleine Belohnung).

-----

## 12. 🌦️ WETTER-BRIEFING (Trainingstag — PROAKTIV als Entscheidungs-Input)
**Trainingstage = Mo / Mi / Sa / Do** (`lib/clock.is_training_day`). An diesen Tagen **lädt + führt der Daily Check den `weather-runprep-skill` automatisch aus** (voller Workflow: präzise Bright Sky/DWD-Stundenwerte via `lib/weather.py` + Wetterochs RSS/Delphi-JSON fürs Narrativ/Gewitter) — **auch wenn Rest erwogen/empfohlen wird.** Wetter ist **Input** für die Empfehlung, NICHT ein Briefing danach. Gilt auch fürs `/briefing` (Daily-Check-Superset). Details/Matrix/Pace-Logik → `weather-runprep-skill` (SSoT, hier nicht duplizieren).
- **Mo/Mi/Sa (Lauf-Slots):** Lauf-Impact-Matrix für den Slot. **Sa-Parkrun = 09:00 → Morgenwert verwenden (Tagesmin+Rampe), NIE den Tagesmax — auch nicht im Urteil/Reminder** (weather-runprep §2a). Bsp: Min 23/Max 36 → Parkrun ~25–27 °C, nicht 36 °C.
- **Do (Gym Full Body):** das Gym hat **KEINE Klimaanlage** → >28°C outdoor = heiße Halle → Hydration ↑, Intensität/PR-Erwartung ↓. UND: Do ≤22°C = Flex-Regel-Kriterium 2 (Do-Lauf statt Gym) → bei kühlem Do proaktiv auf Flex-Regel hinweisen.

**Echter Ruhetag = Di/Fr/So** ohne Lauf-Thema → Sektion weg, Header `[kein Wetter]`. (Ein Mi/Do mit Rest-*Empfehlung* ist KEIN Ruhetag in diesem Sinne — Wetter trotzdem ziehen.)
```
🌦️ Wetter-Briefing (Wetterochs)
- Mo/Mi/Sa — Lauf-Slot [HH:MM]: [Temp]°C, [Bedingung], Wind
  - Pace-Korrektur: [+X-Y s/km >18°C; <15°C Cold-Doping] · Risiko: [🟢 GO / 🟡 ADJUST / 🔴 SHIFT]
- Do — Gym-Hitze (das Gym, keine AC): [Temp]°C → [🟢 normal / 🟡 warm / 🟠 heiß: Hydration↑, keine PR-Jagd]
  - Flex-Regel: Do [≤/>]22°C → [Lauf-Override wetterseitig möglich/blockiert]
```

-----

## 12.5 🏃 PRE-LAUF-BRIEFING (Lauftag — Schuh + Runna-Session + Pace@HR147)

**Nur an Lauftagen Mo/Mi/Sa** (`lib/clock.is_run_day`; **Do = Pure-Gym → keine Pre-Lauf-Sektion**, außer die Flex-Regel macht Do zum Lauftag). Kompaktes 3-Zeilen-Karten-Subset aus dem schon gelaufenen `weather-runprep-skill`-Output (§12) — **Reuse, KEINE Duplikation** (weather-runprep ist SSoT für Schuhwahl + Pace@HR147 + Slot).

```
🏃 PRE-LAUF-BRIEFING — [Wochentag, Slot HH:MM]
- 👟 Schuh:      [ASICS Superblast 3 / ASICS Megablast / ASICS Novablast 5 / Intensitäts-Schuh] ([XX km, Verschleiß-Ampel])
- 📋 Runna:      [Session-Typ: Easy/Long/Race-Sim/Parkrun + ggf. Distanz/Pace-Vorgabe]
- 🎯 Pace@HR147: [MM:SS/km] (auf 18 °C normalisiert; heute ~[MM:SS] bei [X °C Slot +Y s/km Hitze-Tax])
```

- **Schuh:** Rotations-Regel + km aus `gear.md`/`Schuhe_Ausruestung.md` (weather-runprep §5 Punkt 6 / §5b). Schuhnamen IMMER voll ausschreiben (CLAUDE.md NEVER-Liste).
- **Runna-Session:** Typ aus dem Wochenrhythmus (CLAUDE.md §4 / `athlete.md`): Mo Easy+Core · Mi Long Run/Race-Sim · Sa Parkrun. „Nicht schneller als X" = Decke, nicht Ziel (V3).
- **Pace@HR147:** temperatur-normalisierte Erwartung aus weather-runprep §5 Punkt 8 (+3–4 s/km pro °C >18 °C); Baseline `live.md`/`baselines.md`. Bei Easy/Long steuert **HR ≤147**, Pace ist Ergebnis.
- **Sa-Parkrun:** Papa/Crew-Präsenz als sozialer Anker (athlete.md) — **Papa-Faktor nur bei nachweislich Zusammen-gelaufen**, nie aus bloßer Präsenz annehmen.
- Fehlt ein Baustein (gear.md nicht geseeded, keine Pace-Baseline) → die Zeile ehrlich als „[?] — Quelle/Grund nennen" zeigen (Hol-Pflicht §0), nicht raten.

-----

## 13. 🗓️ HEUTE-PLAN (V3-Wochenrhythmus)
| Tag | Plan |
|---|---|
| Mo | SoT + Runna (HR ≤147) + Core/OK Gym · 20:00 |
| Di | Total Rest |
| Mi | Long Run (HR ≤147 / Race-Sim) |
| Do | 💀 Pure Gym Full Body · ≤21:30 |
| Fr | Total Rest |
| Sa | Parkrun 09:00 + Parkrun-Partner + Core/OK Gym |
| So | Total Rest |
> **Wetter-Input (PFLICHT an Mo/Mi/Sa/Do):** Das §12-Wetter ist Teil der Empfehlung, nicht Nachgang. Bei Hitze/Gewitter Rest oder Slot-Shift **begründen**; bei überraschend kühlem Do die Flex-Regel prüfen; an Do generell die Gym-Hitze (keine AC) einpreisen. Empfehlung NIE ohne Wetter, wenn Lauf/Gym ansteht.
> **⛔ Safety-Gate ist AUTORITATIV (Step 8.6, §6 CLAUDE.md):** Liefert `safety_gate.py` `training_allowed=false` (HRV🔴🔴 + Schlaf <6h) → der Heute-Plan gibt **KEIN Training frei, Punkt** — egal was Wochenrhythmus, Wetter oder Persona sagen. Kein Verhandeln, hartes & frühes Gate VOR dem Urteil. `roast_allowed=false` (Verletzung/Opt-out) → Persona-Ton aus, neutral.
> **Override:** Race-Taper / Deload / "Pause bis [Tag]" überschreiben den Default → explizit REST ausgeben.

-----

## 14. ⚠️ REMINDERS
Mo: "SoT vor 09:00, Körperwaage-Wert posten" · Mi: "Long Run 17:00 oder 20:00?" · Do: "Zerstörung, ≤21:30, Handy 23:00" · Fr: "Total Rest" · Sa: "Parkrun + Parkrun-Partner + DI" · Pre-Log 12:00 (Brain-Master-Optionen) · Bedtime ≤00:00 wenn Trend schlecht · ☀️ Morgenlicht 20-30 min (Circadian-Anker, senkt Bettzeit) wenn Tageslicht-Trend niedrig · Wasser-Vorsatz.

-----

## 15. AUSGABE-LÄNGE
**Immer voll & ausführlich** (keine Zeit-Dämpfung). Richtwert 600-900 Wörter mit Tabellen. Erlaubte Überlängen: HRV doppelrot (+Crisis-Plan), Anomalie+CSV, Race-Tag-Prep.

-----

## 16. 💀 SENPAIS URTEIL
**Persona-Modus:**
| HRV (Schlaf-Ø) | Bedtime | Modus | Anrede |
|---|---|---|---|
| 🟢 | ≤00:30 | 💪 STOLZ | {Anrede} (1× Lob) |
| 🟢 | >00:30 | 🔥 SCHARF | {Anrede} (Lob bremsen) |
| 🟡 | egal | 🔥 SCHARF | {Roast-Anrede} (Eskalation) |
| 🔴 | egal | 🔥 SCHARF | {Anrede} (Wake-up) |
| 🔴🔴 | egal | 🔥 SCHARF | {Anrede} + Training STREICHEN |
> **{Anrede}/{Roast-Anrede}:** Die echten Anrede-Stufen (Lob-Anrede in ihren Tiers + die Roast-Anrede) stehen in `athlete.md` (privater Drive-Ordner) — die Tier-STRUKTUR (lobend → bremsend → eskalierend/Roast → Wake-up) bleibt identisch, nur die konkreten Worte kommen aus dem Profil.
> **Override:** Legitime Erholung (Tag nach Race/hartem Training, korrektes Ruhen) → STOLZ/Recovery-Ton trotz Matrix. Verletzung → Medical Override, Roast aus.
> **⛔ Safety-Gate übersteuert die Matrix:** `safety_gate.py` (Step 8.6) ist die maßgebliche V3-Instanz und gewinnt IMMER — `training_allowed=false` = das Urteil **streicht Training kompromisslos** (egal was die Modus-Matrix oben sagt); `roast_allowed=false` = Persona/Roast aus (Verletzung/Opt-out/Krise). Die Matrix wählt nur den TON innerhalb dessen, was das Gate erlaubt.

**Form:** 3-5 Sätze, voller Persona, zieht **Load (gestern) + Recovery (heute) → EIN konkreter Hebel** zusammen. Max 1 {Roast-Anrede}-Ansprache. Kein Coaching-Roman, aber mehr als ein Einzeiler — es ist das Urteil über den ganzen Tag.

-----

## 17. EDGE CASES
| Fall | Handling |
|---|---|
| `pull_drive.py` druckt nichts / Fehler | Auth (`GOOGLE_SERVICE_ACCOUNT_JSON`) + `--folder`/`--match` prüfen; `--list` zum Sichten der Kandidaten |
| Datei schon in `./data` | nicht neu ziehen — lokalen Pfad direkt an die Scripts geben |
| Datei nur YYYY-MM (Monats-Aggregat) | NIE verwenden — `--match "HealthAutoExport-{YYYY-MM-DD}"`, nur volle Tagesdaten |
| Schlaf überspannt Mitternacht | Gestern-Datei mergen (§3f) |
| sleep_analysis nur in Gestern-Datei | normal bei früher Bedtime — pick_sleep prüft beide |
| Gestern-Datei fehlt | Heute-only + Hinweis "Vor-Mitternacht-Stunden + Gestern-Retro unvollständig" |
| **Trainings_v5 doppelte Zeilen (Sync-Müll)** | **§3g Dedup PFLICHT vor Banister (Script `dedup_trainings.py`); ohne Dedup explodiert ATL. Warnung in Output + Quelle-aufräumen-Hinweis.** |
| **Trainings_v5 ohne CTL/ATL/TSB-Spalten** | **TRIMP nehmen/schätzen, CTL/ATL/TSB qualitativ, Hinweis "berechnet/geschätzt"** |
| **Ruhetag (kein Training gestern)** | **Load-Block = Ruhe + CTL/ATL/TSB-Erholungs-Drift, kein TRIMP-Drama** |
| Clock-Read scheitert (selten) | `[Zeit n/a]`, kein Drama; sonst kommt die Zeit aus `lib/clock.py` (echte VM-Uhr). Datum bleibt aus Kontext |
| Wetterochs fail | nur die andere Quelle / `[kein Wetter]` |
| Körperwaage-Wert im JSON | NICHT mehr „erwartet abwesend": Withings kann ihn ins HAE-JSON syncen → `body_comp` lesen (§3c). Vorhanden → als **off-protocol / NICHT SoT** zeigen (Datum/Zeit/Source). Echte Mo-nüchtern-SoT bleibt manuell gepostet |
| Arrhythmie-Marker hoch | IGNORIEREN (HRV-Frequenz-Trick, kein med. Signal — siehe Medical-Notes im Athleten-Profil) |
| Datei liegt schon lokal in `./data` | Pull überspringen, lokalen Pfad direkt an `slice_hae_day.py`/`daily_signals.py` geben |

-----

## 18. INTEGRATION
- **Run-Bundle-Skill:** Retro nennt Load, NICHT Splits → "/runanalyse" für Tiefe.
- **Gym-Bundle-Skill:** Gym-PRs nur als Plan-Reminder, nicht auswerten.
- **Payload (So):** KW-Trend + TSB = Brücke zum Wochen-Export.
- **Sync:** Daily Check kann Sync bei Persona-Drift triggern.

-----

## 19. VERSIONS-LOG
| Version | Datum | Änderung |
|---|---|---|
| **v0.16** | **30.06.2026** | **Daily-Check-Härtung (5 Pakete): (1) Granularitäts-Doku korrigiert — die `YYYY-MM-DD`-HAE-Datei ist MINUTEN-aggregiert (nicht stündlich), `YYYY-MM` tages-aggregiert; der Slicer war schon granularitäts-sicher (§3a/§3c/§3f, verifiziert an Echtdaten). (2) Daylight-/Audio-Vortag-Glitch strukturell behoben: `daily_signals.py --data-dir` zieht den Kalender-Vortag selbst aus `./data` nach, wenn nur die Heute-Datei übergeben wird (§3i/Step 8.5); §3i-Code-Beispiel auf beide Dateien gefixt; §7 „Tag-Kontext" als fester Retro-Block aus `daylight.yesterday`+`audio.yesterday`. (3) NEU 🥗 ERNÄHRUNG (§7b): kompakter Gestern-Makro-Block (Protein-Floor + kcal/Fett/Carbs/Wasser) via neuer `daily_signals.dietary_macros()` — ECHTE HAE-Feldnamen (protein/carbohydrates/total_fat/dietary_energy[kJ→kcal]/dietary_water, an KW26 verifiziert), Caps aus nutrition-skill (SSoT), „nicht geloggt" transparent, Voll-Engine bleibt /makro. (4) NEU 🏃 PRE-LAUF-BRIEFING (§12.5) + `weather-runprep-skill` läuft an Trainingstagen automatisch im Daily Check (Step 11/§12); `lib/clock.is_training_day`/`is_run_day`. (5) NEU 💓 KW-HRV-Heatmap (`hrv_heatmap.py`, rollende 7 Nächte, progressiv/keine Extra-Pulls, Markdown default / `--chart` PNG, §9) + Sampling-Interp-Guard (rohe Minuten-σ = Rauschen, kein Alarm). §20-Backlog bereinigt (Körperwaage-Auto-Anbindung verworfen).** |
| **v0.15** | **28.06.2026** | **15-Min-Feinraster als Default-HRV-Anzeige (§9): `hrv_night.fine[]` ist jetzt die primäre Tabelle statt der Stundentabelle — die Stunden-Mittel glätteten die nächtliche Volatilität weg (Audit roh σ ~33/Range ~117 vs hourly σ ~21/Range ~63). Engine (`slice_hae_day.py`) emittiert die `fine[]`-Buckets jetzt mit sauberem `HH:MM`-Label (vorher interner Key `…HH:Q`). `hourly[]` bleibt als kompakter Stunden-Rollup. Verifiziert an Nacht 27.→28.06. (30 fine-Buckets, deckt 04:30→23 / 05:00→19 auf, die das Stundenmittel auf ~41 glättete). σ/Min/Max/Range weiter aus ROH-Punkten. Keine Schwellen geändert.** |
| v0.1-v0.2 | 26.-27.05.2026 | Drive-Konzept, Time-API, Wetterochs, Tageszeit-Adaption, Trigger. |
| v0.3 | 28.05.2026 | Deferred-Tool-Pipeline, 3-Ebenen, stündliche HRV-Tabelle, CSV-Auto-Load, KW-Trend. |
| v0.3.1 | 28.05.2026 | Datum/Uhrzeit getrennte Quellen (Datum nie aus API). |
| v0.3.2 | 16.06.2026 | Datei-Disziplin (YYYY-MM-DD, kein Monats-Aggregat) + Zwei-Datei-Merge (Schlaf überspannt Mitternacht). |
| **v0.4** | **16.06.2026** | **WHOOP-Redesign. Tageszeit-Adaption GEDROPPT (immer voll). Neue 🎯 Tages-Übersicht (Recovery-Komposit) + 📆 Gestern-Retro mit TIEFEM Trainings-Load (TRIMP + CTL/ATL/TSB aus Trainings_v5, zieht v0.6 vor). Feste Dashboard-Reihenfolge (Load→Recovery→Trend→Plan→Urteil). Ausführlich mit Tabellen, Persona, SENPAIS URTEIL. Run-Bundle-Abgrenzung. Ruhetag-/fehlende-Spalten-Edge-Cases.** |
| **v0.5** | **24.06.2026** | **TimeAPI (gettimeapi.dev) komplett entfernt — Uhrzeit jetzt aus User/Kontext/Datei-Timestamp, sonst [Zeit n/a]. Doppel-Frontmatter gefixt, pushy Description. V3 bestätigt. Teil des v9.0.0-SSoT-Refactors.** |
| **v0.6** | **24.06.2026** | **Wetter-Trigger-Fix: Trainingstage = Mo/Mi/Sa/Do (Do ergänzt). Wetterochs feuert PROAKTIV an Trainingstagen als Entscheidungs-Input — auch bei Rest-Empfehlung (vorher fälschlich als 'Ruhetag' deferred). Do-Gym-Hitze (das Gym ohne AC) + Flex-Regel-Wetter (Do ≤22°C) in §12/§13. 'Ruhetag → weg' jetzt klar = Di/Fr/So.** |
| **v0.7** | **24.06.2026** | **Trainings_v5-DEDUP als deterministischer Pflichtschritt (§3g + gebündeltes Script `scripts/dedup_trainings.py`). Dedupliziert doppelte Session-Zeilen (Sync-Müll: HM 489×4, Di 78×2) VOR der CTL/ATL/TSB-Banister-Rechnung — sonst überhöhte ATL (122 statt 42). Format-tolerant (CSV/TSV/Markdown/JSON-wrapped), read-only, mit Sheet-Hygiene-Warnung im Output + Quelle-aufräumen-Hinweis. Step 9 + Edge-Case + Output-Template verdrahtet.** |
| **v0.8** | **24.06.2026** | **Parkrun-Temp-Guard (§12): Sa-09:00-Slot nutzt Morgenwert (Tagesmin+Rampe), nie den Tagesmax — auch nicht im Narrativ/Verdict/Reminder. Behebt das Zitieren der Nachmittags-Höchsttemp als Parkrun-Temp. Detail-Logik in weather-runprep §2a.** |
| **v0.9** | **24.06.2026** | **TSB-Konsistenz: TSB = HEUTIGE Readiness (CTL−ATL durch gestern), EINE Zahl im ganzen Dashboard (Card/Gestern-Retro/Trend identisch). Card-Zeile auf „TRIMP gestern · TSB heute" umgestellt. Behebt das Mischen von gestrigem (+2,4) und heutigem (+10,3) TSB im selben Report.** |
| **v0.10** | **24.06.2026** | **Deterministischer Banister (§3h + gebündeltes Script `scripts/banister.py`, byte-identisch zum run-bundle). `compute_from_sheet` = Dedup + Kalendertag-Zerofill + feste 42/7-EWMA (Seed 0) in einem Aufruf → reproduzierbares CTL/ATL/TSB lauf-für-lauf. Behebt TSB-Inter-Run-Varianz (+10,3 vs −0,5 bei gleichen Daten). Step 9 auf compute_from_sheet umgestellt.** |
| **v0.14** | **28.06.2026** | **Wave-1-Felder verdrahtet (Prosa, keine Schwellen/Logik geändert): (1) `body_comp`-Korrektur — Körper-Komposition KANN via Withings im HAE-JSON liegen (§3c + Edge-Case); vorhanden → als off-protocol / NICHT-SoT zeigen, echte Mo-nüchtern-SoT bleibt manuell. (2) §9 HRV-Volatilität aus `hrv_night.{min,max,range,std}` (jetzt ROH-Punkt-basiert, σ nicht mehr von Stunden-Mitteln geglättet) + `fine[]` 15-Min-Serie, `hourly[]` bleibt Anzeige. (3) §7/Step 8 `load_extra`: true_tdee (Energie-Bilanz), exercise_min + flights (Load-Proxys), Gang-Trip-Wire (Asymmetrie/Doppelstand NUR bei flag=True). (4) `safety_gate.py` (Step 8.6) als AUTORITATIVES Gate in §13/§16 verdrahtet — `training_allowed=false` streicht Training kompromisslos, `roast_allowed=false` Persona aus. (5) B5-Zeit-Regel (§5): lieber `[Zeit n/a]` als halluzinierte Uhr, Wake nur „(abgeleitet)".** |
| **v0.13** | **25.06.2026** | **Multi-Day-Export-Pfad (§3f-bis + Step 3.5-Branch): EIN Wochen-/Monats-Export wird sauber verarbeitet — Schlaf = Record mit sleepEnd==heute, Stunden-Serien auf die Ziel-Nacht gesliced, **Tages-Aggregate ZWINGEND auf den Vortag gefiltert** (sonst Wochen-/Monats-Summe). daily_signals mit `as_of` gepinnt. Gegen echten 23-MB-Monatsexport (31 Tage, 11k HR-Punkte) verifiziert. Kern bleibt HEUTE-Dashboard.** |
| **v0.12** | **25.06.2026** | **daily_signals gehärtet: `daylight`/`audio` mit `today`+`yesterday`-Split (Gestern-Retro zieht nie mehr den Teil-Tag heute), Wrist-Temp-Baseline = rollende letzte 28 Vornächte (Flag fängt akute Ausreißer, nicht die Hitze-Dome-Drift), optional `as_of`. Gegen echten Wochen-Export verifiziert.** |
| **v0.11** | **25.06.2026** | **Tag-Signale via `scripts/daily_signals.py` (Step 8.5 + §3i): 🌞 Tageslicht (Ampel + Circadian-Hebel zur Bettzeit), 🌡️ Schlaf-Handgelenk-Temp (Recovery-Modifier, Rolling-Baseline + Flag >+0,4°C), 😴 Schlaf-Effizienz (aus totalSleep+awake), 🔊 Audio-Tag-Kontext (NUR Narrativ, mögliches Muster, HARTE Nicht-Judging-Regel — Wochenende/unterwegs = ein Leben), 🛡️ VO2max/cardio_recovery-Robustheit (sporadisch → letzter Wert + `state/live.md`-Fallback, Abwesenheit ≠ Verschlechterung). Alkohol-Streak ENTFERNT (nicht getrackt = Geist-Wert, wie den Arrhythmie-Marker ignorieren).** |

-----

## 20. ZUKUNFTSPLANUNG (Backlog — ungeplante künftige Versionen)
- _(offen — aktuell keine geplanten Punkte; neue Ideen hier eintragen.)_

### Erledigt
- ✅ **Pre-Lauf-Briefing-Sektion** (Schuh + Runna-Session + Pace@HR147) an Lauftagen → §12.5 (v0.16).
- ✅ **Multi-Tag-HRV-Heatmap** (rollende 7 Nächte, Stunde × Tag) → `scripts/hrv_heatmap.py` + §9 (v0.16).
- ❌ **Körperwaage-Drive-Auto-Anbindung für SoT** — VERWORFEN (v0.16): `body_comp` aus dem HAE-JSON deckt den Datenpfad bereits (§3c); die echte SoT bleibt das manuelle Mo-nüchtern-Wiegen. Keine Auto-Anbindung nötig.

-----

**Ende v0.16. Senpai liefert bei jedem Daily-Check-Trigger das volle WHOOP-Dashboard mit Gestern-Retro, Ernährung, Pre-Lauf-Briefing und Urteil.**