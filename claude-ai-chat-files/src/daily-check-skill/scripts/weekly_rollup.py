#!/usr/bin/env python3
"""
weekly_rollup.py — Deterministische KW-Aggregation für den Payload (PR-6).

PROBLEM
-------
Der Payload-Block (payload-skill §2) brauchte bisher LLM-Kopfrechnen über die
Woche (4 Makro-Ampeln × 7 Tage, Bedtime-Score zweistufig, HRV-/Schlaf-Ø,
Δ vs Vor-KW) — genau die Sorte Rechnung, die zwischen Läufen driftet.

LÖSUNG
------
EIN Script rechnet die Wochen-Aggregate aus den schon lokal gezogenen Quellen:
  - HAE-Tagesdateien   ./data/HealthAutoExport-YYYY-MM-DD.json  (Makros, Schlaf, Bedtime)
  - readiness-history  ./data/readiness-history.csv             (HRV/TSB/Readiness/week_km, Vor-KW)
Progressiv: fehlende Tage werden als nicht-geloggt gezählt (ehrlich, nie 0
angenommen) und in `days_missing` gelistet — der Payload-Gap-Check (§0) sieht
sofort, WAS nachzuziehen ist. §0-Kernregel: nur Aggregate auf stdout.

Ampel-Schwellen: SSoT lib/constants.py (Protein-Floor-Bänder, Tagestyp-Caps,
Fett-Hard-Cap 85 g, Cap-Toleranzen ±10 %/+30 %, Bedtime zweistufig 00:00/00:30).

CLI:  python3 weekly_rollup.py --as-of {kw_sonntag} [--data-dir ./data]
          [--history ./data/readiness-history.csv]
"""

import argparse
import csv
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily_signals as DS  # noqa: E402  (Merge-/Makro-Helfer wiederverwenden)

SCHEMA_VERSION = "1.0"

# ── Schwellen (SSoT: lib/constants.py — consistency-gepinnt) ─────────────────
PROTEIN_FLOOR_G = 150      # 🟢 ≥150 · 🟡 135–149 · 🟠 105–134 · 🔴 <105
PROTEIN_YELLOW_MIN = 135
PROTEIN_ORANGE_MIN = 105
CAP_YELLOW_PCT = 10        # kcal/Carbs/Fett: 🟢 ≤Cap · 🟡 ≤+10 % · 🟠 ≤+30 % · 🔴 >+30 %
CAP_ORANGE_PCT = 30
FAT_HARD_CAP_G = 85        # absolutes 🔴-Gate zusätzlich zum Tagestyp-Cap
DAY_CAPS = {               # Wochentag → (kcal, carbs_g, fett_g); Protein-Floor gilt täglich
    "Mo": (2700, 377, 56), "Sa": (2700, 377, 56),
    "Di": (2000, 245, 36), "Fr": (2000, 245, 36), "So": (2000, 245, 36),
    "Mi": (2800, 411, 61),
    "Do": (2300, 302, 45),
}
BEDTIME_HALF_CUTOFF_MIN = 30   # 🟢 ≤00:00 (voll) · 🟡 ≤00:30 (halb) · ❌ danach
BEDTIME_HALF_WEIGHT = 0.5

WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _week_days(as_of):
    """ISO-Woche, die as_of enthält → [Mo … So] als date-Liste."""
    d = date.fromisoformat(as_of)
    monday = d - timedelta(days=d.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def _load_week(data_dir, days):
    """Vorhandene HAE-Tagesdateien der Woche (+Vortag des Montags für die
    Mo-Nacht) EINMAL mergen. → (merged_metrics, missing_days)."""
    load = [days[0] - timedelta(days=1)] + list(days)
    paths, missing = [], []
    for d in load:
        p = os.path.join(data_dir, f"HealthAutoExport-{d.isoformat()}.json")
        if os.path.exists(p):
            paths.append(p)
        elif d in days:
            missing.append(d.isoformat())
    if not paths:
        return {}, missing
    return DS._load(paths), missing


# ── Makro-Ampeln (4 × 7) ─────────────────────────────────────────────────────
def _protein_ampel(g):
    if g >= PROTEIN_FLOOR_G:
        return "🟢"
    if g >= PROTEIN_YELLOW_MIN:
        return "🟡"
    if g >= PROTEIN_ORANGE_MIN:
        return "🟠"
    return "🔴"


def _cap_ampel(value, cap):
    if value <= cap:
        return "🟢"
    if value <= cap * (1 + CAP_YELLOW_PCT / 100.0):
        return "🟡"
    if value <= cap * (1 + CAP_ORANGE_PCT / 100.0):
        return "🟠"
    return "🔴"


def macro_week(merged, days):
    """→ {per_day, counts, all_green_days, n_logged} — 4 Ampeln × geloggte Tage."""
    factor = DS._energy_factor(merged)
    sums = {k: DS._daily(merged, name, "sum")
            for k, (name, _f) in DS._DIETARY_FIELDS.items()}
    per_day, counts = [], {m: {"🟢": 0, "🟡": 0, "🟠": 0, "🔴": 0}
                           for m in ("protein", "kcal", "carbs", "fat")}
    all_green = 0
    n_logged = 0
    for d in days:
        key = d.isoformat()
        wd = WD[d.weekday()]
        prot = sums["protein_g"].get(key)
        kcal = sums["kcal"].get(key)
        carbs = sums["carbs_g"].get(key)
        fat = sums["fat_g"].get(key)
        if all(v is None for v in (prot, kcal, carbs, fat)):
            per_day.append({"day": key, "wd": wd, "logged": False})
            continue
        n_logged += 1
        kcal_v = round(kcal * factor, 0) if kcal is not None else None
        cap_kcal, cap_carbs, cap_fat = DAY_CAPS[wd]
        amp = {
            "protein": _protein_ampel(prot) if prot is not None else None,
            "kcal": _cap_ampel(kcal_v, cap_kcal) if kcal_v is not None else None,
            "carbs": _cap_ampel(carbs, cap_carbs) if carbs is not None else None,
            "fat": (("🔴" if fat > FAT_HARD_CAP_G else _cap_ampel(fat, cap_fat))
                    if fat is not None else None),
        }
        for m, a in amp.items():
            if a:
                counts[m][a] += 1
        if all(a == "🟢" for a in amp.values()):
            all_green += 1
        per_day.append({"day": key, "wd": wd, "logged": True,
                        "protein_g": round(prot, 1) if prot is not None else None,
                        "kcal": kcal_v, "carbs_g": round(carbs, 1) if carbs is not None else None,
                        "fat_g": round(fat, 1) if fat is not None else None,
                        "ampeln": amp})
    return {"per_day": per_day, "counts": counts,
            "all_green_days": all_green, "n_logged": n_logged}


# ── Bedtime zweistufig + Schlaf-Ø ────────────────────────────────────────────
def _bedtime_class(sleep_start):
    """sleepStart-Zeitstempel → 'full' (≤00:00) / 'half' (00:00–00:30) / 'miss'.
    Abend-Start (≥18:00) = vor Mitternacht = voll."""
    hhmm = str(sleep_start)[11:16]
    if not hhmm or ":" not in hhmm:
        return None
    if hhmm >= "18:00":
        return "full"
    if hhmm == "00:00":
        return "full"
    mins = int(hhmm[:2]) * 60 + int(hhmm[3:5])
    if mins <= BEDTIME_HALF_CUTOFF_MIN:
        return "half"
    return "miss"


def sleep_week(merged, days):
    """Nächte mit sleepEnd in der KW → Schlaf-Ø + zweistufiger Bedtime-Score."""
    m = merged.get("sleep_analysis") or {}
    daykeys = {d.isoformat() for d in days}
    nights = []
    for r in m.get("data", []):
        end_day = str(r.get("sleepEnd") or r.get("date", ""))[:10]
        if end_day in daykeys and DS._f(r.get("totalSleep")):
            nights.append(r)
    total = [DS._f(r.get("totalSleep")) for r in nights]
    n_full = n_half = n_miss = 0
    for r in nights:
        cls = _bedtime_class(r.get("sleepStart"))
        if cls == "full":
            n_full += 1
        elif cls == "half":
            n_half += 1
        elif cls == "miss":
            n_miss += 1
    score = n_full + BEDTIME_HALF_WEIGHT * n_half
    return {
        "n_nights": len(nights),
        "sleep_avg_h": round(sum(total) / len(total), 2) if total else None,
        "bedtime": {"full_le_0000": n_full, "half_le_0030": n_half, "miss": n_miss,
                    "score": round(score, 1), "score_str": f"{score:g}/7",
                    "rule": "🟢 ≤00:00 voll · 🟡 ≤00:30 halb · ❌ danach"},
    }


# ── readiness-history: KW-Ø + Δ vs Vor-KW ────────────────────────────────────
def _hist_rows(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def _week_stats(rows, days):
    keys = {d.isoformat() for d in days}
    sel = [r for r in rows if (r.get("date") or "") in keys]

    def avg(col):
        vals = [DS._f(r.get(col)) for r in sel]
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def last(col):
        vals = [(r.get("date"), DS._f(r.get(col))) for r in sel if DS._f(r.get(col)) is not None]
        return vals[-1][1] if vals else None

    return {"n_days": len(sel), "hrv_avg_ms": avg("hrv_ms"), "rhr_avg": avg("rhr"),
            "readiness_avg": avg("readiness_score"), "tsb_last": last("tsb"),
            "week_km_last": last("week_km"), "weight_last": last("weight"),
            "vo2_last": last("vo2")}


def history_trend(history_path, days):
    rows = _hist_rows(history_path)
    cur = _week_stats(rows, days)
    prev_days = [d - timedelta(days=7) for d in days]
    prev = _week_stats(rows, prev_days)

    def delta(key):
        a, b = cur.get(key), prev.get(key)
        return round(a - b, 1) if (a is not None and b is not None) else None

    return {"this_week": cur, "prev_week": prev,
            "delta": {"hrv_avg_ms": delta("hrv_avg_ms"), "rhr_avg": delta("rhr_avg"),
                      "readiness_avg": delta("readiness_avg"),
                      "weight": delta("weight_last"), "vo2": delta("vo2_last")}}


# ── Template-Zeilen (payload-skill §2 — vorgerendert, LLM übersetzt nur) ─────
def render_lines(macros, sleep, trend):
    c = macros["counts"]

    def line(m, label):
        return (f"- {label} 🟢{c[m]['🟢']}/🟡{c[m]['🟡']}/🟠{c[m]['🟠']}/🔴{c[m]['🔴']}"
                + (f"  (nur {macros['n_logged']}/7 Tage geloggt)" if macros["n_logged"] < 7 else ""))

    bt = sleep["bedtime"]
    lines = [
        line("protein", "Protein"), line("kcal", "Kalorien"),
        line("carbs", "Carbs"), line("fat", "Fett"),
        f"- Tages-Gesamt 🟢🟢🟢🟢: {macros['all_green_days']}/{macros['n_logged']}",
        (f"- Schlaf Ø: {sleep['sleep_avg_h']} h | Bedtime-Score: {bt['score_str']} "
         f"({bt['full_le_0000']}×🟢 ≤00:00 voll + {bt['half_le_0030']}×🟡 ≤00:30 halb)"
         if sleep["sleep_avg_h"] is not None else "- Schlaf: [?] (keine Nächte im Fenster gezogen)"),
    ]
    tw, dl = trend["this_week"], trend["delta"]
    if tw.get("hrv_avg_ms") is not None:
        d = dl.get("hrv_avg_ms")
        arrow = "→" if d is None or abs(d) < 1 else ("↑" if d > 0 else "↓")
        lines.append(f"- HRV Wochen-Ø: {tw['hrv_avg_ms']} ms | Trend vs Vor-KW: {arrow}"
                     + (f" ({d:+} ms)" if d is not None else ""))
    return lines


def main():
    ap = argparse.ArgumentParser(
        description="KW-Rollup für den Payload (Makro-Ampeln, Bedtime zweistufig, "
                    "HRV/Schlaf-Ø, Δ vs Vor-KW) — Aggregate-JSON auf stdout.")
    ap.add_argument("--as-of", required=True, dest="as_of", metavar="YYYY-MM-DD",
                    help="Tag in der Ziel-KW (typisch der KW-Sonntag).")
    ap.add_argument("--data-dir", default="./data", dest="data_dir")
    ap.add_argument("--history", default=None,
                    help="readiness-history.csv (Default: <data-dir>/readiness-history.csv)")
    args = ap.parse_args()

    try:
        days = _week_days(args.as_of)
    except ValueError:
        print(json.dumps({"ok": False, "error": f"--as-of muss YYYY-MM-DD sein, war {args.as_of!r}"}),
              file=sys.stdout)
        return 2

    history = args.history or os.path.join(args.data_dir, "readiness-history.csv")
    merged, missing = _load_week(args.data_dir, days)
    macros = macro_week(merged, days) if merged else {
        "per_day": [], "counts": None, "all_green_days": 0, "n_logged": 0}
    sleep = sleep_week(merged, days) if merged else {
        "n_nights": 0, "sleep_avg_h": None,
        "bedtime": {"full_le_0000": 0, "half_le_0030": 0, "miss": 0,
                    "score": 0.0, "score_str": "0/7",
                    "rule": "🟢 ≤00:00 voll · 🟡 ≤00:30 halb · ❌ danach"}}
    trend = history_trend(history, days)

    out = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "week": {"monday": days[0].isoformat(), "sunday": days[-1].isoformat(),
                 "iso_week": days[0].isocalendar()[1]},
        "days_missing_hae": missing,          # → Hol-Pflicht: NACHZIEHEN, nicht [?]
        "macros": macros,
        "sleep": sleep,
        "history": trend,
        "template_lines": (render_lines(macros, sleep, trend)
                           if macros["counts"] else None),
        "note": "Fehlende Tage in days_missing_hae erst ziehen (payload §0 Gap-Check) — "
                "dieses Rollup rechnet nur über real vorhandene Dateien.",
    }
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
