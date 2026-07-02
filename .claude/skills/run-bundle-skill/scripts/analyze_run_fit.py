#!/usr/bin/env python3
"""
analyze_run_fit.py — DIE FIT-Analyse-Engine des run-bundle-skill (v3.14).

ZWECK
-----
Der FIT-Pfad der Lauf-Analyse: liest die Garmin-/HealthFit-`.fit`, wendet den
Kadenz-primären Walking-Filter v3.5 an und liefert ausschließlich AGGREGATE
(kompaktes JSON) auf stdout — NIE Roh-Record-Arrays (das würde den ganzen
Sinn der Pipeline brechen: nur Aggregate + Verdict dürfen in den Modell-Kontext).
Die Aggregations-Funktionen hier sind die GETEILTE Engine — `analyze_run.py`
(CSV-Fallback) parst nur anders und ruft dieselben Funktionen auf.

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

# Steady-Z2-Segment-Detektion (Pace@Z2 + Decoupling): ein harter Schluss-Surge
# (Beast-Finish) darf den Easy-Pace-Benchmark NICHT verfälschen. „Hart" = Z4/Z5,
# d.h. Ø-Lauf-HR über der Z3-Decke; substanziell = genug Lauf-Samples (kein
# Mini-Rest-Lap des Auto-Splitters).
HARD_HR_CAP = 159              # > 159 == Z4/Z5 (Schluss-Surge / Beast-KM)
MIN_HARD_RUN_SAMPLES = 60      # Mindest-Lauf-Samples, damit ein Lap als Surge zählt
# Einheit = SAMPLES (bei 1-Hz-Records ≈ Sekunden; Apple-FITs können unregelmäßig
# samplen — die Schwellen sind bewusst Sample-basiert, nicht Zeit-basiert).
TRAIL_SOFT_GAP_N = 15          # Samples ohne Z4/Z5 → Sample-Surge gilt als beendet
MIN_TRAIL_BLOCK_N = 30         # Mindest-Sample-Länge eines Schluss-Surges

# §11-Ampel-Bänder (SSoT: lib/constants.py + run-bundle-skill §11 — Werte werden
# von tests/test_threshold_consistency.py gegen die Registry gepinnt).
CADENCE_AMPEL = (175, 166, 160)     # 🟢 ≥175 · 🟡 166–174 · 🟠 160–165 · 🔴 <160
GCT_AMPEL_MS = (260, 280, 300)      # 🟢 <260 · 🟡 260–280 · 🟠 280–300 · 🔴 >300
VR_AMPEL_PCT = (8.0, 10.0, 12.0)    # 🟢 <8 · 🟡 8–10 · 🟠 10–12 · 🔴 >12
EF_AMPEL = (1.75, 1.55, 1.40)       # 🟢🟢 >1,75 · 🟢 1,55–1,75 · 🟠 1,40–1,55 · 🔴 <1,40
DECOUPLING_AMPEL_PCT = (5.0, 7.0, 10.0)  # 🟢 <5 · 🟡 5–7 · 🟠 7–10 · 🔴 >10
EASY_HR_YELLOW_MAX = 155            # Easy: 🟢 Ø≤147 · 🟡 148–155 · 🔴 >155


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

        # Kadenz-ABSENZ ≠ 0 spm: fehlt das cadence-Feld ganz (Sensor-Dropout /
        # Gerät ohne Kadenz), wäre „0 spm" eine Walking-Fehlklassifikation
        # (NEVER-Regel: Gehen NIE aus Signal-Absenz ableiten, §4). spm bleibt
        # dann None und der Gangart-Filter fällt auf Speed-only zurück.
        cad = _num(d.get("cadence"))
        frac = _num(d.get("fractional_cadence")) or 0.0
        spm = (cad + frac) * 2.0 if cad is not None else None

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

        # Walking-Filter v3.5 (Kadenz-primär, Speed-Bestätigung).
        # Ohne Kadenz-Signal (spm is None): Speed-only-Fallback statt 0-spm-Lüge.
        if spm is None:
            is_stand = spd < STAND_SPD
            is_walk = (spd < WALK_SPD) and not is_stand
        else:
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


# ── Vertical Ratio (%) für ein running-only-Set ─────────────────────────────
def _vr_pct(run):
    """VR (%) für ein running-only-Sample-Set.
    Native vertical_ratio bevorzugt (Median). Fehlt sie (Apple-Watch-FITs liefern
    keine native VR), Rekonstruktion als VERHÄLTNIS DER MEDIANE
    (median(VO) ÷ median(Stride) · 100) — so reconciled der Wert mit den im selben
    Split gezeigten vo_mm/stride_mm (ratio-of-medians, nicht median-of-ratios).
    None, wenn nichts ableitbar."""
    vals = [r["vr"] for r in run if r.get("vr") is not None]
    if vals:
        return _median(vals)
    vo = _median([r["vo"] for r in run if r.get("vo") is not None])
    st = _median([r["stride"] for r in run if r.get("stride")])
    return vo / st * 100.0 if (vo is not None and st) else None


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
        seg_dist = (d1 - d0) if (d0 is not None and d1 is not None) else 0.0
        # Partieller Schluss-KM (<300 m Daten) → Grade aus GPS-End-Glitch unterdrücken (Fix v3.13)
        if len(alts) >= 2 and seg_dist >= 300.0:
            grade = (alts[-1] - alts[0]) / seg_dist * 100.0

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
            "vr_pct": _r(_vr_pct(run), 1),
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
            "vr_pct": _r(_num(d.get("avg_vertical_ratio")), 1),   # nativ (Garmin); Apple → None → unten rekonstruiert
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
                if l.get("vr_pct") is None:   # keine native Lap-VR (Apple) → aus Record-Fenster rekonstruieren
                    l["vr_pct"] = _r(_vr_pct([r for r in win if r["run"]]), 1)

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
            "vr_pct": l.get("vr_pct"),
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


# ── Optischer HR-Cadence-Lock-Detektor (T3) ─────────────────────────────────
LOCK_TOL_BPM = 6.0          # |HR − spm/2| ≤ 6 bpm ≈ optischer Lock auf die Kadenz
LOCK_MIN_SAMPLES = 60       # mind. so viele running-HR-Samples für ein Urteil
LOCK_MIN_SUSTAIN_S = 120    # ≥2 min zusammenhängend gelockt → Verdacht
LOCK_MIN_FRACTION = 0.50    # oder ≥50 % der Strecke gelockt


def hr_source_warn(recs):
    """Heuristik: rastet der optische HR-Sensor auf die Kadenz (HR ≈ spm/2)?
    Der klassische Apple-Watch-Optical-Lock-Artefakt bei harten Intervallen.
    Vergleicht HR mit spm/2 über die running-only-Samples und liefert ein
    AGGREGAT (nie die Roh-Serie). Ohne Brustgurt bleibt die Sensor-Wand offen —
    dieser Flag warnt, statt der Intervall-HR blind zu vertrauen.
    """
    run = [r for r in recs if r["run"] and r["hr"] is not None and r["spm"]]
    n = len(run)
    if n < LOCK_MIN_SAMPLES:
        return {"optical_cadence_lock_suspected": False, "n_compared": n,
                "note": "zu wenige running-only-HR-Samples für ein Urteil"}

    # Lock auf die Kadenz-Grundfrequenz (HR ≈ spm, „liest zu hoch") ODER die
    # halbe Harmonische (HR ≈ spm/2) — beide sind dokumentierte Optical-Artefakte.
    locked = [min(abs(r["hr"] - r["spm"]), abs(r["hr"] - r["spm"] / 2.0)) <= LOCK_TOL_BPM
              for r in run]
    locked_n = sum(locked)
    locked_frac = locked_n / n

    # längste zusammenhängende gelockte Strecke in Sekunden (ts-Differenz, geclamped)
    longest = cur = 0.0
    prev_ts = None
    prev_lock = False
    for r, is_lock in zip(run, locked):
        if is_lock and prev_lock:
            dt = _dt(prev_ts, r["ts"])
            if dt is None or dt <= 0 or dt > 15:
                cur = 0.0   # echte Aufzeichnungs-Lücke (>15s) = Bruch der Strecke, kein 1s-Füller
            else:
                cur += dt
                longest = max(longest, cur)
        else:
            cur = 0.0
        prev_ts, prev_lock = r["ts"], is_lock

    suspected = (longest >= LOCK_MIN_SUSTAIN_S) or (locked_frac >= LOCK_MIN_FRACTION)
    return {
        "optical_cadence_lock_suspected": suspected,
        "longest_locked_stretch_s": _r(longest, 0),
        "locked_fraction_pct": _r(100.0 * locked_frac, 1),
        "n_compared": n,
        "note": ("HR rastet streckenweise auf die Kadenz — Intervall-HR ohne "
                 "Brustgurt unzuverlässig (Sensor-Wand offen)"
                 if suspected else "kein anhaltender optischer Cadence-Lock erkannt"),
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
def _smoothed_top_speed(recs):
    """Top-Speed GPS-Spike-geschützt: Maximum des 3-Sample-MEDIANS statt des
    Einzel-Sample-Maximums (ein einzelner GPS-Glitch kann sonst eine absurde
    2:xx-Pace als „Bestwert" produzieren). Nur running-Samples als Zentrum."""
    spds = [r["spd"] for r in recs]
    best, best_rec = None, None
    for i, r in enumerate(recs):
        if not r["run"] or not r["spd"]:
            continue
        window = [s for s in spds[max(0, i - 1):i + 2] if s]
        if len(window) < 2:      # Rand-Sample ohne Nachbarn → kein Spike-Schutz möglich
            continue
        m = _median(window)
        if m and (best is None or m > best):
            best, best_rec = m, r
    return best, best_rec


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

    top_spd_v, top_spd_rec = _smoothed_top_speed(recs)
    max_hr = pick("hr")
    max_pw = pick("power")
    max_cad = pick("spm", predicate=lambda r: r["run"])
    max_str = pick("stride", predicate=lambda r: r["run"])
    min_gct = pick("gct", want_max=False, predicate=lambda r: r["run"] and r["gct"] > 0)

    out = {}
    if top_spd_rec:
        out["top_speed"] = {"pace": _pace_str(_pace_from_speed(top_spd_v)),
                            "km": km(top_spd_rec),
                            "method": "3-Sample-Median, running-only (GPS-Spike-Schutz)"}
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


# ── Steady-Z2-Segment (Surge-frei) ──────────────────────────────────────────
def lap_run_segments(fit, recs):
    """
    Pro Lap: running-only-Records + Ø-Lauf-HR (zeit-fenster-zugeordnet).
    Leere Liste, wenn keine (vollständigen) Lap-start_times vorliegen.
    """
    starts = [_msg_dict(m).get("start_time") for m in fit.get_messages("lap")]
    if not starts or any(s is None for s in starts):
        return []
    segs = []
    for i, lo in enumerate(starts):
        hi = starts[i + 1] if i + 1 < len(starts) else None
        win = [r for r in recs if r["ts"] is not None and r["ts"] >= lo
               and (hi is None or r["ts"] < hi)]
        run = [r for r in win if r["run"]]
        hrs = [r["hr"] for r in run if r["hr"] is not None]
        segs.append({"run": run, "mean_hr": _mean(hrs), "n_run": len(run)})
    return segs


def _drop_trailing_hard_block(run):
    """
    Sample-Level-Fallback (kein Lap-Struktur): den finalen zusammenhängenden
    Z4/Z5-Block (Beast-Finish) abschneiden, damit der Easy-Pace nicht durch
    einen harten Schluss-KM korrumpiert wird. Gibt (getrimmte_run_records,
    block_len) zurück; block_len==0 ⇒ kein Surge erkannt.
    Zähl-Einheit = SAMPLES (siehe TRAIL_SOFT_GAP_N — bei 1-Hz-Records ≈ s).
    """
    n = len(run)
    cut = n
    soft = 0
    i = n - 1
    while i >= 0:
        hr = run[i]["hr"]
        hard = hr is not None and hr > HARD_HR_CAP
        if hard:
            cut = i
            soft = 0
        else:
            soft += 1
            if soft >= TRAIL_SOFT_GAP_N:
                break
        i -= 1
    block_len = n - cut
    if 0 < cut < n and block_len >= MIN_TRAIL_BLOCK_N:
        return run[:cut], block_len
    return run, 0


def steady_z2_segment(recs, fit):
    """
    Running-only-Records des STEADY-Z2-Abschnitts für Pace@Z2 + Decoupling.

    Ein harter Schluss-Surge (Beast-Finish) darf den Easy-Pace-Benchmark NICHT
    verfälschen. Strategie:
      1. Lap-managed: liegt eine klare Lap-Struktur vor (managed-Z2-Lap(s) +
         abschließende(r) HARTE(r) Lap(s) in Z4/Z5), nimm nur die managed Laps.
      2. Sample-Fallback (keine Lap-Struktur / kein Drop): längster steady
         Lauf-Abschnitt = ganzer Lauf MINUS finalem Z4/Z5-Block.
    Gibt (segment_run_records, label) zurück.
    """
    laps = lap_run_segments(fit, recs)
    if laps:
        keep = list(laps)
        dropped = 0
        while len(keep) > 1:
            last = keep[-1]
            if (last["mean_hr"] is not None and last["mean_hr"] > HARD_HR_CAP
                    and last["n_run"] >= MIN_HARD_RUN_SAMPLES):
                keep.pop()
                dropped += 1
            else:
                break
        if dropped:
            seg = [r for s in keep for r in s["run"]]
            return seg, (f"managed Z2-Lap(s), running-only "
                         f"(ohne {dropped} harte(n) Schluss-Lap(s) Z4/Z5)")

    run = [r for r in recs if r["run"]]
    trimmed, blk = _drop_trailing_hard_block(run)
    if blk:
        return trimmed, (f"längster steady Lauf-Abschnitt, running-only "
                         f"(ohne {blk}-Sample-Schluss-Surge Z4/Z5)")
    return run, "ganzer Lauf, running-only (kein harter Schluss-Surge erkannt)"


# ── Decoupling H1 vs H2 (steady Z2-Segment, EF = Speed/HR) ───────────────────
def decoupling(seg_run, label=None):
    """H1-vs-H2-Cardiac-Drift über das STEADY-Z2-Segment (nicht den ganzen Lauf,
    sonst flacht ein Beast-Finish den Drift ein)."""
    run = [r for r in seg_run if r["hr"] is not None and r["spd"] > 0]
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
        "method": "EF=Speed/HR, H1 vs H2, steady Z2-Segment running-only",
        "segment": label,
        "decoupling_pct": _r(dec, 1),          # >0 = Cardiac-Drift
        "h1_pace": _pace_str(_pace_from_speed(s1)),
        "h2_pace": _pace_str(_pace_from_speed(s2)),
        "h1_hr": _r(hr1, 0),
        "h2_hr": _r(hr2, 0),
        "valid": True,
        "note": "valide nur bei Steady-State Long Run >=45min @ Z2 (sonst Diagnostik)",
    }


