#!/usr/bin/env python3
"""
parse_workout.py — Runna-/strukturierte-Workout-Parser (run-bundle-skill v3.8+)

ZWECK
-----
Strukturierte Läufe (Runna) tragen die VORSCHRIFT in der FIT:
  - `workout`        → Name (wkt_name) + Anzahl Steps
  - `workout_step`   → pro Schritt: Intensität, Dauer (Distanz/Zeit), Target (Speed-Band/HR-Band)
  - `lap`            → Ist-Ausführung, pro Step ein Lap (lap_trigger distance/time)

Dieser Helper:
  1. rekonstruiert die Vorschrift AUS DER FIT (auch ohne gepasteten Runna-Text),
     inkl. Repeat-Expansion und Speed-Band → Pace-Band-Konvertierung,
  2. mappt die Ist-Laps 1:1 auf die expandierte Vorschrift,
  3. rechnet Soll-Ist-Compliance pro Rep (Pace im Band? HR pro Lap aus records),
  4. liefert eine fertige Tabelle + Verdikt-Bausteine für den Report.

WICHTIG (Skill-Regel): Ein `✅` in Runnas gepastetem Plan-Text ist DEKO, KEIN
Compliance-/Absolviert-Signal. Wahrheit = FIT-Ist. Dieser Helper liest nur die FIT.

CLI:  python parse_workout.py <datei.fit>
API:  from parse_workout import parse_workout; res = parse_workout(path)
"""

import sys

INTENSITY = {0: "active", 1: "rest", 2: "warmup", 3: "cooldown", 4: "recovery"}


def _pace_str(sec_per_km):
    if not sec_per_km or sec_per_km <= 0:
        return "-"
    return f"{int(sec_per_km // 60)}:{int(round(sec_per_km % 60)):02d}/km"


def _iname(v):
    return INTENSITY.get(v, v if isinstance(v, str) else str(v))


def _emit(d):
    """Ein workout_step-Dict → normalisierter Vorschrift-Eintrag."""
    dt = d.get("duration_type")
    if dt == "distance":
        dur = ("distance", d.get("duration_distance"))
    elif dt == "time":
        dur = ("time", d.get("duration_time"))
    else:
        dur = ("open", None)

    tt = d.get("target_type")
    target = None
    if tt == "speed" and d.get("custom_target_speed_low"):
        lo = d.get("custom_target_speed_low")   # m/s, langsam
        hi = d.get("custom_target_speed_high")  # m/s, schnell
        # hohe Speed = schnellere (kleinere) Pace
        target = ("pace_band", 1000.0 / hi, 1000.0 / lo)
    elif tt == "heart_rate" and d.get("custom_target_heart_rate_low"):
        target = ("hr_band", d.get("custom_target_heart_rate_low"),
                  d.get("custom_target_heart_rate_high"))

    return {
        "name": d.get("wkt_step_name"),
        "intensity": _iname(d.get("intensity")),
        "dur": dur,
        "target": target,
        "_src_idx": d.get("message_index"),
    }


def reconstruct_prescription(fit):
    """wkt_name + FLACHE Vorschrift-Sequenz (Repeats expandiert)."""
    name = None
    for m in fit.get_messages("workout"):
        for fld in m:
            if fld.name == "wkt_name" and fld.value is not None:
                name = fld.value

    raw = {}
    for m in fit.get_messages("workout_step"):
        d = {fld.name: fld.value for fld in m}
        raw[d.get("message_index")] = d
    if not raw:
        return name, []

    idxs = sorted(raw)
    flat = []
    for idx in idxs:
        d = raw[idx]
        if d.get("duration_type") == "repeat_until_steps_cmplt":
            S = d.get("duration_step")              # Wiederhol-Start-Index
            K = d.get("repeat_steps") or 1          # Gesamt-Iterationen
            body = [j for j in idxs if S is not None and S <= j <= idx - 1]
            # Body wurde im Vorwärtslauf bereits 1× emittiert → (K-1)× nachlegen
            for _ in range(max(0, K - 1)):
                for j in body:
                    flat.append(_emit(raw[j]))
        else:
            flat.append(_emit(d))
    return name, flat


