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
import os
import sys
from collections import defaultdict
from datetime import date, timedelta


def _load(obj):
    """Akzeptiert EINEN Pfad/Dict ODER eine LISTE davon (heute + gestern / Range).
    Mehrere Quellen werden pro Metrik-Name gemergt: data-Arrays aneinandergehängt,
    nach Zeitstempel dedupt + sortiert. So sieht daily_signals heute UND gestern →
    der Vortag (daylight/audio `yesterday`) verhungert nie, auch wenn nur Tagesdateien
    statt eines Range-Exports gezogen wurden (Daylight-Vortag-Fix)."""
    objs = obj if isinstance(obj, (list, tuple)) else [obj]
    merged = {}
    for o in objs:
        d = o if isinstance(o, dict) else json.load(open(o, encoding="utf-8"))
        data = d.get("data", d)
        for m in data.get("metrics", []):
            name = m.get("name")
            if not name:
                continue
            slot = merged.setdefault(
                name, {"name": name, "units": m.get("units"), "data": [], "_seen": set()}
            )
            for p in m.get("data", []):
                key = str(p.get("date", ""))
                if key and key in slot["_seen"]:
                    continue          # exakter Zeitstempel-Dup über Dateien → überspringen
                slot["_seen"].add(key)
                slot["data"].append(p)
    for slot in merged.values():
        slot["data"].sort(key=lambda p: str(p.get("date", "")))  # "letzte"=jüngste global
        slot.pop("_seen", None)
    return merged


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


def _yesterday(as_of):
    """Kalender-Vortag von as_of (YYYY-MM-DD) oder None bei ungültigem as_of."""
    d = _date(as_of)
    return (d - timedelta(days=1)).isoformat() if d else None


def _present_days(merged):
    """Alle Kalendertage (YYYY-MM-DD), die irgendeine Metrik im gemergten Dict trägt."""
    days = set()
    for blk in merged.values():
        for p in blk.get("data", []):
            d = _day(p.get("date", ""))
            if d:
                days.add(d)
    return days


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
    if as_of:
        # Tag-Shift-Fix (Audit-CONFIRMED): bei gesetztem as_of KEIN Fallback auf den
        # letzten Datentag — fehlt der Tag (typischer Morgen-Check ohne Tageslicht-
        # Punkte), ist today=None statt still gestern. yesterday = exakter Kalender-
        # Vortag, nie "nächst-früherer" Tag.
        today_key = str(as_of)[:10]
        y_key = _yesterday(as_of)
    else:
        today_key = keys[-1]
        y_key = _prev_key(keys, today_key)

    def pack(k):
        if k is None or k not in d:
            return None
        return {"day": k, "minutes": round(d[k]), "ampel": _daylight_ampel(d[k])}

    return {"today": pack(today_key), "yesterday": pack(y_key),
            "history": {k: round(v) for k, v in d.items()}}


def sleep_efficiency(metrics, as_of=None):
    """Effizienz = Schlafzeit / Bett-Zeit. asleep/inBed sind in beiden Export-Typen oft 0,
    daher robust aus totalSleep + awake (= Schlaffenster, deckt sich mit inBedEnd-inBedStart).
    Mit as_of: nur Records ≤ as_of (kein Zukunfts-Leck bei Range-Exporten)."""
    m = metrics.get("sleep_analysis")
    if not m or not m.get("data"):
        return None
    rec = None
    for r in reversed(m["data"]):
        if as_of and _day(r.get("date", "")) > str(as_of)[:10]:
            continue
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


