#!/usr/bin/env python3
"""
sentinel.py — deterministischer V3-Trip-Wire-Evaluator ("Senpai-Sentinel").

WARUM dieses Skript existiert:
  Der Daily Check (SKILL.md) ist REAKTIV — er feuert, wenn der Athlet fragt. Senpai
  soll aber PROAKTIV nur die ACTIONABLE Signale aufflaggen: Muster über mehrere Tage
  (HRV-/RHR-Trend, Gewichts-Drift) plus die scharfen Einzeltag-Trip-Wires (Gang-
  Asymmetrie, Atemstörungen, Bedtime-Drift). Wie `safety_gate.py` macht dieses Skript
  CLAUDE.md-Prosa (§5 Ampel / §6 Overrides) zu einem deterministischen, testbaren
  Urteil — KEIN LLM-Rauschen. Es ENTSCHEIDET nichts über das Training (das ist die
  Aufgabe von `safety_gate.py`), sondern listet nur, WAS Aufmerksamkeit braucht.

⛔ KERNREGEL (CLAUDE.md §0): Dieses Skript konsumiert NUR bereits reduzierte Aggregate
  — die Tages-CSV (1 Zeile/Tag), den `slice_hae_day`-Slice (heute reduziert) und die
  Gewichts-CSV (1 Wiegung/Tag). NIE rohe Per-Sekunde-/Per-Minute-Serien. Es gibt nur
  ein kompaktes Alert-JSON aus, nie Roh-Arrays.

⛔ PERSONAL-DATA-FREI (CLAUDE.md Kopf): Es ist KEINE Körper-Schwelle hartkodiert. Die
  metabolische Gewichts-Schwelle lebt im Drive-`athlete.md` und wird per
  `--weight-threshold-kg` übergeben (vom /briefing bzw. der Skill-Pipeline gefüllt).

TRIP-WIRES (jeweils an CLAUDE.md §5/§6 gebunden — KEINE neuen Schwellen erfunden):

  1. HRV🔴 sustained  (§5: "<50 (2+ Tage) → Bedtime/Mg/−10% Intensität")
       HRV-Tages-Ø < 50 ms an ≥2 jüngsten Tagen in Folge → WARN.
       Nur heute rot (kein 2-Tage-Kontext) → WATCH (beobachten, nicht eskalieren).

  2. HRV🔴🔴 defer  (§5/§6: "<40 + Schlaf <6h → Training STREICHEN")
       HRV heute < 40 ms → CRITICAL-POINTER. Dieses Skript DUPLIZIERT das Gate NICHT —
       es eskaliert nur nach `safety_gate.py` (das die AND-Schlaf-Bedingung autoritativ
       prüft und `training_allowed` setzt).

  3. RHR-Elevation  (§6 Recovery-Komposit: "RHR Baseline+5")
       Ruhepuls an ≥2 jüngsten Tagen ≥ (rollender Median + 5 bpm) → WARN.

  4. Weight-Creep  (§1: metabolische Gewichts-Schwelle, Wert aus athlete.md)
       Gewicht steigt über die letzten Wiegungen Richtung Schwelle. Auf/über Schwelle
       ODER innerhalb des Annäherungs-Bandes + steigend → WARN; nur steigend → WATCH.

  5. Bedtime-Drift  (§8: Bedtime 🔴 >00:30)
       Bedtime aus --daily klar nach 00:30 → WARN (1-Tages-Read, bei 2+ Tagen Muster).

  6. Walking-Asymmetry-Trip-Wire  (§7: Gang-Asymmetrie >5 % anhaltend)
       --daily load_extra.gait.asymmetry_pct.flag == True → WARN (Verletzungs-/
       Schonhaltungs-KONTEXT, NIE als Befund framen).

  7. Breathing-Disturbances  (§3c/§11: Schwelle 10/h)
       --daily recovery.breathing_disturbances > 10 → WARN (Medikation/Allergie prüfen).

CLI:  sentinel.py [--health-csv CSV] [--daily JSON|-] [--weight-csv CSV]
                  [--weight-threshold-kg N] [--weight-approach-kg N]
      --health-csv  : Gesundheitsdaten 'Tägliche Kennzahlen' (Datum, Ruheherzfrequenz,
                      HFV[=HRV], VO₂ max …) — Mehrtages-HRV-/RHR-Trend.
      --daily       : `slice_hae_day`-Ausgabe (heute reduziert). "-" liest stdin.
      --weight-csv  : Gesundheitsdaten 'Gewicht' (Datum, Gewicht) — Gewichts-Trend.
      --weight-threshold-kg : metabolische Schwelle aus athlete.md (sonst kein Proximity-
                      Urteil, nur Trend).

Output (kompaktes JSON, NIE Roh-Arrays — §0):
  {alerts:[{signal,level,detail}], actionable:bool, checked:[...], as_of?}
    level     ∈ {CRITICAL, WARN, WATCH}   (WATCH = nur Hinweis)
    actionable = True, wenn IRGENDEIN Alert WARN+ (CRITICAL/WARN) feuert.
    checked   = Liste der Trip-Wires, die mit den vorhandenen Daten ausgewertet wurden.
"""
import argparse
import csv
import json
import re
import statistics
import sys
import unicodedata

