#!/usr/bin/env python3
"""
daily_signals.py — Tag-Signale aus HealthAutoExport-JSON (daily-check v0.11+)

Extrahiert deterministisch die in v0.11 ergänzten Metriken:
- time_in_daylight ........ Minuten/Tag (Circadian-Hebel) + Ampel
- Schlaf-Effizienz ........ asleep / inBed der letzten Nacht
- Schlaf-Handgelenk-Temp .. letzter Wert + Rolling-Baseline (Mittel der Vornächte)
                            + Abweichung + Flag (Krankheit/Hitze-Last)
- Umgebungs-Audio ......... Ø + Peak je Tag + NEUTRALER Lautstärke-Hinweis
- VO2max / cardio_recovery  LETZTE verfügbare Lesung + Datum (sporadisch!)
- dietary_water ........... letzter Wert (ml)

ROBUSTHEIT: Fehlt eine Metrik im Export, kommt None zurück — der Skill fällt auf
userMemories zurück und zeigt Abwesenheit NIE als Wert oder als Verschlechterung.

WICHTIG (Narrativ-Regel lebt im SKILL.md, nicht hier): Der Audio/Tag-Kontext ist nur
ein MÖGLICHES Muster über mehrere Metriken — vorsichtig vermuten, NIE moralisieren.
Lange abends unterwegs am Wochenende = ein Leben, kein Defizit.

CLI:  python daily_signals.py <healthautoexport.json>
API:  from daily_signals import all_signals; sig = all_signals(json_path_or_obj)
"""
import json
import sys
from collections import defaultdict
from datetime import date, timedelta


def _load(obj):
    d = obj if isinstance(obj, dict) else json.load(open(obj, encoding="utf-8"))
    data = d.get("data", d)
    return {m["name"]: m for m in data.get("metrics", [])}


def _day(s):
    return str(s)[:10]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _daily(metrics, name, agg="sum"):
    m = metrics.get(name)
    if not m:
        return {}
    by = defaultdict(list)
    for p in m.get("data", []):
        q = p.get("qty")
        if q is None:
            q = p.get("Avg")
        q = _f(q)
        if q is not None:
            by[_day(p.get("date", ""))].append(q)
    out = {}
    for k, v in by.items():
        if not v:
            continue
        out[k] = sum(v) if agg == "sum" else (max(v) if agg == "max" else sum(v) / len(v))
    return dict(sorted(out.items()))


def _date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _prev_key(keys, today_key):
    """Kalender-Vortag von today_key, falls in keys; sonst nächst-früherer vorhandener Tag."""
    td = _date(today_key)
    if td is None:
        return keys[-2] if len(keys) >= 2 else None
    y = (td - timedelta(days=1)).isoformat()
    if y in keys:
        return y
    earlier = [k for k in keys if _date(k) and _date(k) < td]
    return earlier[-1] if earlier else None


def _daylight_ampel(mins):
    if mins >= 120:
        return "🟢"
    if mins >= 60:
        return "🟡"
    if mins >= 30:
        return "🟠"
    return "🔴"


def daylight_minutes(metrics, as_of=None):
    d = _daily(metrics, "time_in_daylight", "sum")
    if not d:
        return None
    keys = list(d.keys())
    today_key = str(as_of)[:10] if as_of else keys[-1]
    if today_key not in d:
        today_key = keys[-1]
    y_key = _prev_key(keys, today_key)

    def pack(k):
        if k is None or k not in d:
            return None
        return {"day": k, "minutes": round(d[k]), "ampel": _daylight_ampel(d[k])}

    return {"today": pack(today_key), "yesterday": pack(y_key),
            "history": {k: round(v) for k, v in d.items()}}