def wrist_temp(metrics, as_of=None):
    m = metrics.get("apple_sleeping_wrist_temperature")
    if not m or not m.get("data"):
        return None
    vals = [(_day(p.get("date", "")), _f(p.get("qty"))) for p in m["data"] if _f(p.get("qty")) is not None]
    if as_of:
        vals = [v for v in vals if v[0] <= str(as_of)[:10]]  # kein Zukunfts-Leck
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
    if as_of:
        # Tag-Shift-Fix: exakte Kalendertage bei gesetztem as_of (wie daylight).
        today_key = str(as_of)[:10]
        y_key = _yesterday(as_of)
    else:
        today_key = keys[-1]
        y_key = _prev_key(keys, today_key)

    def pack(k):
        if k is None or k not in peak:
            return None
        return {"day": k, "avg": round(avg[k], 1) if k in avg else None,
                "peak": round(peak[k], 1), "hint": _audio_hint(peak[k])}

    return {"today": pack(today_key), "yesterday": pack(y_key),
            "peak_history": {k: round(v, 1) for k, v in peak.items()}}


def latest_reading(metrics, name, as_of=None):
    """Letzte verfügbare Lesung einer sporadischen Metrik (z. B. vo2_max).
    Mit as_of: letzte Lesung ≤ as_of (kein Zukunfts-Leck bei Range-Exporten)."""
    m = metrics.get(name)
    if not m or not m.get("data"):
        return None
    pts = [(_day(p.get("date", "")), _f(p.get("qty"))) for p in m["data"] if _f(p.get("qty")) is not None]
    if as_of:
        pts = [p for p in pts if p[0] <= str(as_of)[:10]]
    if not pts:
        return None
    day, val = pts[-1]
    return {"value": round(val, 2), "date": day}


def dietary_water(metrics, as_of=None):
    """Wasser als TAGESSUMME (ml) für as_of (bzw. letzten geloggten Tag) —
    nicht mehr die letzte Einzel-Lesung (mehrere Logs/Tag summieren korrekt)."""
    d = _daily(metrics, "dietary_water", "sum")
    if not d:
        return None
    key = str(as_of)[:10] if as_of else sorted(d)[-1]
    v = d.get(key)
    return round(v, 1) if v is not None else None


# Health Auto Export liefert dietary_energy typischerweise in KILOJOULE — die
# Einheit wird aber aus dem units-Feld AUTODETEKTIERT (App-/Regions-Einstellung
# kann kcal liefern; blinde kJ-Annahme wäre ein 4,184×-Fehler).
_KJ_PER_KCAL = 4.184


def _energy_factor(metrics):
    """kJ→kcal-Faktor aus dem units-Feld von dietary_energy (Autodetect)."""
    units = str((metrics.get("dietary_energy") or {}).get("units") or "").lower()
    if "kcal" in units or units == "cal":
        return 1.0
    if "kj" in units or "kilojoule" in units:
        return 1.0 / _KJ_PER_KCAL
    return 1.0 / _KJ_PER_KCAL   # HAE-Default ist kJ (an echten Exporten verifiziert)

# out_key → (HAE-Metrik-Name, Faktor). ⚠️ ECHTE HAE-Feldnamen (an KW26-Daten verifiziert):
# protein/carbohydrates/total_fat/fiber/dietary_sugar (g), dietary_energy (kJ!), dietary_water (mL).
# NICHT dietary_protein/dietary_fat_total/dietary_carbohydrates — die existieren in HAE nicht.
_DIETARY_FIELDS = {
    "protein_g": ("protein", 1.0),
    "carbs_g": ("carbohydrates", 1.0),
    "fat_g": ("total_fat", 1.0),
    "fiber_g": ("fiber", 1.0),
    "sugar_g": ("dietary_sugar", 1.0),
    "kcal": ("dietary_energy", 1.0 / _KJ_PER_KCAL),   # HAE-Einheit kJ → kcal
    "water_ml": ("dietary_water", 1.0),
}