# --- Schwellen: 1:1 aus CLAUDE.md §5/§6 — NIE hier neu erfinden -----------------
HRV_RED = 50            # §5: 🔴 unter diesem Wert (Deload/Cap bei 2+ Tagen)
HRV_CRITICAL = 40       # §5/§6: 🔴🔴 unter diesem Wert (Gate-Territorium)
RHR_OVER_BASELINE = 5   # §6 Recovery-Komposit: "RHR Baseline+5"
BREATHING_MAX = 10      # §3c/§11: Atemstörungen actionable über diesem Wert
BEDTIME_TARGET_MIN = 30  # §8: Bedtime-Ziel 00:30 = 30 min nach Mitternacht
SUSTAINED_DAYS = 2      # §5/§6: "2+ Tage" / "≥2 days" = anhaltendes Muster
WEIGHT_APPROACH_KG = 2.0  # operatives Annäherungs-Band (kein Körper-Fakt)

# Level-Ordnung + welche Level als "actionable" zählen.
LEVEL_RANK = {"CRITICAL": 0, "WARN": 1, "WATCH": 2}
ACTIONABLE_LEVELS = {"CRITICAL", "WARN"}

SIGNAL_ORDER = [
    "hrv_sustained_red", "hrv_double_red", "rhr_elevation", "weight_creep",
    "bedtime_drift", "walking_asymmetry", "breathing_disturbances",
]


# ================================================================ trip-wires (pure)
def _hrv_sustained(daily, health_rows):
    """§5: HRV-Ø <50 an den 2 jüngsten Tagen → WARN; nur heute rot → WATCH."""
    hrv_by_day = {}
    for r in health_rows or []:
        if r.get("date") and r.get("hrv") is not None:
            hrv_by_day[r["date"]] = r["hrv"]
    if daily:
        as_of = daily.get("as_of")
        today_hrv = (daily.get("hrv_night") or {}).get("avg")
        if as_of and today_hrv is not None:
            hrv_by_day[as_of] = today_hrv
    if not hrv_by_day:
        return None, False

    days = sorted(hrv_by_day)
    latest = days[-1]
    if len(days) >= SUSTAINED_DAYS:
        recent = days[-SUSTAINED_DAYS:]
        vals = [hrv_by_day[d] for d in recent]
        if all(v < HRV_RED for v in vals):
            shown = ", ".join(f"{d}={round(hrv_by_day[d])}" for d in recent)
            return ({"signal": "hrv_sustained_red", "level": "WARN",
                     "detail": f"HRV🔴 {SUSTAINED_DAYS} Tage in Folge <{HRV_RED} ms "
                               f"({shown}) → Bedtime/Mg/−10 % Intensität (§5)."}, True)
        if hrv_by_day[latest] < HRV_RED:
            return ({"signal": "hrv_sustained_red", "level": "WATCH",
                     "detail": f"HRV🔴 nur heute ({latest}={round(hrv_by_day[latest])} <{HRV_RED} ms); "
                               f"Vortag {days[-2]}={round(hrv_by_day[days[-2]])} nicht rot — "
                               f"kein 2-Tage-Muster, nur beobachten (§5)."}, True)
        return None, True

    # nur ein Tag verfügbar
    if hrv_by_day[latest] < HRV_RED:
        return ({"signal": "hrv_sustained_red", "level": "WATCH",
                 "detail": f"HRV🔴 Einzeltag ({latest}={round(hrv_by_day[latest])} <{HRV_RED} ms); "
                           f"nur 1 Tag vorhanden — 2-Tage-Kontext fehlt, nicht eskalieren (§5)."}, True)
    return None, True


