#!/usr/bin/env python3
"""
analyze_run.py — CSV-Fallback-Engine des run-bundle-skill (v3.14).

ZWECK
-----
Echtes Pendant zur FIT-Engine (`analyze_run_fit.py`) für den HealthFit-CSV-Pfad
(kein FIT verfügbar). Vorher war dies ein Referenz-Stub, der ROHE Mittelwerte
inkl. Gehen rechnete — ein NEVER-Regel-Bruch (Kadenz/GCT/Pace nie MIT Gehpausen
bewerten). Jetzt: EIN Aggregations-Codepfad für beide Formate — dieses Script
parst NUR das CSV in dieselben Record-Dicts und ruft die geteilten Funktionen
der FIT-Engine auf (Walking-Filter v3.5, km-Splits, HR-Zonen, run_form,
Bestwerte, Decoupling, Pace@Z2, §11-Ampeln, Topografie).

Gleiche Regeln wie die FIT-Engine (dort autoritativ dokumentiert):
- Kadenz = Single-Foot × 2; Kadenz-ABSENZ ≠ 0 spm (Speed-only-Fallback).
- Walking-Filter v3.5: (spm<140 UND spd<2,0); Stillstand separat.
- Ausschließlich AGGREGATE auf stdout — NIE Roh-Sample-Arrays (§0-Kernregel).

CSV-Schema (HealthFit, Semicolon-Delimiter, Komma-Dezimal — SKILL §2c):
Time;Timestamp;ISO8601;Heart Rate (bpm);Power (watt);Cadence (count/min);…;
Distance (meter);Speed (m/s);Stride length (mm);VO (mm);GCT (ms);Lap;Intensity;…

CLI:  python3 analyze_run.py <csv_path> --as-of YYYY-MM-DD
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

# Geteilte Aggregations-Engine (gleicher Ordner) — Parser hier, Rechnen dort.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_run_fit as F  # noqa: E402

SCHEMA_VERSION = "3.14"


def _f(v):
    """CSV-Zelle → float. Komma-Dezimal, leere Zellen → None."""
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ts(v):
    """ISO8601-Zelle → datetime (None bei Parse-Fehler)."""
    if not v:
        return None
    s = str(v).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def read_csv_records(csv_path):
    """HealthFit-CSV → (records, laps_raw). Records = dieselben Dicts wie die
    FIT-Engine (ts/hr/spd/alt/dist/spm/power/gct/vo/stride/vr/temp/run/walk/stand),
    damit alle geteilten Aggregations-Funktionen 1:1 laufen."""
    recs, lap_ids = [], []
    with open(csv_path, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        if not reader.fieldnames:
            return [], []
        cols = {c.strip(): c for c in reader.fieldnames}

        def get(row, name):
            c = cols.get(name)
            return row.get(c) if c else None

        last_dist = 0.0
        for row in reader:
            # Kadenz-ABSENZ ≠ 0 spm (wie FIT-Engine): fehlende Zelle → None →
            # Speed-only-Fallback im Gangart-Filter, keine Walking-Lüge.
            cad = _f(get(row, "Cadence (count/min)"))
            spm = cad * 2.0 if cad is not None else None
            spd = _f(get(row, "Speed (m/s)")) or 0.0
            dist = _f(get(row, "Distance (meter)"))
            if dist is None:
                dist = last_dist
            else:
                last_dist = dist

            if spm is None:
                is_stand = spd < F.STAND_SPD
                is_walk = (spd < F.WALK_SPD) and not is_stand
            else:
                is_stand = (spm == 0) and (spd < F.STAND_SPD)
                is_walk = (spm < F.WALK_CAD) and (spd < F.WALK_SPD) and not is_stand

            recs.append({
                "ts": _ts(get(row, "ISO8601")),
                "hr": _f(get(row, "Heart Rate (bpm)")),
                "spd": spd,
                "alt": _f(get(row, "Elevation (meter)")),
                "dist": dist,
                "spm": spm,
                "power": _f(get(row, "Power (watt)")),
                "gct": _f(get(row, "GCT (ms)")),
                "vo": _f(get(row, "VO (mm)")),
                "stride": _f(get(row, "Stride length (mm)")),
                "vr": None,          # CSV hat keine native VR-Spalte → Rekonstruktion (VO/Stride)
                "temp": None,        # CSV trägt keine Temperatur → Hitze-Norm nur via session/CLI
                "run": (not is_walk and not is_stand),
                "walk": is_walk,
                "stand": is_stand,
            })
            lap_ids.append(get(row, "Lap"))
    return recs, lap_ids


def csv_lap_splits(recs, lap_ids):
    """Lap-Splits aus der CSV-`Lap`-Spalte — gleiche Zeilen-Form wie die
    FIT-`splits_lap` (CSV hat keine lap-Messages, §2c)."""
    groups = {}
    order = []
    for r, lid in zip(recs, lap_ids):
        key = str(lid).strip() if lid is not None and str(lid).strip() else None
        if key is None:
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    out = []
    for i, key in enumerate(order):
        b = groups[key]
        run = [r for r in b if r["run"]]
        hrs = [r["hr"] for r in b if r["hr"] is not None]
        d0, d1 = b[0]["dist"], b[-1]["dist"]
        dur = F._dt(b[0]["ts"], b[-1]["ts"])
        spd_run = F._mean([r["spd"] for r in run])
        hr_avg = F._mean(hrs)
        out.append({
            "lap": i + 1,
            "trigger": "csv_lap",
            "intensity": None,
            "dist_m": F._r((d1 - d0), 0) if (d0 is not None and d1 is not None) else None,
            "time_s": F._r(dur, 0),
            "pace": F._pace_str(F._pace_from_speed(spd_run)),
            "hr_avg": F._r(hr_avg, 0),
            "hr_max": max(hrs) if hrs else None,
            "zone": F.zone_of(hr_avg),
            "cadence": F._r(F._mean([r["spm"] for r in run]), 0),
            "gct_ms": F._r(F._median([r["gct"] for r in run]), 0),
            "vr_pct": F._r(F._vr_pct(run), 1),
            "walk_pct": F._r(100.0 * sum(1 for r in b if r["walk"]) / len(b), 1) if b else None,
        })
    return out


def analyze(csv_path, as_of):
    recs, lap_ids = read_csv_records(csv_path)
    if not recs:
        F._fail("CSV leer oder Schema nicht erkannt (HealthFit, ';'-Delimiter erwartet).",
                csv_path=csv_path)

    session = {}   # CSV hat keine Session-Aggregate → alles aus dem Stream (§2c)
    summary = F.build_summary(recs, session, apple_watch_fit=True)

    run_spd = F._mean([r["spd"] for r in recs if r["run"]])
    run_avg_pace_s = F._pace_from_speed(run_spd) if run_spd else None

    hrz = F.hr_zone_distribution(recs)
    # Kein FIT → keine Lap-Struktur für die Surge-Erkennung: Sample-Fallback
    # (identische Logik wie steady_z2_segment ohne Laps).
    run = [r for r in recs if r["run"]]
    trimmed, blk = F._drop_trailing_hard_block(run)
    if blk:
        seg_run, seg_label = trimmed, (f"längster steady Lauf-Abschnitt, running-only "
                                       f"(ohne {blk}-Sample-Schluss-Surge Z4/Z5)")
    else:
        seg_run, seg_label = run, "ganzer Lauf, running-only (kein harter Schluss-Surge erkannt)"

    dec = F.decoupling(seg_run, seg_label)
    pz2 = F.pace_at_z2(seg_run, session, recs=recs, label=seg_label,
                       decoupling_pct=dec.get("decoupling_pct"),
                       walk_pct=summary.get("walk_pct"),
                       z4z5_pct=hrz.get("z4_z5_pct"))

    run_date = (summary.get("start_time_utc") or "")[:10] or (as_of or "")
    pre_v3 = bool(run_date) and run_date < "2026-05-27"

    n_no_cad = sum(1 for r in recs if r["spm"] is None)
    walking_filter = "v3.5 (cad<140 & spd<2.0; stand=cad0&spd<0.5 separat)"
    if n_no_cad:
        walking_filter += (f"; ⚠️ {n_no_cad}/{len(recs)} Samples ohne Kadenz → "
                           f"Speed-only-Fallback (Gehanteil weniger belastbar)")

    splits = F.km_splits(recs)
    form = F.run_form(recs, session)
    best = F.best_values(recs)
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
    ampeln = F.v3_ampeln(summary, form, dec, seg_run, race_effort)

    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "csv_path": csv_path,
            "as_of": as_of,
            "run_date": run_date or None,
            "pre_v3": pre_v3,
            "sport": None,           # CSV trägt kein sport-Feld → Sport-Guard N/A (§2c)
            "sub_sport": None,
            "workout_name": None,    # kein Runna-Container im CSV
            "record_count": len(recs),
            "walking_filter": walking_filter,
            "parser": "healthfit-csv (FALLBACK — FIT bleibt König; Session-Aggregate stream-gerechnet)",
            "skill": "run-bundle-skill v3.14",
        },
        "summary": summary,
        "splits_km": splits,
        "splits_lap": csv_lap_splits(recs, lap_ids),
        "hr_zones": hrz,
        "hr_source_warn": F.hr_source_warn(recs),
        "run_form": form,
        "best_values": best,
        "sprint_last_60s": F.last_60s_sprint(recs, run_avg_pace_s),
        "decoupling": dec,
        "pace_at_z2": pz2,
        "v3_ampeln": ampeln,
        "topography": F.topography(recs),
    }


def main():
    ap = argparse.ArgumentParser(
        description="HealthFit-CSV-Lauf-Analyse (run-bundle-skill v3.14, Fallback-Pfad) — "
                    "Aggregate-JSON auf stdout.")
    ap.add_argument("csv_path", help="Pfad zur HealthFit-CSV")
    ap.add_argument("--as-of", required=True, metavar="YYYY-MM-DD",
                    help="Bezugsdatum (heute), z.B. 2026-06-28")
    args = ap.parse_args()
    result = analyze(args.csv_path, args.as_of)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
