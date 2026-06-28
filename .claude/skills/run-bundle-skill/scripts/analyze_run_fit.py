#!/usr/bin/env python3
"""
analyze_run_fit.py — DIE FIT-Analyse-Engine des run-bundle-skill (v3.11).

ZWECK
-----
Der gebündelte `analyze_run.py` parst NUR HealthFit-CSV und rechnet ROHE
Mittelwerte (inkl. Gehen) — ihm fehlt der Walking-Filter v3.5. Dieses Script
ist der echte FIT-Pfad: es liest die Garmin-/HealthFit-`.fit`, wendet den
Kadenz-primären Walking-Filter v3.5 an und liefert ausschließlich AGGREGATE
(kompaktes JSON) auf stdout — NIE Roh-Record-Arrays (das würde den ganzen
Sinn der Pipeline brechen: nur Aggregate + Verdict dürfen in den Modell-Kontext).

PIPELINE-REGELN (autoritativ, hier hart verdrahtet)
---------------------------------------------------
- Kadenz = (cadence + fractional_cadence) * 2   (FIT-Kadenz ist Single-Foot!)
- enhanced_speed > speed ; enhanced_altitude > altitude  (Apple-Watch-FITs
  haben oft nur die nicht-enhanced Felder → graceful fallback)
- Walking-Filter v3.5: Walking = (spm < 140 UND spd < 2.0 m/s) GLEICHZEITIG;
  reiner Stillstand (spm == 0 UND spd < 0.5) wird SEPARAT ausgeschlossen.
- Running-only-Records sind der einzige gültige Form-Benchmark.
- HR-Zonen (V3, hart): Z1 <136 · Z2 136–147 · Z3 148–159 · Z4 160–171 · Z5 ≥172
- Hitze: Baseline 18 °C, +3.5 s/km je °C darüber.
- SPORT-GUARD: HAE-Bundles enthalten „Outdoor Radfahren"-Tracks.
  session.sport/sub_sport wird geprüft; ist es Radfahren (oder nicht Laufen),
  bricht das Script mit klarem JSON-Fehler + Exit-Code ≠ 0 ab.

CLI:  python3 analyze_run_fit.py <fit_path> --as-of YYYY-MM-DD
"""

import argparse
import json
import math
import sys

# ── V3-Konstanten ──────────────────────────────────────────────────────────
HR_Z2_CAP = 147            # Z2-Decke (bpm)
HEAT_BASELINE_C = 18.0     # Hitze-Baseline (°C)
HEAT_TAX_S_PER_C = 3.5     # Pace-Tax (s/km je °C über Baseline)
WALK_CAD = 140             # spm-Schwelle Walking
WALK_SPD = 2.0             # m/s-Schwelle Walking
STAND_SPD = 0.5            # m/s-Schwelle Stillstand
RUNNING_SPORTS = {"running"}   # sub_sport generic/trail/treadmill etc. sind ok


# ── kleine Helfer ───────────────────────────────────────────────────────────
def _msg_dict(msg):
    """fitparse-Message → {feldname: wert} (nur nicht-None)."""
    return {f.name: f.value for f in msg.fields if f.value is not None}


def _first(d, *keys):
    """Erster vorhandener (nicht-None) Wert aus mehreren Kandidat-Keys."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _num(v):
    """Robust nach float; None/unparsebar → None."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    n = len(xs)
    if n == 0:
        return None
    m = n // 2
    return xs[m] if n % 2 else (xs[m - 1] + xs[m]) / 2.0


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _r(x, nd=2):
    """Runden, None-safe."""
    return round(x, nd) if isinstance(x, (int, float)) else None


def _pace_str(sec_per_km):
    """Sekunden/km → 'M:SS/km'. None/0 → None."""
    if not sec_per_km or sec_per_km <= 0 or math.isinf(sec_per_km):
        return None
    total = int(round(sec_per_km))   # auf ganze Sekunden runden, dann zerlegen
    return f"{total // 60}:{total % 60:02d}/km"


def _pace_from_speed(spd_ms):
    """m/s → Sekunden/km."""
    if not spd_ms or spd_ms <= 0:
        return None
    return 1000.0 / spd_ms