def _hrv_double_red_defer(daily):
    """§5/§6: HRV heute <40 → CRITICAL-Pointer auf safety_gate (NICHT dupliziert)."""
    if not daily:
        return None, False
    avg = (daily.get("hrv_night") or {}).get("avg")
    if avg is None:
        return None, False
    if avg < HRV_CRITICAL:
        return ({"signal": "hrv_double_red", "level": "CRITICAL",
                 "detail": f"HRV {round(avg)} <{HRV_CRITICAL} ms = HRV🔴🔴-Territorium (§6). "
                           f"safety_gate.py ist AUTORITATIV für die Training-Streichen-Entscheidung "
                           f"(prüft +Schlaf<6h, setzt training_allowed) — Sentinel dupliziert das Gate "
                           f"nicht, sondern eskaliert dorthin."}, True)
    return None, True


def _rhr_elevation(health_rows):
    """§6 Recovery-Komposit: Ruhepuls an 2 jüngsten Tagen ≥ Baseline-Median + 5 → WARN."""
    rhr_by_day = {r["date"]: r["rhr"] for r in (health_rows or [])
                  if r.get("date") and r.get("rhr") is not None}
    days = sorted(rhr_by_day)
    # Baseline braucht Geschichte: ≥2 jüngste + ≥2 Baseline-Tage = ≥4 Tage.
    if len(days) < SUSTAINED_DAYS + 2:
        return None, False

    recent_days = days[-SUSTAINED_DAYS:]
    baseline_days = days[:-SUSTAINED_DAYS]
    baseline = statistics.median([rhr_by_day[d] for d in baseline_days])
    recent_vals = [rhr_by_day[d] for d in recent_days]
    if all(v >= baseline + RHR_OVER_BASELINE for v in recent_vals):
        shown = ", ".join(f"{d}={round(rhr_by_day[d])}" for d in recent_days)
        return ({"signal": "rhr_elevation", "level": "WARN",
                 "detail": f"Ruhepuls {SUSTAINED_DAYS} Tage ≥ Baseline+{RHR_OVER_BASELINE}: "
                           f"Trailing-Median {round(baseline, 1)} bpm, zuletzt {shown} "
                           f"→ Erholungs-/Last-Check (§6 Recovery-Komposit)."}, True)
    return None, True


def _weight_creep(daily, weight_rows, threshold, approach):
    """§1: Gewicht steigt Richtung metabolischer Schwelle (Wert aus athlete.md)."""
    series, src = [], None
    if weight_rows:
        series = [(r["date"], r["weight_kg"]) for r in weight_rows
                  if r.get("date") and r.get("weight_kg") is not None]
        series.sort()
        src = "weight_csv"
    if not series and daily:
        bc = (daily.get("body_comp") or {}).get("weight_body_mass")
        if bc and bc.get("value") is not None:
            series = [(bc.get("date") or daily.get("as_of") or "?", bc["value"])]
            src = "daily_body_comp" + (" (off-protocol, NICHT SoT)" if bc.get("off_protocol") else "")
    if not series:
        return None, False

    window = series[-5:]                       # letzte N Wiegungen
    latest = window[-1][1]
    net = latest - window[0][1]
    trending_up = len(window) >= 2 and net > 0
    trend_txt = f"{window[0][1]:.1f}→{latest:.1f} kg (+{net:.1f})"

    if threshold is not None:
        headroom = threshold - latest
        if latest >= threshold:
            return ({"signal": "weight_creep", "level": "WARN",
                     "detail": f"Gewicht {latest:.1f} kg ≥ metabolische Schwelle {threshold:.0f} kg "
                               f"(Quelle {src}) → Recomp-Hebel ziehen (§1)."}, True)
        if headroom <= approach:
            lvl = "WARN" if trending_up else "WATCH"
            mid = f"steigt ({trend_txt}) und " if trending_up else "liegt "
            return ({"signal": "weight_creep", "level": lvl,
                     "detail": f"Gewicht {mid}nur {headroom:.1f} kg unter der metabolischen "
                               f"Schwelle {threshold:.0f} kg (Quelle {src}) → gegensteuern (§1)."}, True)
        if trending_up:
            return ({"signal": "weight_creep", "level": "WATCH",
                     "detail": f"Gewicht steigt ({trend_txt}); noch {headroom:.1f} kg bis "
                               f"Schwelle {threshold:.0f} kg (Quelle {src}) — Trend, keine Eskalation."}, True)
        return None, True

    # ohne Schwelle: nur Trend-Hinweis, nie actionable
    if trending_up:
        return ({"signal": "weight_creep", "level": "WATCH",
                 "detail": f"Gewicht steigt ({trend_txt}, Quelle {src}); keine metabolische "
                           f"Schwelle übergeben (--weight-threshold-kg aus athlete.md) → nur Trend."}, True)
    return None, True