def dietary_macros(metrics, as_of=None):
    """Tages-Makros für HEUTE + GESTERN aus den HAE-dietary_*-Feldern.

    Per-Tag-Summe via `_daily(sum)` (mehrere Meal-Einträge/Tag → Tagessumme).
    **`today`/`yesterday` sind EXAKTE Kalendertage** (as_of bzw. as_of−1) — kein
    „nächst-früherer" Fallback: ist der Tag nicht geloggt, kommt `None` zurück
    (Logging ist intermittent, oft Fr–So leer). NIE 0 annehmen. `logged_days`
    listet, an welchen Tagen überhaupt Makros existieren (für „zuletzt geloggt").
    """
    sums, daykeys = {}, set()
    for out_key, (hae_name, factor) in _DIETARY_FIELDS.items():
        d = _daily(metrics, hae_name, "sum")
        if out_key == "kcal":
            factor = _energy_factor(metrics)   # Einheiten-Autodetect statt blinder kJ-Annahme
        sums[out_key] = (d, factor)
        daykeys |= set(d.keys())
    if not daykeys:
        return None
    keys = sorted(daykeys)
    today_key = str(as_of)[:10] if as_of else keys[-1]
    y_key = _yesterday(as_of) if as_of else (keys[-2] if len(keys) >= 2 else None)

    def pack(k):
        if k is None:
            return None
        rec, any_val = {"day": k}, False
        for out_key, (d, factor) in sums.items():
            if k in d:
                rec[out_key] = round(d[k] * factor, 1)
                any_val = True
            else:
                rec[out_key] = None
        return rec if any_val else None

    return {"today": pack(today_key), "yesterday": pack(y_key), "logged_days": keys}


def all_signals(json_obj, as_of=None, data_dir=None):
    """Alle Tag-Signale. **Vortag-Härtung (Daylight-/Audio-Glitch):** ist as_of gesetzt
    und der Kalender-Vortag fehlt in den geladenen Daten, wird automatisch
    `<data_dir>/HealthAutoExport-<gestern>.json` nachgeladen + gemergt (nicht-fatal,
    wenn die Datei fehlt). `data_dir` default = Verzeichnis des ersten String-Pfads.
    So resolved `yesterday` auch dann, wenn der Aufrufer nur die Heute-Datei übergibt."""
    objs = list(json_obj) if isinstance(json_obj, (list, tuple)) else [json_obj]
    m = _load(objs)
    if as_of:
        y = _yesterday(as_of)
        if y and y not in _present_days(m):
            dd = data_dir
            if dd is None:
                for o in objs:
                    if isinstance(o, str):
                        dd = os.path.dirname(o) or "."
                        break
            if dd is not None:
                cand = os.path.join(dd, f"HealthAutoExport-{y}.json")
                if os.path.exists(cand) and cand not in objs:
                    objs = objs + [cand]
                    m = _load(objs)
    return {
        "daylight": daylight_minutes(m, as_of),
        "sleep_efficiency": sleep_efficiency(m, as_of),
        "wrist_temp": wrist_temp(m, as_of),
        "audio": audio_context(m, as_of),
        "vo2_max": latest_reading(m, "vo2_max", as_of),
        "cardio_recovery": latest_reading(m, "cardio_recovery", as_of),
        "dietary_water_ml": dietary_water(m, as_of),
        "dietary": dietary_macros(m, as_of),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Tag-Signale aus HealthAutoExport-JSON(s). HEUTE + (optional) GESTERN/Range "
        "übergeben — mehrere Dateien werden gemergt, damit der Vortag nie verhungert."
    )
    ap.add_argument("hae", nargs="+", help="HAE-JSON-Pfad(e): HEUTE zuerst, dann optional GESTERN bzw. ein Range-Export")
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="Bezugstag YYYY-MM-DD (pinnt today/yesterday); Default = letzter Tag im Export")
    ap.add_argument("--data-dir", dest="data_dir", default=None,
                    help="Verzeichnis für den Vortag-Auto-Nachzug (default = Ordner der ersten HAE-Datei)")
    args = ap.parse_args()
    print(json.dumps(all_signals(args.hae, as_of=args.as_of, data_dir=args.data_dir),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