def zone_of(hr):
    """V3-HR-Zone (hart, kein Aufrunden)."""
    if hr is None:
        return None
    if hr < 136:
        return "Z1"
    if hr <= 147:
        return "Z2"
    if hr <= 159:
        return "Z3"
    if hr <= 171:
        return "Z4"
    return "Z5"


def _fail(msg, **extra):
    """Klarer JSON-Fehler auf stdout + Exit ≠ 0."""
    out = {"ok": False, "error": msg}
    out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(2)


# ── Record-Extraktion ───────────────────────────────────────────────────────
def extract_records(fit):
    """
    FIT-records → schlanke Liste von Sample-Dicts (intern, NIE in den Output).
    Wendet Kadenz×2, enhanced_*-Fallback und den v3.5-Walking-Filter an.
    """
    recs = []
    have_enhanced_speed = False
    have_enhanced_alt = False
    last_dist = 0.0
    last_temp = None

    for msg in fit.get_messages("record"):
        d = _msg_dict(msg)

        cad = _num(d.get("cadence")) or 0.0
        frac = _num(d.get("fractional_cadence")) or 0.0
        spm = (cad + frac) * 2.0

        if "enhanced_speed" in d:
            have_enhanced_speed = True
        if "enhanced_altitude" in d:
            have_enhanced_alt = True
        spd = _num(_first(d, "enhanced_speed", "speed")) or 0.0
        alt = _num(_first(d, "enhanced_altitude", "altitude"))

        dist = _num(d.get("distance"))
        if dist is None:
            dist = last_dist
        else:
            last_dist = dist

        temp = _num(d.get("temperature"))
        if temp is None:
            temp = last_temp
        else:
            last_temp = temp

        # Walking-Filter v3.5 (Kadenz-primär, Speed-Bestätigung)
        is_stand = (spm == 0) and (spd < STAND_SPD)
        is_walk = (spm < WALK_CAD) and (spd < WALK_SPD) and not is_stand
        is_run = not is_walk and not is_stand

        recs.append({
            "ts": d.get("timestamp"),
            "hr": _num(d.get("heart_rate")),
            "spd": spd,
            "alt": alt,
            "dist": dist,
            "spm": spm,
            "power": _num(d.get("power")),
            "gct": _num(d.get("stance_time")),               # ms
            "vo": _num(d.get("vertical_oscillation")),       # mm
            "stride": _num(d.get("step_length")),            # mm
            "vr": _num(d.get("vertical_ratio")),             # %
            "temp": temp,
            "run": is_run,
            "walk": is_walk,
            "stand": is_stand,
        })

    apple_watch_fit = not (have_enhanced_speed or have_enhanced_alt)
    return recs, apple_watch_fit


def _dt(a, b):
    """Sekunden zwischen zwei Timestamps; robust gegen None."""
    if a is None or b is None:
        return None
    try:
        return (b - a).total_seconds()
    except Exception:
        return None