def _bedtime_drift(daily):
    """§8: Bedtime klar nach 00:30 → WARN (1-Tages-Read)."""
    if not daily:
        return None, False
    bt = (daily.get("heute_sleep") or {}).get("bedtime")
    if not bt:
        return None, False
    try:
        hh, mm = (int(x) for x in str(bt).split(":")[:2])
    except (ValueError, TypeError):
        return None, False
    if hh >= 18:        # Abend vor Mitternacht → im Ziel
        return None, True
    minutes_past = hh * 60 + mm
    if minutes_past > BEDTIME_TARGET_MIN:
        return ({"signal": "bedtime_drift", "level": "WARN",
                 "detail": f"Bedtime {bt} = {minutes_past} min nach Mitternacht, deutlich über "
                           f"Ziel 00:30 (§8). 1-Tages-Read — bei 2+ Tagen Muster (mehr Dailies geben)."}, True)
    return None, True


def _walking_asymmetry(daily):
    """§7: Gang-Asymmetrie-Flag (anhaltend >5 %) → WARN (Kontext, kein Befund)."""
    if not daily:
        return None, False
    asym = ((daily.get("load_extra") or {}).get("gait") or {}).get("asymmetry_pct")
    if not asym:
        return None, False
    if asym.get("flag"):
        return ({"signal": "walking_asymmetry", "level": "WARN",
                 "detail": f"Geh-Asymmetrie {asym.get('avg')} % erhöht (Flag, >5 % anhaltend) — "
                           f"Verletzungs-/Schonhaltungs-KONTEXT, vorsichtig, NIE als Befund framen (§7)."}, True)
    return None, True


def _breathing(daily):
    """§3c/§11: Atemstörungen >10/h → WARN (Medikation/Allergie prüfen)."""
    if not daily:
        return None, False
    bd = (daily.get("recovery") or {}).get("breathing_disturbances")
    if not bd or bd.get("value") is None:
        return None, False
    v = bd["value"]
    if v > BREATHING_MAX:
        return ({"signal": "breathing_disturbances", "level": "WARN",
                 "detail": f"Atemstörungen {round(v)}/h >{BREATHING_MAX} (§3c/§11) — "
                           f"Medikation/Allergie prüfen, CSV-Forensik anbieten."}, True)
    return None, True


# ================================================================ orchestrator (pure)
def evaluate(daily=None, health_rows=None, weight_rows=None,
             weight_threshold_kg=None, weight_approach_kg=WEIGHT_APPROACH_KG):
    """Reine Funktion: reduzierte Inputs → Alert-Dict. Keine I/O, leicht testbar.

    Robust gegen fehlende Inputs: jeder Trip-Wire wertet nur aus, was vorhanden ist,
    und meldet über das zweite Tuple-Element, ob er überhaupt geprüft werden konnte.
    """
    health_rows = health_rows or []
    results = [
        _hrv_sustained(daily, health_rows),
        _hrv_double_red_defer(daily),
        _rhr_elevation(health_rows),
        _weight_creep(daily, weight_rows, weight_threshold_kg, weight_approach_kg),
        _bedtime_drift(daily),
        _walking_asymmetry(daily),
        _breathing(daily),
    ]

    alerts, checked = [], []
    for name, (alert, was_checked) in zip(SIGNAL_ORDER, results):
        if was_checked:
            checked.append(name)
        if alert:
            alerts.append(alert)
    alerts.sort(key=lambda a: LEVEL_RANK.get(a["level"], 99))

    actionable = any(a["level"] in ACTIONABLE_LEVELS for a in alerts)
    out = {"alerts": alerts, "actionable": actionable, "checked": checked}
    if daily and daily.get("as_of"):
        out["as_of"] = daily["as_of"]
    return out