def _lap_actuals(fit):
    """Laps mit Ist-Werten; HR pro Lap aus records (Laps haben oft keine avg_heart_rate)."""
    laps = []
    for m in fit.get_messages("lap"):
        d = {fld.name: fld.value for fld in m}
        spd = d.get("enhanced_avg_speed") or d.get("avg_speed")
        laps.append({
            "trigger": d.get("lap_trigger"),
            "intensity": _iname(d.get("intensity")),
            "dist": d.get("total_distance"),
            "time": d.get("total_timer_time") or d.get("total_elapsed_time"),
            "speed": spd,
            "pace_sec": (1000.0 / spd) if spd else None,
            "hr_avg": d.get("avg_heart_rate"),
            "hr_max": d.get("max_heart_rate"),
            "start_time": d.get("start_time"),
        })

    # HR pro Lap aus records nachrechnen, falls Lap keine HR trägt
    if any(l["hr_avg"] is None for l in laps) and laps:
        recs = []
        for m in fit.get_messages("record"):
            d = {fld.name: fld.value for fld in m}
            if d.get("timestamp") is not None and d.get("heart_rate") is not None:
                recs.append((d["timestamp"], d["heart_rate"]))
        recs.sort()
        bounds = [l["start_time"] for l in laps if l["start_time"] is not None]
        if len(bounds) == len(laps):
            for i, l in enumerate(laps):
                lo = l["start_time"]
                hi = laps[i + 1]["start_time"] if i + 1 < len(laps) else None
                hrs = [hr for (ts, hr) in recs if ts >= lo and (hi is None or ts < hi)]
                if hrs and l["hr_avg"] is None:
                    l["hr_avg"] = round(sum(hrs) / len(hrs))
                    l["hr_max"] = max(hrs)
    return laps


def _compliance(actual_pace, band):
    """band = (lo_sec_fast, hi_sec_slow). ✅ im Band, 🟡 ±5 %, sonst ❌."""
    if actual_pace is None or band is None:
        return "—"
    fast, slow = band[1], band[2]
    if fast <= actual_pace <= slow:
        return "✅ im Band"
    tol = 0.05 * ((fast + slow) / 2)
    if (fast - tol) <= actual_pace <= (slow + tol):
        return "🟡 knapp daneben"
    return "❌ schneller" if actual_pace < fast else "❌ langsamer"


def parse_workout(path):
    from fitparse import FitFile
    fit = FitFile(path)
    name, flat = reconstruct_prescription(fit)
    laps = _lap_actuals(fit)
    structured = len(flat) > 0

    rows = []
    # Lap↔Step-Mismatch: weichen Vorschrift-Steps und Ist-Laps in der Anzahl ab
    # (übersprungene Steps, manueller Lap, abgebrochenes Workout), ist die
    # 1:1-Index-Zuordnung ab der Abweichung POTENZIELL VERSCHOBEN — Warn-Flag
    # statt stiller Fehlzuordnung (Audit-CONFIRMED).
    mismatch = structured and (len(flat) != len(laps))
    if structured:
        n = min(len(flat), len(laps))
        rep = 0
        for i in range(n):
            p, l = flat[i], laps[i]
            band = p["target"] if (p["target"] and p["target"][0] == "pace_band") else None
            soll = (_pace_str(band[1]) + "–" + _pace_str(band[2])) if band else "—"
            comp = _compliance(l["pace_sec"], band) if p["intensity"] == "active" else "—"
            if p["intensity"] == "active" and band:
                rep += 1
            rows.append({
                "lap": i, "phase": p["name"] or p["intensity"],
                "intensity": p["intensity"],
                "soll": soll, "ist": _pace_str(l["pace_sec"]),
                "hr": l["hr_avg"], "dist": l["dist"], "comp": comp,
            })
    return {
        "name": name, "structured": structured,
        "prescription": flat, "laps": laps, "rows": rows,
        "lap_count": len(laps), "step_count": len(flat),
        "lap_step_mismatch": mismatch,
        "mismatch_note": (f"⚠️ {len(flat)} Vorschrift-Steps vs {len(laps)} Ist-Laps — "
                          "Index-Zuordnung ab der Abweichung potenziell verschoben, "
                          "Compliance-Tabelle mit Vorsicht lesen."
                          if mismatch else None),
        "manual": (not structured) and any(l["trigger"] == "manual" for l in laps),
    }


def format_table(res):
    if not res["structured"]:
        kind = "manuelle Laps (User-Splits)" if res["manual"] else "keine Lap-Struktur"
        return f"Kein strukturiertes Workout — {kind} ({res['lap_count']} Laps)."
    out = [f"🗓️ **{res['name'] or 'Workout'}** — Soll-Ist pro Lap "
           f"({res['step_count']} Vorschrift-Segmente, {res['lap_count']} Ist-Laps; ✅-Text = Deko, FIT = Wahrheit)"]
    if res.get("mismatch_note"):
        out.append("")
        out.append(res["mismatch_note"])
    out += ["", "| Lap | Phase | Soll | Ist | HR | Compliance |",
            "|---|---|---|---|---|---|"]
    for r in res["rows"]:
        out.append(f"| {r['lap']} | {r['phase']} | {r['soll']} | {r['ist']} | "
                   f"{r['hr'] if r['hr'] is not None else '—'} | {r['comp']} |")
    misses = [r for r in res["rows"] if r["comp"].startswith("❌")]
    if misses:
        out.append("")
        out.append("**Reps außerhalb Target:** " +
                   "; ".join(f"{m['phase']} → {m['ist']} ({m['comp']})" for m in misses))
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    res = parse_workout(sys.argv[1])
    print(f"Workout: {res['name']} · strukturiert={res['structured']} · "
          f"manual={res['manual']} · {res['step_count']} Steps / {res['lap_count']} Laps\n")
    print(format_table(res))


if __name__ == "__main__":
    main()