# ── Splits (per KM) ─────────────────────────────────────────────────────────
def km_splits(recs):
    buckets = {}
    for r in recs:
        if r["dist"] is None:
            continue
        km = int(r["dist"] // 1000)
        buckets.setdefault(km, []).append(r)

    out = []
    for km in sorted(buckets):
        b = buckets[km]
        run = [r for r in b if r["run"]]
        walk_pct = 100.0 * sum(1 for r in b if r["walk"]) / len(b) if b else None

        run_spd = _mean([r["spd"] for r in run])
        pace_run = _pace_from_speed(run_spd)

        d0, d1 = b[0]["dist"], b[-1]["dist"]
        t_elapsed = _dt(b[0]["ts"], b[-1]["ts"])
        dist_km = (d1 - d0) / 1000.0 if (d0 is not None and d1 is not None) else None
        pace_asrun = (t_elapsed / dist_km) if (t_elapsed and dist_km) else None

        hrs = [r["hr"] for r in b if r["hr"] is not None]
        hr_avg = _mean(hrs)

        # Höhen-Delta + Auf-/Abstieg innerhalb des KM
        asc = desc = 0.0
        alts = [r["alt"] for r in b if r["alt"] is not None]
        prev = None
        for a in alts:
            if prev is not None:
                dh = a - prev
                if dh > 0:
                    asc += dh
                else:
                    desc += -dh
            prev = a
        grade = None
        if len(alts) >= 2 and d1 != d0 and d0 is not None:
            grade = (alts[-1] - alts[0]) / (d1 - d0) * 100.0

        out.append({
            "km": km + 1,
            "pace_run_s": _r(pace_run, 1),
            "pace_run": _pace_str(pace_run),
            "pace_asrun": _pace_str(pace_asrun),
            "hr_avg": _r(hr_avg, 0),
            "hr_max": max(hrs) if hrs else None,
            "zone": zone_of(hr_avg),
            "cadence": _r(_mean([r["spm"] for r in run]), 0),
            "gct_ms": _r(_median([r["gct"] for r in run]), 0),
            "vo_mm": _r(_median([r["vo"] for r in run]), 1),
            "stride_mm": _r(_median([r["stride"] for r in run]), 0),
            "power_w": _r(_mean([r["power"] for r in run]), 0),
            "walk_pct": _r(walk_pct, 1),
            "ascent_m": _r(asc, 1),
            "descent_m": _r(desc, 1),
            "grade_pct": _r(grade, 1),
        })
    return out


# ── Splits (per Lap aus FIT lap-Messages) ───────────────────────────────────
def lap_splits(fit, recs):
    laps = []
    for msg in fit.get_messages("lap"):
        d = _msg_dict(msg)
        spd = _num(_first(d, "enhanced_avg_speed", "avg_speed"))
        dur = _num(_first(d, "total_timer_time", "total_elapsed_time"))
        dist = _num(d.get("total_distance"))
        cad = _num(d.get("avg_running_cadence")) or 0.0
        frac = _num(d.get("avg_fractional_cadence")) or 0.0
        laps.append({
            "trigger": d.get("lap_trigger"),
            "intensity": d.get("intensity"),
            "dist_m": _r(dist, 0),
            "time_s": _r(dur, 0),
            "pace_s": _pace_from_speed(spd),
            "hr_avg": _num(d.get("avg_heart_rate")),
            "hr_max": _num(d.get("max_heart_rate")),
            "cadence": _r((cad + frac) * 2.0, 0),
            "gct_ms": _r(_num(d.get("avg_stance_time")), 0),
            "_start": d.get("start_time"),
        })

    # Gehanteil pro Lap aus records (Zeitfenster-Zuordnung)
    bounds = [l["_start"] for l in laps]
    if laps and all(b is not None for b in bounds):
        for i, l in enumerate(laps):
            lo = bounds[i]
            hi = bounds[i + 1] if i + 1 < len(laps) else None
            win = [r for r in recs if r["ts"] is not None and r["ts"] >= lo
                   and (hi is None or r["ts"] < hi)]
            if win:
                l["walk_pct"] = _r(100.0 * sum(1 for r in win if r["walk"]) / len(win), 1)

    out = []
    for i, l in enumerate(laps):
        out.append({
            "lap": i + 1,
            "trigger": l["trigger"],
            "intensity": l["intensity"],
            "dist_m": l["dist_m"],
            "time_s": l["time_s"],
            "pace": _pace_str(l["pace_s"]),
            "hr_avg": _r(l["hr_avg"], 0),
            "hr_max": _r(l["hr_max"], 0),
            "zone": zone_of(l["hr_avg"]),
            "cadence": l["cadence"],
            "gct_ms": l["gct_ms"],
            "walk_pct": l.get("walk_pct"),
        })
    return out


# ── HR-Zonen-Verteilung (zeitgewichtet) ─────────────────────────────────────
def hr_zone_distribution(recs):
    secs = {"Z1": 0.0, "Z2": 0.0, "Z3": 0.0, "Z4": 0.0, "Z5": 0.0}
    for i, r in enumerate(recs):
        z = zone_of(r["hr"])
        if z is None:
            continue
        nxt = recs[i + 1]["ts"] if i + 1 < len(recs) else None
        dt = _dt(r["ts"], nxt)
        if dt is None or dt <= 0 or dt > 15:   # Lücken/Pausen clampen
            dt = 1.0
        secs[z] += dt
    total = sum(secs.values())
    dist = {z: _r(secs[z], 0) for z in secs}
    pct = {z: _r(100.0 * secs[z] / total, 1) if total else None for z in secs}
    return {
        "bounds": "Z1<136 Z2 136-147 Z3 148-159 Z4 160-171 Z5>=172",
        "seconds": dist,
        "pct": pct,
        "z4_z5_pct": _r((secs["Z4"] + secs["Z5"]) / total * 100, 1) if total else None,
    }


# ── Lauf-Form (running-only) ────────────────────────────────────────────────
def run_form(recs, session):
    run = [r for r in recs if r["run"]]
    vr_vals = [r["vr"] for r in run if r["vr"] is not None]
    if not vr_vals:   # VR aus VO/Stride record-gewichtet rekonstruieren
        vr_vals = [r["vo"] / r["stride"] * 100.0 for r in run
                   if r["vo"] is not None and r["stride"]]
    return {
        "cadence_spm": _r(_mean([r["spm"] for r in run]), 1),
        "gct_median_ms": _r(_median([r["gct"] for r in run]), 0),
        "vo_median_mm": _r(_median([r["vo"] for r in run]), 1),
        "stride_median_mm": _r(_median([r["stride"] for r in run]), 0),
        "vr_pct_record_weighted": _r(_mean(vr_vals), 1),
        "vr_pct_session": _r(_num(session.get("avg_vertical_ratio")), 1),
        "power_avg_w": _r(_mean([r["power"] for r in run]), 0),
        "n_run_samples": len(run),
        "method": "running-only (Walking-Filter v3.5); VR record-gewichtet",
    }


# ── Bestwerte mit KM-Position ───────────────────────────────────────────────
def best_values(recs):
    def km(r):
        return _r(r["dist"] / 1000.0, 2) if r["dist"] is not None else None

    def pick(key, want_max=True, predicate=None):
        cand = [r for r in recs if r[key] is not None
                and (predicate is None or predicate(r))]
        if not cand:
            return None
        r = max(cand, key=lambda x: x[key]) if want_max \
            else min(cand, key=lambda x: x[key])
        return r

    top_spd = pick("spd")
    max_hr = pick("hr")
    max_pw = pick("power")
    max_cad = pick("spm", predicate=lambda r: r["run"])
    max_str = pick("stride", predicate=lambda r: r["run"])
    min_gct = pick("gct", want_max=False, predicate=lambda r: r["run"] and r["gct"] > 0)

    out = {}
    if top_spd:
        out["top_speed"] = {"pace": _pace_str(_pace_from_speed(top_spd["spd"])),
                            "km": km(top_spd)}
    if max_hr:
        out["max_hr"] = {"bpm": _r(max_hr["hr"], 0), "km": km(max_hr)}
    if max_pw:
        out["max_power"] = {"w": _r(max_pw["power"], 0), "km": km(max_pw)}
    if max_cad:
        out["max_cadence"] = {"spm": _r(max_cad["spm"], 0), "km": km(max_cad)}
    if max_str:
        out["max_stride"] = {"mm": _r(max_str["stride"], 0), "km": km(max_str)}
    if min_gct:
        out["min_gct"] = {"ms": _r(min_gct["gct"], 0), "km": km(min_gct)}
    return out


# ── Letzte-60s-Sprint-Block (deterministisch, bewegte Zeit) ─────────────────
def last_60s_sprint(recs, run_avg_pace_s):
    moving = [r for r in recs if r["ts"] is not None and r["spd"] >= STAND_SPD]
    if not moving:
        return None
    end_ts = moving[-1]["ts"]
    win = [r for r in moving if _dt(r["ts"], end_ts) is not None
           and 0 <= _dt(r["ts"], end_ts) <= 60]
    if not win:
        return None
    spd = _mean([r["spd"] for r in win])
    run_win = [r for r in win if r["run"]]
    spd_run = _mean([r["spd"] for r in run_win]) if run_win else spd
    pace_run_s = _pace_from_speed(spd_run)
    hrs = [r["hr"] for r in win if r["hr"] is not None]
    delta = None
    if pace_run_s and run_avg_pace_s:
        delta = _r(pace_run_s - run_avg_pace_s, 1)   # negativ = schneller als Ø
    return {
        "window_s": _r(_dt(win[0]["ts"], end_ts), 0),
        "pace": _pace_str(_pace_from_speed(spd)),
        "pace_running_only": _pace_str(pace_run_s),
        "hr_avg": _r(_mean(hrs), 0),
        "hr_max": max(hrs) if hrs else None,
        "cadence": _r(_mean([r["spm"] for r in run_win or win]), 0),
        "vs_run_avg_pace_delta_s": delta,
    }


# ── Decoupling H1 vs H2 (running-only, EF = Speed/HR) ───────────────────────
def decoupling(recs):
    run = [r for r in recs if r["run"] and r["hr"] is not None and r["spd"] > 0]
    if len(run) < 10:
        return {"valid": False, "note": "zu wenige running-only-Samples für Decoupling"}
    mid = len(run) // 2
    h1, h2 = run[:mid], run[mid:]

    def ef(half):
        s = _mean([r["spd"] for r in half])
        h = _mean([r["hr"] for r in half])
        return (s / h) if (s and h) else None, s, h

    ef1, s1, hr1 = ef(h1)
    ef2, s2, hr2 = ef(h2)
    dec = ((ef1 - ef2) / ef1 * 100.0) if (ef1 and ef2) else None
    return {
        "method": "EF=Speed/HR, H1 vs H2, running-only",
        "decoupling_pct": _r(dec, 1),          # >0 = Cardiac-Drift
        "h1_pace": _pace_str(_pace_from_speed(s1)),
        "h2_pace": _pace_str(_pace_from_speed(s2)),
        "h1_hr": _r(hr1, 0),
        "h2_hr": _r(hr2, 0),
        "valid": True,
        "note": "valide nur bei Steady-State Long Run >=45min @ Z2 (sonst Diagnostik)",
    }


# ── Pace@Z2 (running-only, letzte 30 min, hitze-normalisiert) ───────────────
def pace_at_z2(recs, session):
    run = [r for r in recs if r["run"] and r["ts"] is not None]
    if not run:
        return {"note": "keine running-only-Samples für Pace@Z2"}
    end_ts = run[-1]["ts"]
    last30 = [r for r in run if _dt(r["ts"], end_ts) is not None
              and 0 <= _dt(r["ts"], end_ts) <= 1800
              and r["hr"] is not None and r["hr"] <= HR_Z2_CAP]
    window = "letzte 30 min, running-only, HR<=147"
    if not last30:   # Fallback: ganzer Lauf bei HR<=147
        last30 = [r for r in run if r["hr"] is not None and r["hr"] <= HR_Z2_CAP]
        window = "ganzer Lauf, running-only, HR<=147 (kein 30-min-Fenster mit Z2)"
    if not last30:
        return {"note": "kein HR<=147-Abschnitt — kein Z2-Lauf"}

    spd = _mean([r["spd"] for r in last30])
    raw_s = _pace_from_speed(spd)
    start_temp = _num(session.get("avg_temperature"))
    if start_temp is None:
        temps = [r["temp"] for r in recs if r["temp"] is not None]
        start_temp = temps[0] if temps else None
    norm_s = raw_s
    heat_tax = None
    if raw_s is not None and start_temp is not None:
        heat_tax = max(0.0, start_temp - HEAT_BASELINE_C) * HEAT_TAX_S_PER_C
        norm_s = raw_s - heat_tax
    return {
        "window": window,
        "pace_raw_running_only_s": _r(raw_s, 1),
        "pace_raw_running_only": _pace_str(raw_s),
        "pace_normalized_18c_s": _r(norm_s, 1),
        "pace_normalized_18c": _pace_str(norm_s),
        "start_temp_c": _r(start_temp, 1),
        "heat_tax_s_per_km": _r(heat_tax, 1),
        "hr_cap": HR_Z2_CAP,
        "n_samples": len(last30),
        "note": "Baseline = state/live.md; neue Baseline nur bei Z2 sauber, <=22C, Decoupling<8%",
    }


# ── Topografie (200m-Buckets, Auf+Abstieg) ──────────────────────────────────
def topography(recs):
    pts = [r for r in recs if r["dist"] is not None and r["alt"] is not None]
    if len(pts) < 2:
        return {"note": "keine Höhendaten"}

    # Gesamt-Auf/Abstieg aus aufeinanderfolgenden Höhen (kleines Rauschfilter)
    asc = desc = 0.0
    prev = None
    for r in pts:
        if prev is not None:
            dh = r["alt"] - prev
            if dh > 0.1:
                asc += dh
            elif dh < -0.1:
                desc += -dh
        prev = r["alt"]

    buckets = {}
    for r in pts:
        b = int(r["dist"] // 200)
        buckets.setdefault(b, []).append(r)

    bucket_rows = []
    notable = []
    for b in sorted(buckets):
        grp = buckets[b]
        dh = grp[-1]["alt"] - grp[0]["alt"]
        dd = grp[-1]["dist"] - grp[0]["dist"]
        grade = (dh / dd * 100.0) if dd else None
        row = {
            "km_start": _r(grp[0]["dist"] / 1000.0, 2),
            "delta_h_m": _r(dh, 1),
            "grade_pct": _r(grade, 1),
        }
        bucket_rows.append(row)
        if grade is not None and abs(grade) >= 2.0 and dd >= 150:
            notable.append(row)

    return {
        "ascent_m": _r(asc, 1),
        "descent_m": _r(desc, 1),
        "bucket_size_m": 200,
        "buckets": bucket_rows,
        "notable_buckets": notable,   # |Grade| >= 2% — 200m-Forensik-Trigger
    }


# ── Summary ─────────────────────────────────────────────────────────────────
def build_summary(recs, session, apple_watch_fit):
    run = [r for r in recs if r["run"]]
    walk = [r for r in recs if r["walk"]]
    stand = [r for r in recs if r["stand"]]
    n = len(recs) or 1

    dists = [r["dist"] for r in recs if r["dist"] is not None]
    total_dist = (max(dists) - min(dists)) if dists else None
    sess_dist = _num(session.get("total_distance"))
    distance_m = sess_dist if sess_dist else total_dist

    dur = _num(_first(session, "total_timer_time", "total_elapsed_time"))
    if dur is None:
        ts = [r["ts"] for r in recs if r["ts"] is not None]
        dur = _dt(ts[0], ts[-1]) if len(ts) >= 2 else None

    moving_s = 0.0
    for i, r in enumerate(recs):
        if r["spd"] >= STAND_SPD:
            nxt = recs[i + 1]["ts"] if i + 1 < len(recs) else None
            dt = _dt(r["ts"], nxt)
            if dt and 0 < dt <= 15:
                moving_s += dt

    run_spd = _mean([r["spd"] for r in run])
    all_spd = _mean([r["spd"] for r in recs if r["spd"] > 0])
    hrs = [r["hr"] for r in recs if r["hr"] is not None]

    start_ts = recs[0]["ts"] if recs else None
    return {
        "distance_km": _r(distance_m / 1000.0, 2) if distance_m else None,
        "duration_s": _r(dur, 0),
        "moving_time_s": _r(moving_s, 0),
        "pace_avg_asrun": _pace_str(_pace_from_speed(all_spd)),
        "pace_avg_running_only": _pace_str(_pace_from_speed(run_spd)),
        "hr_avg": _r(_mean(hrs), 0),
        "hr_max": max(hrs) if hrs else None,
        "cadence_avg_running_spm": _r(_mean([r["spm"] for r in run]), 1),
        "gct_avg_ms": _r(_median([r["gct"] for r in run]), 0),
        "vo_avg_mm": _r(_median([r["vo"] for r in run]), 1),
        "stride_avg_mm": _r(_median([r["stride"] for r in run]), 0),
        "power_avg_w": _r(_mean([r["power"] for r in run]), 0),
        "walk_pct": _r(100.0 * len(walk) / n, 1),
        "stand_pct": _r(100.0 * len(stand) / n, 1),
        "ascent_m": _r(_num(session.get("total_ascent")), 0),
        "descent_m": _r(_num(session.get("total_descent")), 0),
        "temp_c": _r(_num(session.get("avg_temperature")), 1),
        "calories": _r(_num(session.get("total_calories")), 0),
        "start_time_utc": str(start_ts) if start_ts else None,
        "apple_watch_fit": apple_watch_fit,
    }


# ── Sport-Guard ─────────────────────────────────────────────────────────────
def sport_guard(session):
    """Wirft JSON-Fehler + Exit, wenn der Track nicht Laufen ist (z.B. Radfahren)."""
    sport = session.get("sport")
    sub = session.get("sub_sport")
    sport_l = str(sport).lower() if sport is not None else None
    if sport_l is not None and sport_l not in RUNNING_SPORTS:
        _fail(
            f"Sport-Guard: Track ist '{sport}' (sub_sport='{sub}'), nicht Laufen — "
            f"keine Lauf-Analyse. Vermutlich ein Radfahr-Track im HAE-Bundle.",
            sport=sport_l, sub_sport=str(sub) if sub is not None else None,
        )
    return sport_l, (str(sub) if sub is not None else None)


# ── Main ────────────────────────────────────────────────────────────────────
def analyze(fit_path, as_of):
    try:
        from fitparse import FitFile
    except ImportError:
        _fail("fitparse nicht installiert — `pip install fitparse --break-system-packages`")

    try:
        fit = FitFile(fit_path)
        fit.parse()
    except Exception as e:
        _fail(f"FIT konnte nicht geparst werden: {e}", fit_path=fit_path)

    session = {}
    for msg in fit.get_messages("session"):
        session = _msg_dict(msg)
        break

    sport, sub_sport = sport_guard(session)

    recs, apple_watch_fit = extract_records(fit)
    if not recs:
        _fail("Keine record-Messages in der FIT — nichts zu analysieren.", fit_path=fit_path)

    summary = build_summary(recs, session, apple_watch_fit)
    run_avg_pace_s = None
    run_spd = _mean([r["spd"] for r in recs if r["run"]])
    if run_spd:
        run_avg_pace_s = _pace_from_speed(run_spd)

    workout_name = None
    for msg in fit.get_messages("workout"):
        workout_name = _msg_dict(msg).get("wkt_name")
        break

    return {
        "ok": True,
        "meta": {
            "fit_path": fit_path,
            "as_of": as_of,
            "sport": sport,
            "sub_sport": sub_sport,
            "workout_name": workout_name,
            "apple_watch_fit": apple_watch_fit,
            "record_count": len(recs),
            "walking_filter": "v3.5 (cad<140 & spd<2.0; stand=cad0&spd<0.5 separat)",
            "parser": "fitparse",
            "skill": "run-bundle-skill v3.11",
        },
        "summary": summary,
        "splits_km": km_splits(recs),
        "splits_lap": lap_splits(fit, recs),
        "hr_zones": hr_zone_distribution(recs),
        "run_form": run_form(recs, session),
        "best_values": best_values(recs),
        "sprint_last_60s": last_60s_sprint(recs, run_avg_pace_s),
        "decoupling": decoupling(recs),
        "pace_at_z2": pace_at_z2(recs, session),
        "topography": topography(recs),
    }


def main():
    ap = argparse.ArgumentParser(
        description="FIT-Lauf-Analyse (run-bundle-skill v3.11) — Aggregate-JSON auf stdout.")
    ap.add_argument("fit_path", help="Pfad zur .fit-Datei")
    ap.add_argument("--as-of", required=True, metavar="YYYY-MM-DD",
                    help="Bezugsdatum (heute), z.B. 2026-06-28")
    args = ap.parse_args()

    result = analyze(args.fit_path, args.as_of)
    # Kompaktes JSON (Aggregate-only — NIE Roh-Records)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