# ================================================================ CSV parsing (reduced)
def _norm(s):
    """Header-Normalisierung: Akzente weg, ₂→2 (NFKD), lower, Whitespace gestaucht."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.replace("₂", "2").lower().split())


DATE_ALIASES = ("datum", "date")
HRV_ALIASES = ("hfv", "hrv", "herzfrequenzvariabilitat", "heart rate variability")
RHR_ALIASES = ("ruheherzfrequenz", "ruhepuls", "resting heart rate", "rhr")
WEIGHT_ALIASES = ("gewicht", "weight", "korpergewicht", "korpermasse", "body mass")


def _find_col(headers, aliases):
    """Erste Spalte, deren normalisierter Header zu einem Alias passt (exakt > Substring)."""
    pairs = [(h, _norm(h)) for h in (headers or []) if h]
    for alias in aliases:
        for h, nh in pairs:
            if nh == alias:
                return h
    for alias in aliases:
        for h, nh in pairs:
            if alias in nh:
                return h
    return None


def _num(s):
    """Robuste Zahl: dt. Komma-Dezimal + Tausender-Punkt → float; sonst None."""
    if s is None:
        return None
    s = str(s).strip().replace(" ", "").replace("\xa0", "")
    if not s:
        return None
    if "," in s and "." in s:        # 1.234,5 → 1234.5
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                   # 55,3 → 55.3
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(s):
    """ISO (YYYY-MM-DD) oder dt. DD.MM.YYYY[YY] → ISO-String; sonst None (filtert Summen-Zeilen)."""
    if s is None:
        return None
    s = str(s).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", s)
    if m:
        dd, mm, yy = m.groups()
        yy = ("20" + yy) if len(yy) == 2 else yy
        return f"{yy}-{int(mm):02d}-{int(dd):02d}"
    return None


def read_health_csv(path):
    """Gesundheitsdaten 'Tägliche Kennzahlen' → [{date, hrv, rhr}] (1 Zeile/Tag, reduziert)."""
    rows = []
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        c_date = _find_col(headers, DATE_ALIASES)
        c_hrv = _find_col(headers, HRV_ALIASES)
        c_rhr = _find_col(headers, RHR_ALIASES)
        for r in reader:
            d = _parse_date(r.get(c_date)) if c_date else None
            if not d:
                continue
            rows.append({"date": d,
                         "hrv": _num(r.get(c_hrv)) if c_hrv else None,
                         "rhr": _num(r.get(c_rhr)) if c_rhr else None})
    return rows


def read_weight_csv(path):
    """Gesundheitsdaten 'Gewicht' → [{date, weight_kg}] (1 Wiegung/Tag, reduziert)."""
    rows = []
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        c_date = _find_col(headers, DATE_ALIASES)
        c_w = _find_col(headers, WEIGHT_ALIASES)
        for r in reader:
            d = _parse_date(r.get(c_date)) if c_date else None
            w = _num(r.get(c_w)) if c_w else None
            if d and w is not None:
                rows.append({"date": d, "weight_kg": w})
    return rows


# ================================================================ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Deterministischer V3-Trip-Wire-Evaluator (CLAUDE.md §5/§6). "
                    "Konsumiert NUR reduzierte Aggregate, nie Roh-Serien.")
    ap.add_argument("--health-csv", help="Gesundheitsdaten 'Tägliche Kennzahlen' CSV (HRV/RHR-Trend).")
    ap.add_argument("--daily", help="slice_hae_day-Ausgabe (Datei oder '-' für stdin).")
    ap.add_argument("--weight-csv", help="Gesundheitsdaten 'Gewicht' CSV (Gewichts-Trend).")
    ap.add_argument("--weight-threshold-kg", type=float, default=None,
                    help="Metabolische Schwelle aus athlete.md (sonst nur Trend).")
    ap.add_argument("--weight-approach-kg", type=float, default=WEIGHT_APPROACH_KG,
                    help=f"Annäherungs-Band an die Schwelle (Default {WEIGHT_APPROACH_KG} kg).")
    args = ap.parse_args(argv)

    daily = None
    if args.daily:
        raw = sys.stdin.read() if args.daily == "-" else open(args.daily, encoding="utf-8").read()
        daily = json.loads(raw)
    health_rows = read_health_csv(args.health_csv) if args.health_csv else []
    weight_rows = read_weight_csv(args.weight_csv) if args.weight_csv else None

    out = evaluate(daily=daily, health_rows=health_rows, weight_rows=weight_rows,
                   weight_threshold_kg=args.weight_threshold_kg,
                   weight_approach_kg=args.weight_approach_kg)
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