# ── Pace@Z2 (steady Z2-Segment, HR<=147, hitze-normalisiert) ────────────────
def pace_at_z2(seg_run, session, recs=None, label=None,
               decoupling_pct=None, walk_pct=None, z4z5_pct=None):
    """
    Ø-Pace bei HR<=147 über das STEADY-Z2-Segment (Surge-frei), normalisiert
    auf 18 °C (3.5 s/km/°C). Das Fenster ist NICHT „letzte 30 min" — ein harter
    Schluss-KM darf den Easy-Pace-Benchmark nicht verfälschen.
    """
    # Race/Parkrun (Z4+Z5-dominant): es gibt keinen echten Z2-Abschnitt — eine
    # Pace@Z2 aus den paar Warmup-Samples <=147 wäre Unsinn → unterdrücken (Fix v3.13).
    if z4z5_pct is not None and z4z5_pct > 50.0:
        return {"note": f"Race-Effort (Z4+Z5 {z4z5_pct:.0f}% > 50%) — kein Z2-Lauf, Pace@Z2 N/A",
                "race_effort": True, "baseline_eligible": False}
    z2 = [r for r in seg_run if r["hr"] is not None and r["hr"] <= HR_Z2_CAP]
    window = label or "steady Z2-Segment, running-only, HR<=147"
    if not z2:   # Fallback: ganzes Segment running-only (kein HR<=147 darin)
        z2 = [r for r in seg_run if r["spd"] and r["spd"] > 0]
        window = (label or "steady Z2-Segment") + " (kein HR<=147 — ganzes Segment)"
    if not z2:
        return {"note": "kein HR<=147-Abschnitt — kein Z2-Lauf"}

    spd = _mean([r["spd"] for r in z2])
    raw_s = _pace_from_speed(spd)
    # START-Temp = erste echte Temperatur-Lesung der Records (das Label sagt
    # „Starttemp", also muss es auch die sein) — session.avg_temperature ist der
    # LAUF-DURCHSCHNITT und nur der klar gelabelte Fallback (Audit-CONFIRMED:
    # vorher lief die Hitze-Norm auf avg unter dem Label „start_temp_c").
    start_temp, temp_source = None, None
    if recs:
        temps = [r["temp"] for r in recs if r["temp"] is not None]
        if temps:
            start_temp, temp_source = temps[0], "records_start"
    if start_temp is None:
        start_temp = _num(session.get("avg_temperature"))
        temp_source = "session_avg" if start_temp is not None else None
    norm_s = raw_s
    heat_tax = None
    if raw_s is not None and start_temp is not None:
        heat_tax = max(0.0, start_temp - HEAT_BASELINE_C) * HEAT_TAX_S_PER_C
        norm_s = raw_s - heat_tax

    # Gating: neue Baseline nur bei sauberem Z2 (<=22 °C, Gehen<=5%, Decoupling<8%)
    reasons = []
    if start_temp is not None and start_temp > 22.0:
        reasons.append(f"temp {start_temp:.0f}C>22")
    if walk_pct is not None and walk_pct > 5.0:
        reasons.append(f"walk {walk_pct:.1f}%>5%")
    if decoupling_pct is not None and decoupling_pct >= 8.0:
        reasons.append(f"decoupling {decoupling_pct:.1f}%>=8%")
    baseline_eligible = (not reasons) and (start_temp is not None
                                           and decoupling_pct is not None)

    return {
        "window": window,
        "pace_raw_running_only_s": _r(raw_s, 1),
        "pace_raw_running_only": _pace_str(raw_s),
        "pace_normalized_18c_s": _r(norm_s, 1),
        "pace_normalized_18c": _pace_str(norm_s),
        "start_temp_c": _r(start_temp, 1),
        "temp_source": temp_source,
        "heat_tax_s_per_km": _r(heat_tax, 1),
        "hr_cap": HR_Z2_CAP,
        "n_samples": len(z2),
        "baseline_eligible": baseline_eligible,
        "ineligible_reasons": reasons or None,
        "note": "Baseline = state/live.md; neue Baseline nur bei Z2 sauber, <=22C, Gehen<=5%, Decoupling<8%",
    }


