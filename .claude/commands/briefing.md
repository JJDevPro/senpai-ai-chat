---
description: Senpais proaktives Morgen-Briefing — Daily Check, aber LEAD mit den ACTIONABLE V3-Signalen (Sentinel) wenn welche feuern. Für die geplante 10:00-Routine.
argument-hint: "[optional: Datum YYYY-MM-DD · sonst heute]"
---

# /briefing — Senpais proaktives Morgen-Briefing ("Sentinel"-Flow)

Du bist **Senpai** (CLAUDE.md). Dies ist der **proaktive** Morgen-Flow: nicht abwarten,
bis gefragt wird, sondern die Daten ziehen, nur die **ACTIONABLE** Signale aufflaggen und
sonst das normale Daily-Dashboard liefern. **Alle Aufrufe vom Repo-Root (CWD), `python3`.**

> **⛔ Keine Logik hier duplizieren.** Dieses Command ORCHESTRIERT die bestehende
> `daily-check-skill` + die deterministischen Gates. Der Daily-Check-Workflow,
> die Ampeln, die Output-Struktur und die Persona-Modi leben dort
> (`.claude/skills/daily-check-skill/SKILL.md`) bzw. in CLAUDE.md §5/§6/§16 — lies/lade sie.
> Hier steht NUR die Reihenfolge + die „lead with the alert"-Regel.

Bezugstag: **`$ARGUMENTS`** wenn gesetzt, sonst **heute** (Datum aus Claude-Kontext, NIE API).
Im Folgenden `{heute}` = Bezugstag, `{gestern}` = {heute} − 1.

---

## Schritt 1 — State aus dem privaten Drive-Ordner ziehen (PFLICHT, CLAUDE.md §0)

```bash
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match "athlete.md"   --out ./data
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match "live.md"       --out ./data
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match "baselines.md"  --out ./data
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match "learnings.md"  --out ./data
```
Lies `./data/athlete.md` + `./data/live.md` → Identität, Anrede-Mapping, **die metabolische
Gewichts-Schwelle** (für den Weight-Creep-Trip-Wire), VO2-Baseline, Medical/Sensor-Ignore-Regeln.
Notiere die Schwelle als `{WEIGHT_THRESHOLD_KG}`.

---

## Schritt 2 — Daily Check fahren (die `daily-check-skill` MACHT die Arbeit)

Lade `.claude/skills/daily-check-skill/SKILL.md` und folge ihrem Workflow (§2). Kurzgefasst:

```bash
# HAE heute + gestern (Mitternachts-Merge), nur volle Tagesdateien YYYY-MM-DD:
python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-{heute}"   --out ./data
python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-{gestern}" --out ./data

# Slice (Aggregate, KEINE Roh-Serien) — Ausgabe SICHERN, sie speist Gate + Sentinel:
python3 .claude/skills/daily-check-skill/scripts/slice_hae_day.py \
    ./data/HealthAutoExport-{heute}.json ./data/HealthAutoExport-{gestern}.json \
    --as-of {heute} > ./data/slice_{heute}.json

# Tag-Signale (Tageslicht/Effizienz/Wrist-Temp/Audio/VO2-Fallback):
python3 .claude/skills/daily-check-skill/scripts/daily_signals.py \
    ./data/HealthAutoExport-{heute}.json --as-of {heute}

# Sheets → CSV (Trends + Trip-Wire-Input):
python3 lib/pull_drive.py --sheet 1zhNbm7f2SOeJL0QWGhaDt113R61tmHvi0KZCT1Z0sxU --tab "Trainings"          --out ./data/Trainings_v5.csv
python3 lib/pull_drive.py --sheet 1ENUtb3LS5GgaDDhciBCuyUDqlwJTsjU6n6PTCZuIcDE --tab "Tägliche Kennzahlen" --out ./data/Kennzahlen_taeglich.csv
python3 lib/pull_drive.py --sheet 1ENUtb3LS5GgaDDhciBCuyUDqlwJTsjU6n6PTCZuIcDE --tab "Gewicht"             --out ./data/Gewicht.csv
```
Dann **dedup → banister** (CTL/ATL/TSB) wie in SKILL.md §3g/§3h. Das ergibt das volle
WHOOP-Dashboard (Card · Gestern-Retro · Schlaf · HRV · KW-Trend · Heute-Plan · Urteil).
**Multi-Day-Export?** → SKILL.md §3f-bis (EIN Range-File, `--as-of` slict selbst).

---

## Schritt 3 — Deterministische Gates (AUTORITATIV, vor dem Urteil)

```bash
# (a) Safety-Gate — die maßgebliche V3-Instanz (CLAUDE.md §6, SKILL.md Step 8.6):
python3 .claude/skills/daily-check-skill/scripts/safety_gate.py ./data/slice_{heute}.json \
    --prev-hrv {gestern_hrv_avg}        # gestrige hrv_night.avg aus Kennzahlen_taeglich.csv/Gestern-Slice
    # ggf. --injury / --opt-out aus dem Chat-Kontext

# (b) Sentinel — proaktive Trip-Wires (HRV/RHR-Trend, Gewichts-Drift, Asymmetrie, Atmung, Bedtime):
python3 .claude/skills/daily-check-skill/scripts/sentinel.py \
    --daily ./data/slice_{heute}.json \
    --health-csv ./data/Kennzahlen_taeglich.csv \
    --weight-csv ./data/Gewicht.csv \
    --weight-threshold-kg {WEIGHT_THRESHOLD_KG}
```
- **`safety_gate` gewinnt IMMER:** `training_allowed=false` (HRV🔴🔴 + Schlaf <6h) → der Heute-Plan
  gibt KEIN Training frei, kein Verhandeln. `roast_allowed=false` (Verletzung/Opt-out) → Persona-Ton aus.