def sleep_efficiency(metrics):
    """Effizienz = Schlafzeit / Bett-Zeit. asleep/inBed sind in beiden Export-Typen oft 0,
    daher robust aus totalSleep + awake (= Schlaffenster, deckt sich mit inBedEnd-inBedStart)."""
    m = metrics.get("sleep_analysis")
    if not m or not m.get("data"):
        return None
    rec = None
    for r in reversed(m["data"]):
        if _f(r.get("totalSleep")):
            rec = r
            break
    if not rec:
        return None
    total = _f(rec.get("totalSleep"))
    awake = _f(rec.get("awake")) or 0.0
    asleep = _f(rec.get("asleep"))
    inbed = _f(rec.get("inBed"))
    if asleep and inbed and inbed > 0:          # bevorzugt echte Felder, falls befüllt
        t_asleep, t_bed = asleep, inbed
    else:                                        # Fallback: Schlaffenster aus totalSleep+awake
        t_asleep, t_bed = total, total + awake
    if not t_bed or t_bed <= 0:
        return None
    eff = 100 * t_asleep / t_bed
    amp = "🟢" if eff >= 90 else ("🟡" if eff >= 85 else ("🟠" if eff >= 75 else "🔴"))
    return {"efficiency": round(eff, 1), "asleep_h": round(t_asleep, 2),
            "inbed_h": round(t_bed, 2), "awake_h": round(awake, 2), "ampel": amp}


def wrist_temp(metrics):
    m = metrics.get("apple_sleeping_wrist_temperature")
    if not m or not m.get("data"):
        return None
    vals = [(_day(p.get("date", "")), _f(p.get("qty"))) for p in m["data"] if _f(p.get("qty")) is not None]
    if not vals:
        return None
    latest_day, latest = vals[-1]
    prior = [v for _, v in vals[:-1]][-28:]   # rollendes 28-Nächte-Fenster (recent baseline)
    baseline = sum(prior) / len(prior) if prior else latest
    dev = latest - baseline
    return {"latest": round(latest, 2), "baseline": round(baseline, 2),
            "deviation": round(dev, 2), "flag": dev > 0.4, "n_nights": len(vals),
            "baseline_nights": len(prior), "baseline_ok": len(prior) >= 5}


def _audio_hint(peak):
    # NEUTRAL — nur grobe Lautstärke-Lage, KEIN Urteil. Schwellen aus Wochen-Daten
    # kalibriert (Indoor-Tage Peak ~70-78 dB, Outdoor-Event-Tag 90,5 dB).
    if peak >= 88:
        return "laut"           # viel los möglich
    if peak >= 82:
        return "erhöht"         # evtl. unterwegs/sozial
    if peak >= 78:
        return "leicht erhöht"
    return "ruhig"              # Indoor-typisch


def audio_context(metrics, as_of=None):
    avg = _daily(metrics, "environmental_audio_exposure", "avg")
    peak = _daily(metrics, "environmental_audio_exposure", "max")
    if not peak:
        return None
    keys = list(peak.keys())
    today_key = str(as_of)[:10] if as_of else keys[-1]
    if today_key not in peak:
        today_key = keys[-1]
    y_key = _prev_key(keys, today_key)

    def pack(k):
        if k is None or k not in peak:
            return None
        return {"day": k, "avg": round(avg[k], 1) if k in avg else None,
                "peak": round(peak[k], 1), "hint": _audio_hint(peak[k])}

    return {"today": pack(today_key), "yesterday": pack(y_key),
            "peak_history": {k: round(v, 1) for k, v in peak.items()}}


def latest_reading(metrics, name):
    """Letzte verfügbare Lesung einer sporadischen Metrik (z. B. vo2_max)."""
    m = metrics.get(name)
    if not m or not m.get("data"):
        return None
    pts = [(_day(p.get("date", "")), _f(p.get("qty"))) for p in m["data"] if _f(p.get("qty")) is not None]
    if not pts:
        return None
    day, val = pts[-1]
    return {"value": round(val, 2), "date": day}


def dietary_water(metrics):
    r = latest_reading(metrics, "dietary_water")
    return r["value"] if r else None


def all_signals(json_obj, as_of=None):
    m = _load(json_obj)
    return {
        "daylight": daylight_minutes(m, as_of),
        "sleep_efficiency": sleep_efficiency(m),
        "wrist_temp": wrist_temp(m),
        "audio": audio_context(m, as_of),
        "vo2_max": latest_reading(m, "vo2_max"),
        "cardio_recovery": latest_reading(m, "cardio_recovery"),
        "dietary_water_ml": dietary_water(m),
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    print(json.dumps(all_signals(sys.argv[1]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
