#!/usr/bin/env python3
"""
slice_hae_day.py — Health-Auto-Export auf EINEN Zieltag slicen (daily-check §3f / §3f-bis).

Der #1-Daily-Check-Bug: ein Range-/Multi-Day-HAE-Export (Woche/Monat) wird ungesliced
verrechnet → jede Tages-Summe (Aktiv-Energie, Schritte, Distanz, Physical Effort) wird zur
WOCHEN-/MONATS-Summe und damit grob falsch. Dieses Script zieht aus EINEM oder ZWEI
Tages-/Range-JSONs deterministisch die Zieltag-Aggregate und gibt KOMPAKTES JSON aus.

Tages-Logik (WHOOP-Dashboard, HEUTE-zentriert):
  --as-of = HEUTE. GESTERN = as_of − 1 (der ausgewertete Trainings-/Load-Tag).
  • GESTERN-LOAD : active_energy / steps / distance / physical_effort / Tages- & Wach-HR
                   — JEDE Summe ZWINGEND auf `date == gestern` gefiltert (nie übers File summiert).
  • HEUTE-NACHT  : sleep_analysis per sleepEnd == as_of (NICHT sleepStart),
                   stündliche HRV-Tabelle NUR im Schlaffenster, plus RHR/HRR(cardio_recovery)/
                   VO2/Atmung/SpO2 wo vorhanden.

Robust gegen: (a) zwei Tagesdateien (today_json + yesterday_json), (b) EINE Range-/Monatsdatei
allein (today_json deckt den ganzen Zeitraum), (c) Stunden-Aggregat- UND Minuten-Roh-Shapes
(HR mit Min/Avg/Max, alles andere mit qty). Es werden NIE Roh-Minuten-Arrays ausgegeben —
nur die kleine stündliche HRV-Tabelle (auf Stunden gebucketet).

CLI:  python3 slice_hae_day.py <today_json> [<yesterday_json>] --as-of YYYY-MM-DD
"""
import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta


# ---------------------------------------------------------------- low-level helpers
def _load_metrics(path):
    """HAE-JSON → {name: [samples]}. Mehrere Dateien werden per merge() vereint."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    data = d.get("data", d)
    out = {}
    for m in data.get("metrics", []):
        out[m["name"]] = {"units": m.get("units"), "data": m.get("data", [])}
    return out


def _merge(*metric_maps):
    """Mehrere {name:{units,data}} vereinen; Duplikate per (name,date) dedupen."""
    merged = {}
    for mm in metric_maps:
        if not mm:
            continue
        for name, blk in mm.items():
            tgt = merged.setdefault(name, {"units": blk.get("units"), "data": [], "_seen": set()})
            if tgt["units"] is None:
                tgt["units"] = blk.get("units")
            for s in blk.get("data", []):
                key = s.get("date")
                if key in tgt["_seen"]:
                    continue
                tgt["_seen"].add(key)
                tgt["data"].append(s)
    for blk in merged.values():
        blk.pop("_seen", None)
        blk["data"].sort(key=lambda r: str(r.get("date", "")))
    return merged


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _day(s):
    return str(s)[:10]


def _hhmm(s):
    s = str(s)
    return s[11:16] if len(s) >= 16 else None


def _series(metrics, name):
    blk = metrics.get(name)
    return blk["data"] if blk else []


def _units(metrics, name):
    blk = metrics.get(name)
    return blk.get("units") if blk else None


def _val(rec, keys=("qty",)):
    for k in keys:
        v = _f(rec.get(k))
        if v is not None:
            return v
    return None


# ---------------------------------------------------------------- aggregation primitives
def _day_sum(metrics, name, target):
    """Tages-SUMME, ZWINGEND auf `date == target` gefiltert (kumulative Metriken)."""
    vals = [_val(r) for r in _series(metrics, name) if _day(r.get("date")) == target]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _day_stat(metrics, name, target):
    """avg + peak einer Metrik AM Zieltag (z. B. physical_effort)."""
    vals = [_val(r) for r in _series(metrics, name) if _day(r.get("date")) == target]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"avg": round(sum(vals) / len(vals), 2), "peak": round(max(vals), 2)}


def _day_avg(metrics, name, target):
    """Tages-MITTEL (nicht Summe) einer Metrik AM Zieltag (z. B. Gait-Prozente)."""
    vals = [_val(r) for r in _series(metrics, name) if _day(r.get("date")) == target]
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals)) if vals else None


def _latest_reading(metrics, name, on_or_before=None):
    """Letzte verfügbare Lesung (sporadische Metrik). Optional ≤ on_or_before."""
    pts = [(r.get("date"), _val(r)) for r in _series(metrics, name)]
    pts = [(d, v) for d, v in pts if v is not None and (on_or_before is None or _day(d) <= on_or_before)]
    if not pts:
        return None
    pts.sort(key=lambda p: str(p[0]))
    d, v = pts[-1]
    return {"value": round(v, 2), "date": _day(d)}


# ---------------------------------------------------------------- sleep
def _all_sleep_windows(metrics):
    out = []
    for r in _series(metrics, "sleep_analysis"):
        ss, se = r.get("sleepStart"), r.get("sleepEnd")
        if ss and se:
            out.append((str(ss), str(se)))
    return out


def _pick_sleep(metrics, as_of):
    """Schlaf-Record der HEUTE-Nacht = sleepEnd == as_of (NICHT sleepStart). Fallback: letzter Record."""
    recs = _series(metrics, "sleep_analysis")
    for r in recs:
        if _day(r.get("sleepEnd")) == as_of:
            return r, "sleepEnd==as_of"
    if recs:
        recs_sorted = sorted(recs, key=lambda r: str(r.get("sleepEnd", "")))
        return recs_sorted[-1], "fallback:last_record"
    return None, None


def _sleep_block(rec, attribution):
    if rec is None:
        return None
    total = _f(rec.get("totalSleep"))
    deep = _f(rec.get("deep"))
    core = _f(rec.get("core"))
    rem = _f(rec.get("rem"))
    awake = _f(rec.get("awake"))

    def pct(part):
        return round(100 * part / total, 1) if (part is not None and total) else None

    return {
        "attributed_by": attribution,          # IMMER sleepEnd-basiert (oder Fallback)
        "sleepStart": rec.get("sleepStart"),
        "sleepEnd": rec.get("sleepEnd"),
        "bedtime": _hhmm(rec.get("inBedStart") or rec.get("sleepStart")),
        "total_h": round(total, 2) if total is not None else None,
        "deep_h": round(deep, 2) if deep is not None else None,
        "deep_pct": pct(deep),
        "core_h": round(core, 2) if core is not None else None,
        "rem_h": round(rem, 2) if rem is not None else None,
        "rem_pct": pct(rem),
        "awake_h": round(awake, 2) if awake is not None else None,
    }


# ---------------------------------------------------------------- HR (gestern day)
def _hr_value(rec, prefer):
    return _val(rec, prefer)


def _gestern_heart(metrics, gestern, sleep_windows):
    samples = [r for r in _series(metrics, "heart_rate") if _day(r.get("date")) == gestern]
    if not samples:
        return None

    def in_sleep(dt):
        return any(ss <= str(dt) <= se for ss, se in sleep_windows)

    avgs = [(_hr_value(r, ("Avg", "qty")), r.get("date")) for r in samples]
    avgs = [(v, d) for v, d in avgs if v is not None]
    waking = [v for v, d in avgs if not in_sleep(d)]

    peak_rec = max(samples, key=lambda r: (_hr_value(r, ("Max", "qty", "Avg")) or -1))
    peak = _hr_value(peak_rec, ("Max", "qty", "Avg"))

    return {
        "day_avg": round(sum(v for v, _ in avgs) / len(avgs), 1) if avgs else None,
        "waking_avg": round(sum(waking) / len(waking), 1) if waking else None,
        "peak": round(peak, 1) if peak is not None else None,
        "peak_time": _hhmm(peak_rec.get("date")) if peak is not None else None,
        "n_samples": len(samples),
    }


# ---------------------------------------------------------------- HRV night table
def _hrv_ampel(v):
    if v >= 60:
        return "🟢"
    if v >= 50:
        return "🟡"
    return "🔴"


def _hrv_night(metrics, sleep_rec):
    """HRV-Nacht-Stats im Schlaffenster.

    B3: Volatilitäts-Kennzahlen (avg/min/max/range/std) kommen aus den ROHEN
    In-Window-HRV-Punkten — NICHT aus den Stunden-Mitteln (Stunden-Mittel glätten σ
    künstlich runter: Audit-Beweis raw σ 33.1 / range 117 vs hourly σ 20.9 / range 63;
    claude.ai rechnet roh, wir jetzt auch). Zusätzlich:
      • `hourly`  — die bestehende Stunden-Tabelle (§9-Anzeige, unverändert).
      • `fine`    — 15-Minuten-Feinserie (Key YYYY-MM-DD HH:Q, Q=minute//15);
                    klein gehalten (≤~36 Punkte/Nacht), nie Roh-Minuten-Arrays.
    """
    if sleep_rec is None:
        return None
    ss, se = str(sleep_rec.get("sleepStart")), str(sleep_rec.get("sleepEnd"))
    if not ss or not se:
        return None
    raw_vals = []                        # ROHE In-Window-Punkte → Volatilität
    hour_buckets = defaultdict(list)     # date[:13] (Tag+Stunde) → werte (Anzeige)
    fine_buckets = defaultdict(list)     # "YYYY-MM-DD HH:Q" (15-min) → werte
    for r in _series(metrics, "heart_rate_variability"):
        dt = str(r.get("date"))
        if ss <= dt <= se:
            v = _val(r)
            if v is not None:
                raw_vals.append(v)
                hour_buckets[dt[:13]].append(v)
                mm = dt[14:16]
                q = int(mm) // 15 if mm.isdigit() else 0
                fine_buckets[f"{dt[:10]} {dt[11:13]}:{q}"].append(v)
    if not raw_vals:
        return None
    hourly = []
    for bkey in sorted(hour_buckets):
        hv = sum(hour_buckets[bkey]) / len(hour_buckets[bkey])
        hourly.append({"t": bkey[11:13] + ":00", "hrv": round(hv), "ampel": _hrv_ampel(hv)})
    fine = []
    for fkey in sorted(fine_buckets):
        fv = sum(fine_buckets[fkey]) / len(fine_buckets[fkey])
        fine.append({"t": fkey, "hrv": round(fv), "ampel": _hrv_ampel(fv)})
    avg = sum(raw_vals) / len(raw_vals)
    return {
        "avg": round(avg),
        "min": round(min(raw_vals)),
        "max": round(max(raw_vals)),
        "range": round(max(raw_vals) - min(raw_vals)),
        "std": round(statistics.pstdev(raw_vals), 1) if len(raw_vals) > 1 else 0.0,
        "n": len(raw_vals),
        "ampel": _hrv_ampel(avg),
        "hourly": hourly,
        "fine": fine,
    }


# ---------------------------------------------------------------- body composition (B4)
def _body_comp(metrics, as_of):
    """Letzte Körper-Mess-Werte (≤ as_of) je Metrik mit Protokoll-Flag.

    off_protocol = Quelle ist NICHT die Protokoll-Körperwaage ODER gemessen nach 09:00
    (claude.ai flaggt das Withings-Spät-Wiegen; wir hatten es übersehen)."""
    out = {}
    for name in ("weight_body_mass", "body_fat_percentage", "lean_body_mass", "body_mass_index"):
        pts = [r for r in _series(metrics, name)
               if _val(r) is not None and _day(r.get("date")) <= as_of]
        if not pts:
            out[name] = None
            continue
        pts.sort(key=lambda r: str(r.get("date")))
        rec = pts[-1]
        src = rec.get("source") or ""
        t = _hhmm(rec.get("date"))
        off = (src.lower() != "körperwaage") or (t is not None and t > "09:00")
        out[name] = {
            "value": round(_val(rec), 2),
            "date": _day(rec.get("date")),
            "time": t,
            "source": src,
            "in_json": True,
            "off_protocol": off,
        }
    return out


# ---------------------------------------------------------------- load extras (C)
def _load_extra(metrics, gestern):
    """Zusätzliche Tages-Last-Signale (nur wenn vorhanden):
    Grundumsatz → echter TDEE, Bewegungs-Minuten, Etagen, Gang-Symmetrie/Doppelstand."""
    out = {}
    basal = _day_sum(metrics, "basal_energy_burned", gestern)
    active = _day_sum(metrics, "active_energy", gestern)
    if basal is not None:
        out["basal_energy_kcal"] = round(basal, 1)
        if active is not None:
            out["true_tdee_kcal"] = round(basal + active, 1)  # Grundumsatz + Aktiv
    ex = _day_sum(metrics, "apple_exercise_time", gestern)
    if ex is not None:
        out["exercise_min"] = round(ex)
    flights = _day_sum(metrics, "flights_climbed", gestern)
    if flights is not None:
        out["flights_climbed"] = round(flights)

    gait = {}
    asym = _day_avg(metrics, "walking_asymmetry_percentage", gestern)
    if asym is not None:
        # Gang-Asymmetrie: anhaltend >5 % gilt als auffällig (Verletzungs-/Schonhaltung).
        gait["asymmetry_pct"] = {"avg": round(asym, 1), "flag": asym > 5}
    dsupp = _day_avg(metrics, "walking_double_support_percentage", gestern)
    if dsupp is not None:
        # Doppelstand-Norm ~20–40 %; außerhalb = veränderte Gangmechanik.
        gait["double_support_pct"] = {"avg": round(dsupp, 1), "flag": (dsupp < 20 or dsupp > 40)}
    if gait:
        out["gait"] = gait
    return out or None


# ---------------------------------------------------------------- window stats (spo2 / breathing)
def _window_stat(metrics, name, sleep_rec):
    if sleep_rec is None:
        return None
    ss, se = str(sleep_rec.get("sleepStart")), str(sleep_rec.get("sleepEnd"))
    vals = [_val(r) for r in _series(metrics, name) if ss <= str(r.get("date")) <= se]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"night_avg": round(sum(vals) / len(vals), 1), "min": round(min(vals), 1), "n": len(vals)}


# ---------------------------------------------------------------- assembly
def slice_day(metrics, as_of):
    gestern = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
    sleep_windows = _all_sleep_windows(metrics)
    sleep_rec, attribution = _pick_sleep(metrics, as_of)

    dist_units = _units(metrics, "walking_running_distance")
    distance = _day_sum(metrics, "walking_running_distance", gestern)
    steps = _day_sum(metrics, "step_count", gestern)
    walking_hr = _latest_reading(metrics, "walking_heart_rate_average", on_or_before=gestern)

    warnings = []
    days_present = sorted({_day(r.get("date")) for r in _series(metrics, "heart_rate_variability")}
                          or {_day(r.get("date")) for r in _series(metrics, "active_energy")})
    if len(days_present) > 2:
        warnings.append(
            f"multi_day_range: {len(days_present)} Tage im File "
            f"({days_present[0]}…{days_present[-1]}) — Aggregate auf gestern={gestern} gefiltert.")
    if gestern not in days_present and _series(metrics, "active_energy"):
        warnings.append(f"no_gestern_data: kein {gestern} im File — Gestern-Load unvollständig.")
    if attribution and attribution.startswith("fallback"):
        warnings.append("sleep_fallback: kein sleepEnd==as_of — letzter Schlaf-Record genutzt.")

    return {
        "as_of": as_of,
        "gestern": gestern,
        "days_in_file": days_present,
        "gestern_load": {
            "active_energy_kcal": round(_day_sum(metrics, "active_energy", gestern) or 0, 1)
            if _day_sum(metrics, "active_energy", gestern) is not None else None,
            "steps": int(steps) if steps is not None else None,
            "distance": {"value": round(distance, 2), "units": dist_units or "km"}
            if distance is not None else None,
            "physical_effort": _day_stat(metrics, "physical_effort", gestern),
            "stand_hours": int(_day_sum(metrics, "apple_stand_hour", gestern))
            if _day_sum(metrics, "apple_stand_hour", gestern) is not None else None,
            "heart": _gestern_heart(metrics, gestern, sleep_windows),
            "walking_hr": walking_hr,
        },
        "load_extra": _load_extra(metrics, gestern),
        "body_comp": _body_comp(metrics, as_of),
        "heute_sleep": _sleep_block(sleep_rec, attribution),
        "hrv_night": _hrv_night(metrics, sleep_rec),
        "recovery": {
            "rhr": _latest_reading(metrics, "resting_heart_rate", on_or_before=as_of),
            "cardio_recovery_hrr": _latest_reading(metrics, "cardio_recovery"),
            "vo2_max": _latest_reading(metrics, "vo2_max"),
            "respiratory_rate": _window_stat(metrics, "respiratory_rate", sleep_rec),
            "breathing_disturbances": _latest_reading(metrics, "breathing_disturbances", on_or_before=as_of),
            "spo2": _window_stat(metrics, "blood_oxygen_saturation", sleep_rec),
        },
        "warnings": warnings,
    }


def main():
    ap = argparse.ArgumentParser(description="HAE auf einen Zieltag slicen (daily-check §3f/§3f-bis).")
    ap.add_argument("today_json", help="HEUTE-Datei ODER eine Range-/Monatsdatei, die den Zeitraum abdeckt.")
    ap.add_argument("yesterday_json", nargs="?", default=None, help="Optionale GESTERN-Tagesdatei (Mitternachts-Merge).")
    ap.add_argument("--as-of", required=True, help="HEUTE als YYYY-MM-DD. GESTERN = as_of − 1.")
    args = ap.parse_args()

    try:
        date.fromisoformat(args.as_of)
    except ValueError:
        print(json.dumps({"error": f"--as-of muss YYYY-MM-DD sein, war: {args.as_of!r}"}), file=sys.stderr)
        sys.exit(2)

    maps = [_load_metrics(args.today_json)]
    if args.yesterday_json:
        maps.append(_load_metrics(args.yesterday_json))
    metrics = _merge(*maps)

    print(json.dumps(slice_day(metrics, args.as_of), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