- **`sentinel`** liefert `{alerts, actionable, checked}`. Es ENTSCHEIDET nichts über Training — bei
  HRV🔴🔴 zeigt es nur einen `hrv_double_red`-Pointer zurück aufs Gate (nicht dupliziert).

---

## Schritt 3.5 — Garmin-Klon-Layer (Readiness · HRV-Status · Body Battery · Running Tolerance)

Aus den schon gezogenen Aggregaten (KEIN Re-Compute), Reihenfolge wie SKILL.md Steps 10.1–10.5:

```bash
# (c) HRV-Status (60-Tage-MAD-Band aus der Tägliche-Kennzahlen-Historie):
python3 .claude/skills/daily-check-skill/scripts/hrv_baseline.py \
    --health-csv ./data/Kennzahlen_taeglich.csv --as-of {heute} > ./data/hrv_baseline_{heute}.json

# (d) Readiness 0–100 (fusioniert HRV-Status + Schlaf + TSB + Gate + Sentinel):
python3 .claude/skills/daily-check-skill/scripts/readiness.py \
    --hrv-baseline ./data/hrv_baseline_{heute}.json --daily ./data/slice_{heute}.json \
    --banister <banister_json> --safety-gate <gate_json> --sentinel <sentinel_json> > ./data/readiness_{heute}.json

# (e) Body Battery + (f) Running Tolerance:
python3 .claude/skills/daily-check-skill/scripts/body_battery.py \
    --slice ./data/slice_{heute}.json --hrv ./data/hrv_baseline_{heute}.json --banister <banister_json> --as-of {heute} > ./data/bb_{heute}.json
python3 .claude/skills/daily-check-skill/scripts/running_tolerance.py \
    --trainings ./data/Trainings_v5.csv --as-of {heute}

# (g) History persistieren (T12, best-effort, NON-BLOCKING — Pre-Seed-Hinweis nur melden):
python3 .claude/skills/daily-check-skill/scripts/readiness_history.py --as-of {heute} \
    --readiness ./data/readiness_{heute}.json --body-battery ./data/bb_{heute}.json \
    --banister <banister_json> --hrv-baseline ./data/hrv_baseline_{heute}.json
```
- **⛔ Safety-Gate bleibt autoritativ:** Bei `safety_override=true` steht die Readiness ≤35 + rot, egal was die Komponenten sagen.

---

## Schritt 4 — Report zusammensetzen: LEAD mit den Alerts, wenn `actionable=True`

- **`sentinel.actionable == True`** → **beginne den Report mit den Alerts**, in Senpais Stimme
  (CLAUDE.md §2, Modus aus §16/SKILL.md §16), sortiert nach Schärfe (CRITICAL → WARN). Pro Alert:
  *was* feuert, *warum* (der `detail` nennt schon §-Bezug + Hebel), *ein* konkreter Schritt.
  Danach folgt das **normale, volle** Daily-Dashboard (nichts kürzen — „Länge ≠ Uhrzeit", CLAUDE.md §3).
  WATCH-Einträge sind KEIN Lead — höchstens eine Randnotiz im passenden Block.
- **`actionable == False`** → **normaler Daily Check**, kein Alarm-Lead. Stilles 🟢 genügt;
  die `checked`-Liste belegt, dass die Trip-Wires liefen und ruhig blieben (1 Satz, kein Drama).
- In BEIDEN Fällen bleiben Gate-Overrides bindend: ein `training_allowed=false` streicht Training
  sichtbar im Heute-Plan + Urteil, egal was Sentinel/Wochenrhythmus/Wetter sagen.

---

## Schritt 5 — Heute-Plan nach Wochentag (V3-Wochenrhythmus, SKILL.md §13)

Aus dem `{heute}`-Wochentag den Plan + die Reminder ziehen (SKILL.md §13/§14). Kurz:
**Mo** SoT-Wiegen + Run (HR≤147) + Core/OK 20:00 · **Di** Total Rest · **Mi** Long Run (HR≤147/Race-Sim) ·
**Do** 💀 Pure Gym Full Body ≤21:30 · **Fr** Total Rest · **Sa** Parkrun 09:00 + Partner + Core/OK ·
**So** Total Rest. An **Mo/Mi/Sa/Do** Wetterochs PROAKTIV (SKILL.md §12 — Entscheidungs-Input).
Override (Taper/Deload/„Pause bis…") + jedes Gate-Streichen schlägt den Default.

---

**Kurz:** State ziehen → Daily Check (Skill) → Gate + Sentinel → Garmin-Klon-Layer
(HRV-Status · Readiness · Body Battery · Running Tolerance) → bei `actionable` mit dem Alert
führen, sonst normaler Check → Heute-Plan. Nur Aggregate + Verdict erreichen den Kontext (§0).
Verdict am Ende via `python3 lib/archive.py --report - --kind daily --date {heute}` ins Journal (best-effort).