# ── §11-Ampeln + EF (engine-seitig — der Report ÜBERSETZT nur noch) ─────────
def _band_desc(v, hi, mid, lo, colors=("🟢", "🟡", "🟠", "🔴")):
    """Absteigende Schwellen (größer = besser): v≥hi → colors[0] … v<lo → colors[3]."""
    if v is None:
        return None
    if v >= hi:
        return colors[0]
    if v >= mid:
        return colors[1]
    if v >= lo:
        return colors[2]
    return colors[3]


def _band_asc(v, lo, mid, hi, colors=("🟢", "🟡", "🟠", "🔴")):
    """Aufsteigende Schwellen (kleiner = besser): v<lo → colors[0] … v>hi → colors[3]."""
    if v is None:
        return None
    if v < lo:
        return colors[0]
    if v <= mid:
        return colors[1]
    if v <= hi:
        return colors[2]
    return colors[3]


def v3_ampeln(summary, form, dec, seg_run, race_effort):
    """§11-Ampel-Urteile deterministisch aus der Engine — {value, ampel[, note]}
    pro Metrik. Der LLM-Report übersetzt die Ampeln in Persona-Text, er rechnet
    sie NICht nach (Verdict-Kontrakt, Entscheidung #2)."""
    out = {}

    cad = form.get("cadence_spm")
    c_hi, c_mid, c_lo = CADENCE_AMPEL
    out["cadence"] = {"value": cad, "ampel": _band_desc(cad, c_hi, c_mid, c_lo)}

    gct = form.get("gct_median_ms")
    g_lo, g_mid, g_hi = GCT_AMPEL_MS
    out["gct"] = {"value": gct, "ampel": _band_asc(gct, g_lo, g_mid, g_hi)}

    vr = form.get("vr_pct_record_weighted")
    v_lo, v_mid, v_hi = VR_AMPEL_PCT
    out["vertical_ratio"] = {"value": vr, "ampel": _band_asc(vr, v_lo, v_mid, v_hi)}

    # EF (Aerobe Effizienz) = Speed [m/min] / HR über das Steady-Z2-Segment.
    ef_run = [r for r in seg_run if r["hr"] and r["spd"]]
    ef = None
    if ef_run:
        s = _mean([r["spd"] for r in ef_run])
        h = _mean([r["hr"] for r in ef_run])
        ef = (s * 60.0 / h) if (s and h) else None
    e_hi, e_mid, e_lo = EF_AMPEL
    out["ef"] = {"value": _r(ef, 3),
                 "ampel": _band_desc(ef, e_hi, e_mid, e_lo, ("🟢🟢", "🟢", "🟠", "🔴")),
                 "basis": "Speed[m/min]/HR, steady Z2-Segment running-only"}

    # Decoupling-Ampel — nur methodisch valide bei Steady-State ≥45 min (§7/§11).
    d_val = dec.get("decoupling_pct")
    d_lo, d_mid, d_hi = DECOUPLING_AMPEL_PCT
    dur = summary.get("duration_s") or 0
    steady_ok = (not race_effort) and dur >= 45 * 60
    d_amp = _band_asc(d_val, d_lo, d_mid, d_hi)
    out["decoupling"] = {
        "value": d_val,
        "ampel": (d_amp if steady_ok else ("🟡" if d_val is not None else None)),
        "valid_steady_state": steady_ok,
        "note": None if steady_ok else "methodisch nicht aussagekräftig (kein Steady-State ≥45 min @ Z2)",
    }

    # Easy/Long-HR-Compliance (V3-HR-Cap-Logik) — bei Race N/A (Z3/Z4 ist der Plan).
    hr_avg = summary.get("hr_avg")
    if race_effort:
        out["easy_hr_compliance"] = {"value": hr_avg, "ampel": None,
                                     "note": "Race-Effort — HR-Cap-Ampel N/A (§8b)"}
    else:
        amp = None
        if hr_avg is not None:
            amp = "🟢" if hr_avg <= HR_Z2_CAP else ("🟡" if hr_avg <= EASY_HR_YELLOW_MAX else "🔴")
        out["easy_hr_compliance"] = {
            "value": hr_avg, "ampel": amp,
            "note": "Schnitt ≠ Decke: Z3-Zeitanteil (hr_zones) immer mit ausweisen (§11)",
        }
    return out


