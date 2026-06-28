#!/usr/bin/env python3
"""
stats.py — Statistische Coaching-Analysen (scipy/statsmodels) für daily-check.

Vier ADVISORY-Analysen über die Gesundheitsdaten_v5- + Trainings_v5-Historie.
Alles read-only, Ausgabe = kompaktes JSON (nur Aggregate, nie Rohserien).

EHRLICHKEITS-PRINZIP
--------------------
Jede Analyse prüft Datensuffizienz. Ist n zu klein, fehlt eine Spalte, oder ist
ein Fit instabil → `{"insufficient_data": true, "reason": "..."}` statt eines
schöngerechneten Fits. Keine erfundenen Zahlen.

ANALYSEN
--------
1. bedtime_hrv   — Javiers #1-Stellschraube. OLS Bettzeit → (Folge-)Tag-HFV.
                   slope (ms HFV pro Stunde später) + 95%-CI + R² + n.
                   Confound-Wächter: zweites Modell kontrolliert Schlafdauer.
2. race_readiness— B2Run 6 km (21.07): aus CTL/TSB (Banister) + jüngster
                   Z2-Pace/HF → transparentes 6-km-Pace/Zielband (best/real/konservativ).
3. anomaly       — Robuster z-Score (Median/MAD) über die letzten N Tage für
                   HFV & Ruhe-HF → statistische Ausreißer (ergänzt §5-Ampel, ersetzt sie nicht).
4. banister_fit  — Best-effort-Personalisierung der CTL/ATL-Zeitkonstanten
                   (vs Default 42/7) gegen HFV/RHR. ADVISORY — ersetzt NIE den
                   deterministischen 42/7-Banister; instabil/dünn → Default + Hinweis.

CLI
---
  python stats.py bedtime_hrv   --sleep ges_sleep.csv --daily ges_daily.csv
  python stats.py race_readiness --trainings trainings.csv [--as-of YYYY-MM-DD]
  python stats.py anomaly       --daily ges_daily.csv
  python stats.py banister_fit  --trainings trainings.csv --daily ges_daily.csv

Kernfunktionen (fit_bedtime_hrv, robust_anomaly, project_race, fit_banister_tc)
nehmen native Python-Strukturen → testbar OHNE echte Daten (siehe tests/test_stats.py).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict

import numpy as np

# ── Sibling-Imports (banister/dedup liegen im selben scripts/-Verzeichnis) ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ════════════════════════════════════════════════════════════════════════
#  Parsing-Helfer (deutsche Header, ₂-Subscripts, Komma/Punkt, DD.MM.YYYY)
# ════════════════════════════════════════════════════════════════════════
_DATE_FMTS = ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%Y/%m/%d")


def parse_date(s):
    if isinstance(s, (dt.date, dt.datetime)):
        return s.date() if isinstance(s, dt.datetime) else s
    s = (s or "").strip()
    if not s:
        return None
    head = s.split()[0].split("T")[0]
    for cand in (s, head):
        for fmt in _DATE_FMTS:
            try:
                return dt.datetime.strptime(cand, fmt).date()
            except ValueError:
                continue
    return None


def to_float(x):
    if x is None:
        return None
    s = str(x).replace(",", ".").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def clock_to_decimal(s):
    """'HH:MM' → Dezimalstunde, abends negativ (Lateness-Achse um Mitternacht).
    23:30 → -0.5 · 00:30 → +0.5 · 02:20 → +2.33 · monoton 'später = größer'."""
    s = (s or "").strip()
    if ":" not in s:
        return None
    try:
        h, m = (int(p) for p in s.split(":")[:2])
    except ValueError:
        return None
    v = h + m / 60.0
    if h >= 18:          # 18:00–23:59 → Vorabend, negativ
        v -= 24.0
    return v


def hms_to_seconds(s):
    """'0h:43m:48s' → Sekunden."""
    m = re.match(r"\s*(\d+)h:(\d+)m:(\d+)s", (s or "").strip())
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def hm_to_hours(s):
    """'8h:31m' → Stunden (Schlafdauer-Strings)."""
    m = re.search(r"(\d+)h:(\d+)m", (s or "").strip())
    if not m:
        return None
    return int(m.group(1)) + int(m.group(2)) / 60.0


def load_csv(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [], []
    header = [h.strip() for h in rows[0]]
    return header, rows[1:]


def col_idx(header, *names):
    """Erste Spalte, deren (getrimmter, lower) Name eines der Targets enthält."""
    low = [(h or "").strip().lower() for h in header]
    for name in names:
        n = name.strip().lower()
        for i, h in enumerate(low):
            if h == n:
                return i
    for name in names:               # Fallback: Substring
        n = name.strip().lower()
        for i, h in enumerate(low):
            if n in h:
                return i
    return None


def _median_by_date(rows, di, vi, transform=to_float):
    """{date: Median der Nicht-None-Werte} — kollabiert die Sheet-Duplikate."""
    g = defaultdict(list)
    for r in rows:
        if di >= len(r) or vi >= len(r):
            continue
        d = parse_date(r[di])
        v = transform(r[vi])
        if d is not None and v is not None:
            g[d].append(v)
    return {d: statistics.median(v) for d, v in g.items() if v}


# ════════════════════════════════════════════════════════════════════════
#  1) BEDTIME → HRV  (Kernfunktion: native pairs → testbar)
# ════════════════════════════════════════════════════════════════════════
def fit_bedtime_hrv(pairs, ref_bedtime=0.5, durations=None, min_n=20):
    """
    pairs:      list[(bedtime_decimal, hrv_ms)] — abends negativ, nach Mitternacht positiv.
    ref_bedtime: Anker für die Kosten-Formulierung (0.5 = 00:30).
    durations:  optional list[Schlafdauer_h] gleicher Länge → Confound-Modell (HFV ~ Bett + Dauer).
    Rückgabe:   OLS-Slope (ms HFV / Stunde später) + 95%-CI + R² + n + predicted@ref/+1h/+2h.
    """
    import statsmodels.api as sm

    xy = [(b, h) for b, h in pairs if b is not None and h is not None
          and math.isfinite(b) and math.isfinite(h)]
    if len(xy) < min_n:
        return {"insufficient_data": True,
                "reason": f"n={len(xy)} < {min_n} gemeinsame Nächte für robustes OLS",
                "n": len(xy)}
    x = np.array([p[0] for p in xy], float)
    y = np.array([p[1] for p in xy], float)
    if np.ptp(x) < 0.5:
        return {"insufficient_data": True,
                "reason": "Bettzeit-Streuung <0.5 h → Slope nicht identifizierbar", "n": len(xy)}

    model = sm.OLS(y, sm.add_constant(x)).fit()
    slope = float(model.params[1])
    intercept = float(model.params[0])
    ci = model.conf_int(0.05)[1]
    out = {
        "n": len(xy),
        "slope_ms_per_hour_later": round(slope, 3),
        "ci95": [round(float(ci[0]), 3), round(float(ci[1]), 3)],
        "r_squared": round(float(model.rsquared), 4),
        "p_value": round(float(model.pvalues[1]), 4),
        "intercept_ms": round(intercept, 2),
        "ref_bedtime_hours": ref_bedtime,
        "bedtime_range_hours": [round(float(x.min()), 2), round(float(x.max()), 2)],
        "predicted_hrv": {
            "at_ref": round(intercept + slope * ref_bedtime, 1),
            "ref_plus_1h": round(intercept + slope * (ref_bedtime + 1), 1),
            "ref_plus_2h": round(intercept + slope * (ref_bedtime + 2), 1),
        },
        "cost_per_hour_past_ref_ms": round(slope, 2),
        "significant_5pct": bool(model.pvalues[1] < 0.05),
    }
    # Confound-Wächter: kontrolliert Schlafdauer (später ↔ kürzer ↔ schlechtere HFV)
    if durations is not None:
        dd = [(b, h, d) for (b, h), d in zip(pairs, durations)
              if None not in (b, h, d) and all(math.isfinite(v) for v in (b, h, d))]
        if len(dd) >= min_n:
            xb = np.array([r[0] for r in dd], float)
            yb = np.array([r[1] for r in dd], float)
            xdur = np.array([r[2] for r in dd], float)
            m2 = sm.OLS(yb, sm.add_constant(np.column_stack([xb, xdur]))).fit()
            out["controlled_for_sleep_duration"] = {
                "n": len(dd),
                "slope_bedtime_ms_per_hour": round(float(m2.params[1]), 3),
                "p_value": round(float(m2.pvalues[1]), 4),
                "note": "Bettzeit-Slope NACH Herauspartialisieren der Schlafdauer — "
                        "bleibt er negativ & signifikant, ist es nicht bloß 'spät = kürzer'.",
            }
    out["confound_note"] = (
        "Assoziation, keine Kausalität: späte Nächte korrelieren mit Wochenende, "
        "Alkohol, Stress, kürzerem Schlaf — alle senken HFV unabhängig. Slope = "
        "obere Schranke des reinen Timing-Effekts. Engeres Fenster (--window-days) "
        "isoliert den jüngsten Verhaltens-Effekt sauberer."
    )
    return out


def cmd_bedtime_hrv(args):
    sh, sd = load_csv(args.sleep)
    dh, dd = load_csv(args.daily)
    s_date = col_idx(sh, "Datum")
    s_main = col_idx(sh, "Main")
    s_anf = col_idx(sh, "Anfang")
    s_slp = col_idx(sh, "Schlaf")
    d_date = col_idx(dh, "Datum")
    d_hfv = col_idx(dh, "HFV", "HRV")
    if None in (s_date, s_anf) or d_date is None or d_hfv is None:
        return {"insufficient_data": True,
                "reason": "Pflichtspalten fehlen (Schlaf:Datum/Anfang, Tägliche:Datum/HFV)"}

    # Bettzeit + Schlafdauer je Nacht (nur Haupt-Schlaf)
    bedtime, duration = {}, {}
    for r in sd:
        if s_main is not None and s_main < len(r) and r[s_main].strip().lower() not in ("true", "wahr", "1"):
            continue
        d = parse_date(r[s_date]) if s_date < len(r) else None
        if d is None:
            continue
        b = clock_to_decimal(r[s_anf]) if s_anf < len(r) else None
        if b is not None and d not in bedtime:
            bedtime[d] = b
            if s_slp is not None and s_slp < len(r):
                duration[d] = hm_to_hours(r[s_slp])

    hfv = _median_by_date(dd, d_date, d_hfv)
    if not bedtime or not hfv:
        return {"insufficient_data": True, "reason": "Keine Bettzeit- oder HFV-Werte geparst"}

    # Fenster auf jüngste N Tage (Default 180) — isoliert aktuelles Verhalten vom
    # Fitness-/Saison-Trend über 15 Monate, der den Timing-Effekt sonst überdeckt.
    last = max(hfv)
    lag = args.lag_days
    pairs, durs = [], []
    for d, b in bedtime.items():
        if args.window_days and (last - d).days > args.window_days:
            continue
        h = hfv.get(d + dt.timedelta(days=lag))
        if h is not None:
            pairs.append((b, h))
            durs.append(duration.get(d))
    res = fit_bedtime_hrv(pairs, ref_bedtime=args.ref_bedtime, durations=durs)
    res["window_days"] = args.window_days
    res["hrv_lag_days"] = lag
    res["alignment_note"] = (
        "lag_days=1: HFV des Folgetags = Erholung NACH der Nacht (Datums-Konvention "
        "der Sheets; lag=0/2 via --lag-days prüfbar). HFV = 'Tägliche Kennzahlen', "
        "Bettzeit = Schlaf-Tab 'Anfang' (Haupt-Schlaf)."
    )
    # Voll-Historie als Kontext (ohne Fenster) — Trend vs Absolutsignal
    if args.window_days:
        full = [(b, hfv.get(d + dt.timedelta(days=lag)))
                for d, b in bedtime.items() if hfv.get(d + dt.timedelta(days=lag)) is not None]
        ctx = fit_bedtime_hrv([(b, h) for b, h in full], ref_bedtime=args.ref_bedtime, min_n=20)
        res["full_history_context"] = {k: ctx.get(k) for k in
                                       ("n", "slope_ms_per_hour_later", "ci95", "r_squared", "p_value")
                                       if k in ctx} or ctx
    return res


# ════════════════════════════════════════════════════════════════════════
#  2) RACE READINESS  (B2Run 6 km, 21.07) — transparente Heuristik
# ════════════════════════════════════════════════════════════════════════
# Annahmen (explizit, überschreibbar). Faktor = Renn-Pace / Z2-Pace (kleiner = schneller).
RACE_FACTORS = {"best": 0.82, "real": 0.87, "conservative": 0.93}


def project_race(z2_pace_min_km, race_km=6.0, tsb=None, factors=None):
    """
    z2_pace_min_km: jüngste aerobe (Z2) Pace [min/km].
    tsb:            optionale Form (Banister) → kleiner TSB-Nudge auf das Band.
    Transparente Heuristik: Renn-Pace = Z2-Pace × Faktor (best/real/konservativ),
    +/- 1 % je nach TSB-Frische. KEINE Physiologie-Magie — nur ein labelter Gap.
    """
    factors = dict(factors or RACE_FACTORS)
    tsb_adj = 0.0
    if tsb is not None:
        if tsb > 5:
            tsb_adj = -0.01            # frisch → minimal schneller
        elif tsb < -15:
            tsb_adj = +0.02            # ermüdet → konservativer
    band = {}
    for name, f in factors.items():
        pace = z2_pace_min_km * (f + tsb_adj)
        total_min = pace * race_km
        band[name] = {
            "pace_min_per_km": round(pace, 2),
            "finish": f"{int(total_min)}:{int(round((total_min % 1) * 60)):02d}",
            "finish_minutes": round(total_min, 1),
            "assumed_race_factor": round(f + tsb_adj, 3),
        }
    return band


def _extract_easy_runs(rows, H, window_days):
    di = col_idx(H, "Datum")
    ai = col_idx(H, "Art")
    gi = col_idx(H, "Gesamtzeit")
    si = col_idx(H, "Strecke")
    hi = col_idx(H, "Ø Herzfrequenz", "Durchschnittliche Herzfrequenz", "Herzfrequenz")
    z1 = col_idx(H, "HRZ1")
    z2 = col_idx(H, "HRZ2")
    z0 = col_idx(H, "HRZ0")
    if None in (di, ai, gi, si):
        return None, None
    dates = [parse_date(r[di]) for r in rows if di < len(r)]
    last = max([d for d in dates if d], default=None)
    if last is None:
        return None, None
    runs, seen = [], set()
    for r in rows:
        if di >= len(r) or "lauf" not in (r[ai] or "").lower():
            continue
        d = parse_date(r[di])
        if not d or (last - d).days > window_days:
            continue
        dist = to_float(r[si]) if si < len(r) else None
        sec = hms_to_seconds(r[gi]) if gi < len(r) else None
        if not dist or not sec or dist < 2:
            continue
        pace = (sec / 60.0) / dist
        hr = to_float(r[hi]) if hi is not None and hi < len(r) else None
        if not (4.0 <= pace <= 9.5):
            continue
        # Trainings_v5-Duplikate kollabieren (Datum+Pace+HF identisch → 1 Session)
        key = (d, round(pace, 2), round(hr) if hr else 0)
        if key in seen:
            continue
        seen.add(key)
        # Z2-Dominanz: Anteil niedriger Zonen an der Bewegungszeit
        zlow = sum(hms_to_seconds(r[z]) or 0 for z in (z0, z1, z2) if z is not None and z < len(r))
        easy = (zlow / sec) >= 0.55 if zlow else (hr is not None and hr <= 150)
        runs.append({"date": d, "pace": pace, "hr": hr, "easy": easy})
    return runs, last


def cmd_race_readiness(args):
    H, rows = load_csv(args.trainings)
    runs, last = _extract_easy_runs(rows, H, args.pace_window)
    if not runs:
        return {"insufficient_data": True,
                "reason": "Keine Laufeinheiten mit Strecke+Zeit im Pace-Fenster"}
    easy = [r for r in runs if r["easy"]]
    if len(easy) >= 3:
        paces = [r["pace"] for r in easy]
        hrs = [r["hr"] for r in easy if r["hr"]]
        pace_basis = "z2_dominant_runs"
    elif len(runs) >= 5:
        # Zu wenig saubere Z2-Läufe (Javier läuft selten reines Z2) → langsamere
        # Hälfte der jüngsten Läufe als aerober Pace-PROXY (transparent geflaggt).
        slow = sorted(runs, key=lambda r: r["pace"])[len(runs) // 2:]
        paces = [r["pace"] for r in slow]
        hrs = [r["hr"] for r in slow if r["hr"]]
        pace_basis = "proxy_slower_half"
    else:
        return {"insufficient_data": True,
                "reason": f"nur {len(runs)} Läufe im Fenster — Pace-Basis zu dünn für Projektion",
                "n_runs": len(runs)}
    z2_pace = statistics.median(paces)

    # CTL/TSB über den deterministischen Banister (Reuse, gleiche 42/7-Konstanten)
    tsb = ctl = None
    banister_meta = None
    try:
        from dedup_trainings import dedup
        from banister import extract_daily_trimp, banister as run_banister
        raw = open(args.trainings, encoding="utf-8", errors="replace").read()
        clean, rep = dedup(raw)
        daily_trimp, _ = extract_daily_trimp(clean, rep.get("header"))
        as_of = args.as_of or dt.date.today().isoformat()
        bres = run_banister(daily_trimp, as_of=as_of)
        if bres:
            tsb, ctl = bres["tsb"], bres["ctl"]
            banister_meta = {"ctl": ctl, "atl": bres["atl"], "tsb": tsb,
                             "warmup_ok": bres["warmup_ok"], "as_of": bres["as_of"]}
    except Exception as e:  # noqa: BLE001 — Banister optional, Heuristik läuft auch ohne
        banister_meta = {"error": f"Banister übersprungen: {e}"}

    band = project_race(z2_pace, race_km=args.race_km, tsb=tsb)
    return {
        "race": {"event": "B2Run", "km": args.race_km, "date": args.race_date},
        "inputs": {
            "z2_pace_min_per_km": round(z2_pace, 2),
            "pace_basis": pace_basis,
            "n_pace_runs": len(paces),
            "n_runs_in_window": len(runs),
            "median_pace_hr": round(statistics.median(hrs)) if hrs else None,
            "pace_window_days": args.pace_window,
            "ctl": ctl, "tsb": tsb,
        },
        "banister": banister_meta,
        "projection": band,
        "heuristic": (
            "Renn-Pace = jüngste Z2-Pace × Renn-Faktor "
            f"(best {RACE_FACTORS['best']} / real {RACE_FACTORS['real']} / "
            f"konservativ {RACE_FACTORS['conservative']}), TSB-Nudge ±1–2 %. "
            "TRANSPARENTE Heuristik, keine VO2max-Projektion — der Faktor ist eine "
            "Annahme über den aerob→Renn-Gap, nicht gemessen. 6 km ≈ 30–45 min Effort."
        ),
        "assumptions": [
            "Z2-Pace = Median 'easy' Läufe (Zonen-Zeit-Anteil ≥55 % niedrig, sonst HF≤150); "
            "bei <3 sauberen Z2-Läufen PROXY = langsamere Hälfte der jüngsten Läufe "
            f"(pace_basis='{pace_basis}' im Output prüfen).",
            "Renn-Faktor fix/labeled — kein individueller Riegel-/VO2-Fit.",
            "Wetter/Topo/Tapering NICHT modelliert (B2Run = Abend, oft warm).",
        ],
    }


# ════════════════════════════════════════════════════════════════════════
#  3) ANOMALY  (robuster z-Score über Median/MAD)
# ════════════════════════════════════════════════════════════════════════
def robust_anomaly(values, higher_is_bad=False, z_thresh=3.5, min_n=10):
    """
    values:        zeitlich geordnete Trailing-Serie (ältest→neust ODER umgekehrt egal;
                   die Funktion bewertet den LETZTEN Eintrag values[-1] gegen den Rest).
    higher_is_bad: True für RHR (hoch=schlecht), False für HFV (niedrig=schlecht).
    Robuster z = (x − Median) / (1.4826 × MAD). Flag bei |z| > z_thresh in
    der 'schlechten' Richtung. Ergänzt die §5-Ampel, ersetzt sie NICHT.
    """
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if len(vals) < min_n:
        return {"insufficient_data": True,
                "reason": f"n={len(vals)} < {min_n} Tage für robusten z-Score", "n": len(vals)}
    latest = vals[-1]
    base = vals[:-1]
    med = statistics.median(base)
    mad = statistics.median([abs(v - med) for v in base])
    if mad == 0:
        spread = statistics.pstdev(base)
        if spread == 0:
            return {"insufficient_data": True,
                    "reason": "Streuung 0 (MAD=σ=0) → z nicht definiert", "n": len(vals)}
        z = (latest - med) / spread
        method = "stdev_fallback"
    else:
        z = (latest - med) / (1.4826 * mad)
        method = "median_mad"
    bad_dir = z > 0 if higher_is_bad else z < 0
    return {
        "n": len(vals),
        "latest": round(latest, 2),
        "median": round(med, 2),
        "mad": round(mad, 3),
        "robust_z": round(z, 2),
        "z_threshold": z_thresh,
        "method": method,
        "is_outlier": bool(abs(z) > z_thresh),
        "is_adverse_outlier": bool(abs(z) > z_thresh and bad_dir),
        "direction": ("hoch" if z > 0 else "niedrig"),
    }


def cmd_anomaly(args):
    dh, dd = load_csv(args.daily)
    d_date = col_idx(dh, "Datum")
    d_hfv = col_idx(dh, "HFV", "HRV")
    d_rhr = col_idx(dh, "Ruheherzfrequenz", "RHR", "Ruhe-HF")
    if d_date is None:
        return {"insufficient_data": True, "reason": "Datum-Spalte fehlt"}
    out = {"window_days": args.window}
    last_seen = max((parse_date(r[d_date]) for r in dd if d_date < len(r)
                     and parse_date(r[d_date])), default=None)
    for key, idx, hib in (("hrv", d_hfv, False), ("rhr", d_rhr, True)):
        if idx is None:
            out[key] = {"insufficient_data": True, "reason": "Spalte fehlt"}
            continue
        series = _median_by_date(dd, d_date, idx)
        if last_seen:
            series = {d: v for d, v in series.items()
                      if (last_seen - d).days <= args.window}
        ordered = [series[d] for d in sorted(series)]
        out[key] = robust_anomaly(ordered, higher_is_bad=hib, z_thresh=args.z_thresh)
        if last_seen:
            out[key]["as_of"] = last_seen.isoformat()
    out["note"] = ("Statistischer Ausreißer-Detektor (Median/MAD), ROBUST gegen "
                   "Einzel-Spikes. Ergänzt die V3-Ampel (§5), ersetzt sie nicht.")
    return out


# ════════════════════════════════════════════════════════════════════════
#  4) BANISTER FIT  (advisory Zeitkonstanten-Personalisierung)
# ════════════════════════════════════════════════════════════════════════
def _ewma_series(daily_trimp_list, tc):
    """daily_trimp_list: lückenlose Tagesreihe [(date, trimp)]. → {date: ewma}."""
    lam = 1 - math.exp(-1 / tc)
    out, acc = {}, 0.0
    for d, t in daily_trimp_list:
        acc += (t - acc) * lam
        out[d] = acc
    return out


def fit_banister_tc(daily_trimp, response, default=(42, 7),
                    bounds=((14, 84), (3, 21)), min_n=60):
    """
    daily_trimp: {date: TRIMP} (Sessions; Lücken werden mit 0 gefüllt).
    response:    {date: HFV oder RHR}.
    Fittet (tc_ctl, tc_atl) so, dass response ~ a + p·CTL + q·ATL minimal residuiert
    (innere OLS), via Grid-Seed + scipy.minimize. Vergleich gegen Default 42/7.
    INSTABIL/DÜNN → Default + insufficient_data-Hinweis. ADVISORY, ersetzt 42/7 NIE.
    """
    from scipy.optimize import minimize

    if not daily_trimp or not response:
        return {"insufficient_data": True, "reason": "Leere TRIMP- oder Response-Serie",
                "recommended_tc": list(default)}
    start, end = min(daily_trimp), max(response)
    if (end - start).days < min_n:
        return {"insufficient_data": True,
                "reason": f"Historie {(end - start).days} d < {min_n} d für stabilen TC-Fit",
                "recommended_tc": list(default),
                "note": "Default 42/7 bleibt maßgeblich."}
    # Lückenlose Tagesreihe, Ruhetage = 0
    series, d = [], start
    while d <= end:
        series.append((d, daily_trimp.get(d, 0.0)))
        d += dt.timedelta(days=1)
    resp_dates = [d for d in response if start <= d <= end]
    y = np.array([response[d] for d in resp_dates], float)
    if len(y) < min_n:
        return {"insufficient_data": True,
                "reason": f"nur {len(y)} Response-Tage überlappen die TRIMP-Reihe",
                "recommended_tc": list(default)}

    def sse(params):
        tc_ctl, tc_atl = params
        if not (bounds[0][0] <= tc_ctl <= bounds[0][1]) or not (bounds[1][0] <= tc_atl <= bounds[1][1]):
            return 1e18
        ctl = _ewma_series(series, tc_ctl)
        atl = _ewma_series(series, tc_atl)
        X = np.column_stack([np.ones(len(resp_dates)),
                             [ctl[d] for d in resp_dates],
                             [atl[d] for d in resp_dates]])
        beta, res, rank, _ = np.linalg.lstsq(X, y, rcond=None)
        if rank < 3:
            return 1e18
        return float(np.sum((y - X @ beta) ** 2))

    def r2_at(params):
        s = sse(params)
        sst = float(np.sum((y - y.mean()) ** 2))
        return 1 - s / sst if sst > 0 else 0.0

    # Grid-Seed → robust gegen lokale Minima, dann verfeinern
    best, best_sse = default, sse(default)
    for tcc in range(int(bounds[0][0]), int(bounds[0][1]) + 1, 7):
        for tca in range(int(bounds[1][0]), int(bounds[1][1]) + 1, 3):
            s = sse((tcc, tca))
            if s < best_sse:
                best, best_sse = (tcc, tca), s
    fit = minimize(sse, x0=best, method="Nelder-Mead",
                   options={"xatol": 0.5, "fatol": 1e-3, "maxiter": 400})
    tc_ctl, tc_atl = (round(float(fit.x[0]), 1), round(float(fit.x[1]), 1)) if fit.success else best
    r2_fit, r2_def = r2_at((tc_ctl, tc_atl)), r2_at(default)

    # Stabilitäts-Wächter
    on_bound = (abs(tc_ctl - bounds[0][0]) < 1 or abs(tc_ctl - bounds[0][1]) < 1 or
                abs(tc_atl - bounds[1][0]) < 1 or abs(tc_atl - bounds[1][1]) < 1)
    gain = r2_fit - r2_def
    unstable = on_bound or gain < 0.01 or r2_fit < 0.05 or not fit.success
    res = {
        "default_tc": list(default),
        "fitted_tc": [tc_ctl, tc_atl],
        "r_squared_fitted": round(r2_fit, 4),
        "r_squared_default": round(r2_def, 4),
        "r2_gain_vs_default": round(gain, 4),
        "n_response_days": len(y),
        "history_days": (end - start).days,
        "advisory_only": True,
        "recommended_tc": list(default) if unstable else [tc_ctl, tc_atl],
    }
    if unstable:
        res["insufficient_data"] = True
        res["reason"] = ("Fit instabil/marginal (Rand-Lösung, R²-Gewinn <0.01, oder R²<0.05) "
                         "→ Default 42/7 bleibt maßgeblich.")
    res["note"] = ("ADVISORY-Personalisierung. Ersetzt NICHT den deterministischen 42/7-"
                   "Banister im Daily-Check — nur ein Hinweis, ob Javiers HFV/RHR auf "
                   "andere Zeitkonstanten reagiert.")
    return res


def cmd_banister_fit(args):
    try:
        from dedup_trainings import dedup
        from banister import extract_daily_trimp
    except Exception as e:  # noqa: BLE001
        return {"insufficient_data": True, "reason": f"banister/dedup-Import fehlgeschlagen: {e}",
                "recommended_tc": [42, 7]}
    raw = open(args.trainings, encoding="utf-8", errors="replace").read()
    clean, rep = dedup(raw)
    daily_trimp, _ = extract_daily_trimp(clean, rep.get("header"))

    dh, dd = load_csv(args.daily)
    d_date = col_idx(dh, "Datum")
    col = col_idx(dh, "HFV", "HRV") if args.response == "HFV" else col_idx(dh, "Ruheherzfrequenz", "RHR")
    if d_date is None or col is None:
        return {"insufficient_data": True, "reason": f"Response-Spalte '{args.response}' fehlt",
                "recommended_tc": [42, 7]}
    response = _median_by_date(dd, d_date, col)
    res = fit_banister_tc(daily_trimp, response)
    res["response_variable"] = args.response
    return res


# ════════════════════════════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════════════════════════════
def main(argv=None):
    p = argparse.ArgumentParser(description="Statistische Coaching-Analysen (advisory).")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bedtime_hrv", help="OLS Bettzeit → (Folge-)Tag-HFV")
    b.add_argument("--sleep", required=True)
    b.add_argument("--daily", required=True)
    b.add_argument("--ref-bedtime", type=float, default=0.5, dest="ref_bedtime")
    b.add_argument("--window-days", type=int, default=180, dest="window_days")
    b.add_argument("--lag-days", type=int, default=1, dest="lag_days")
    b.set_defaults(func=cmd_bedtime_hrv)

    r = sub.add_parser("race_readiness", help="6-km-Projektion aus CTL/TSB + Z2-Pace")
    r.add_argument("--trainings", required=True)
    r.add_argument("--as-of", default=None, dest="as_of")
    r.add_argument("--race-date", default="2026-07-21", dest="race_date")
    r.add_argument("--race-km", type=float, default=6.0, dest="race_km")
    r.add_argument("--pace-window", type=int, default=90, dest="pace_window")
    r.set_defaults(func=cmd_race_readiness)

    a = sub.add_parser("anomaly", help="Robuster z-Score HFV/RHR")
    a.add_argument("--daily", required=True)
    a.add_argument("--window", type=int, default=30)
    a.add_argument("--z-thresh", type=float, default=3.5, dest="z_thresh")
    a.set_defaults(func=cmd_anomaly)

    bf = sub.add_parser("banister_fit", help="Advisory CTL/ATL-Zeitkonstanten-Fit")
    bf.add_argument("--trainings", required=True)
    bf.add_argument("--daily", required=True)
    bf.add_argument("--response", choices=["HFV", "RHR"], default="HFV")
    bf.set_defaults(func=cmd_banister_fit)

    args = p.parse_args(argv)
    res = args.func(args)
    print(json.dumps(res, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