# ── Topografie (100m-Primär + 50m-Fein an Steil-Zonen) ──────────────────────
def _bucketize(pts, size_m):
    """Höhen-Buckets fester Größe → Zeilen mit km_start, Δh, Grade (+ interne Felder
    idx/_grade/_dd für Notable-Gate & Fein-Layer-Mapping)."""
    buckets = {}
    for r in pts:
        buckets.setdefault(int(r["dist"] // size_m), []).append(r)
    rows = []
    for b in sorted(buckets):
        grp = buckets[b]
        dh = grp[-1]["alt"] - grp[0]["alt"]
        dd = grp[-1]["dist"] - grp[0]["dist"]
        grade = (dh / dd * 100.0) if dd else None
        # Partieller Bucket (Track-Ende/GPS-Stop, <50% voll) → Grade-Artefakt unterdrücken (Fix v3.13)
        if dd is not None and dd < size_m * 0.5:
            grade = None
        rows.append({
            "idx": b,
            "km_start": _r(grp[0]["dist"] / 1000.0, 2),
            "delta_h_m": _r(dh, 1),
            "grade_pct": _r(grade, 1),
            "_grade": grade,
            "_dd": dd,
        })
    return rows


def topography(recs, bucket_m=100, fine_m=50):
    """Zwei Auflösungen: Primär (100m, feiner als die alten 200m) + 50m-Fein-Layer
    NUR in/um die Steil-Zonen (|Grade|>=2%), damit Anstieg→Abstieg-Paare im Detail
    sichtbar bleiben, ohne den ganzen Lauf in 50m-Zeilen zu kippen (§0-Kernregel)."""
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

    def _clean(rows):
        return [{"km_start": r["km_start"], "delta_h_m": r["delta_h_m"],
                 "grade_pct": r["grade_pct"]} for r in rows]

    # Primär-Auflösung (100m). Notable-Gate proportional: Bucket muss ≥75% voll sein
    # (filtert den partiellen End-Bucket / GPS-Stop-Artefakt raus).
    prim = _bucketize(pts, bucket_m)
    notable = [r for r in prim if r["_grade"] is not None
               and abs(r["_grade"]) >= 2.0 and r["_dd"] >= bucket_m * 0.75]

    # 50m-Fein-Layer NUR in/um die Steil-Zonen (+ je 1 Nachbar → Climb+Descent-Paar).
    fine_all = _bucketize(pts, fine_m)
    ratio = max(1, int(round(bucket_m / float(fine_m))))   # Fein-Buckets je Primär-Bucket
    keep = set()
    for r in notable:
        base = r["idx"] * ratio
        for fi in range(base - 1, base + ratio + 1):
            keep.add(fi)
    fine_rows = [r for r in fine_all if r["idx"] in keep]

    return {
        "ascent_m": _r(asc, 1),
        "descent_m": _r(desc, 1),
        "bucket_size_m": bucket_m,
        "buckets": _clean(prim),
        "notable_buckets": _clean(notable),    # |Grade| >= 2% (Primär-Auflösung)
        "fine_bucket_size_m": fine_m,
        "fine_buckets": _clean(fine_rows),      # 50m-Detail NUR in den Steil-Zonen
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

    # Steady-Z2-Segment (Surge-frei) — gemeinsame Basis für Pace@Z2 + Decoupling
    hrz = hr_zone_distribution(recs)
    seg_run, seg_label = steady_z2_segment(recs, fit)
    dec = decoupling(seg_run, seg_label)
    pz2 = pace_at_z2(seg_run, session, recs=recs, label=seg_label,
                     decoupling_pct=dec.get("decoupling_pct"),
                     walk_pct=summary.get("walk_pct"),
                     z4z5_pct=hrz.get("z4_z5_pct"))

    # V3-Ära beginnt 27.05.2026 (post-Japan). Läufe davor = historische Referenz,
    # NICHT an V3-Compliance/-Cues/-Baselines messen (Fix v3.13).
    run_date = (summary.get("start_time_utc") or "")[:10] or (as_of or "")
    pre_v3 = bool(run_date) and run_date < "2026-05-27"

    # Kadenz-Absenz-Transparenz: bei Speed-only-Fallback (spm=None) das im Meta
    # ausweisen — Gehanteil ist dann weniger belastbar (§4).
    n_no_cad = sum(1 for r in recs if r["spm"] is None)
    walking_filter = "v3.5 (cad<140 & spd<2.0; stand=cad0&spd<0.5 separat)"
    if n_no_cad:
        walking_filter += (f"; ⚠️ {n_no_cad}/{len(recs)} Samples ohne Kadenz → "
                           f"Speed-only-Fallback (Gehanteil weniger belastbar)")

    splits = km_splits(recs)
    form = run_form(recs, session)
    best = best_values(recs)

    # 7. Bestwert: schnellster KM aus den running-only-KM-Splits. Den partiellen
    # Schluss-Bucket ausschließen, wenn er <0,8 km trägt (Mini-Rest ≠ Bestwert).
    eligible = list(splits)
    dist_km = summary.get("distance_km")
    if eligible and dist_km and (dist_km - int(dist_km)) < 0.8 and len(eligible) > 1 \
            and eligible[-1]["km"] > int(dist_km):
        eligible = eligible[:-1]
    fk = min((s for s in eligible if s.get("pace_run_s")),
             key=lambda s: s["pace_run_s"], default=None)
    if fk:
        best["fastest_km"] = {"km": fk["km"], "pace": fk["pace_run"],
                              "hr_avg": fk["hr_avg"],
                              "basis": "running-only KM-Split (partieller Schluss-KM <0,8 km ausgeschlossen)"}

    race_effort = bool(pz2.get("race_effort"))
    ampeln = v3_ampeln(summary, form, dec, seg_run, race_effort)

    return {
        "ok": True,
        "schema_version": "3.14",
        "meta": {
            "fit_path": fit_path,
            "as_of": as_of,
            "run_date": run_date or None,
            "pre_v3": pre_v3,
            "sport": sport,
            "sub_sport": sub_sport,
            "workout_name": workout_name,
            "apple_watch_fit": apple_watch_fit,
            "record_count": len(recs),
            "walking_filter": walking_filter,
            "parser": "fitparse",
            "skill": "run-bundle-skill v3.14",
        },
        "summary": summary,
        "splits_km": splits,
        "splits_lap": lap_splits(fit, recs),
        "hr_zones": hrz,
        "hr_source_warn": hr_source_warn(recs),
        "run_form": form,
        "best_values": best,
        "sprint_last_60s": last_60s_sprint(recs, run_avg_pace_s),
        "decoupling": dec,
        "pace_at_z2": pz2,
        "v3_ampeln": ampeln,
        "topography": topography(recs),
    }


def main():
    ap = argparse.ArgumentParser(
        description="FIT-Lauf-Analyse (run-bundle-skill v3.14) — Aggregate-JSON auf stdout.")
    ap.add_argument("fit_path", help="Pfad zur .fit-Datei")
    ap.add_argument("--as-of", required=True, metavar="YYYY-MM-DD",
                    help="Bezugsdatum (heute), z.B. 2026-06-28")
    args = ap.parse_args()

    result = analyze(args.fit_path, args.as_of)
    # Kompaktes JSON (Aggregate-only — NIE Roh-Records)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
