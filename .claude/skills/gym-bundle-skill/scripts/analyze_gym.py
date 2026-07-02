#!/usr/bin/env python3
"""
analyze_gym.py — DIE Gym-Analyse-Engine des gym-bundle-skill (v2.0).

ZWECK
-----
Vorher ein Referenz-Stub (pandas, kein CLI-Kontrakt, keine Validierung).
Jetzt die deterministische Engine nach analyze_run_fit-Muster: parst die
Übungs-Text-Message + die HealthFit-Segmente-/Master-CSV, rechnet Tonnage,
Muskelgruppen-Verteilung, PR-Detection gegen baselines.md, HR-Profil +
Belastungs-Score pro Übung, Bedtime-Ampel — und liefert ausschließlich
AGGREGATE (kompaktes JSON) auf stdout. NIE Roh-Sample-Zeilen (§0-Kernregel).
Jede Zahl/Ampel kommt aus DIESEM Script; der Report übersetzt nur
(Verdict-Kontrakt, Entscheidung #2).

INPUTS
------
--exercises <txt|->   Übungs-Text des Athleten (Zeilen "3030 - Beinpresse -
                      80, 85, 90, 95 kg (max)"; Notationen siehe SKILL §3).
--segments <csv>      HealthFit-CSV: entweder die *-segmente.csv (1 Zeile/
                      Segment) ODER die Master-CSV (4-s-Sampling mit Lap-
                      Spalte) — Format wird autodetektiert. Optional
                      (Text-Only-Modus ohne HR).
--baselines <md>      ./data/baselines.md (Drive-Personal-Folder) für die
                      PR-Detection. Optional (dann pr_status="no_baseline").
--as-of YYYY-MM-DD    Bezugstag (PFLICHT — deterministische Pipeline).
--days-since-last N   Tage seit letzter Gym-Session → Re-Entry-80%-Regel.

CLI:  python3 analyze_gym.py --exercises uebungen.txt --segments seg.csv \
          --baselines ./data/baselines.md --as-of 2026-07-02
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime

SCHEMA_VERSION = "2.0"

# ── Ampel-/Band-Konstanten (SSoT: lib/constants.py — consistency-gepinnt) ────
LEG_BAND_PCT = (50, 65)
UPPER_BAND_PCT = (25, 35)
CORE_BAND_PCT = (8, 15)
GYM_END_GREEN = "21:30"     # 🟢 ≤21:30 (V3-Slot Do)
GYM_END_YELLOW = "22:00"    # 🟡 ≤22:00
GYM_END_ORANGE = "22:30"    # 🟠 ≤22:30 · 🔴 danach
REENTRY_GAP_DAYS = 7
REENTRY_FACTORS = (0.8, 0.9, 1.0)
DEFAULT_REPS = 10

# Generische Geräte-Referenz-Map (SKILL §4 — Struktur/Methode; die für das
# jeweilige Gym gültige Map lebt in athlete.md/Drive und kann via --device-map
# überschrieben werden).
DEVICE_MAP = {
    "3030": ("Beinpresse", "Beine"),
    "3020": ("Latzug", "Oberkörper"),
    "5012": ("Rücken", "Oberkörper"),
    "3008": ("Klappsitz", "Core"),
    "3098": ("Bizeps Horizontal", "Oberkörper"),
    "5011": ("Adduktion/Abduktion", "Beine"),
    "3225": ("Rotation", "Core"),
    "3018": ("Waden", "Beine"),
    "3032": ("Schulterpresse", "Oberkörper"),
    "3036": ("Dip", "Oberkörper"),
    "5013": ("Beinstrecker/Beinbeuger", "Beine"),
}

# Übungsname → Muskelgruppe (Fallback, wenn Geräte-Nr. unbekannt/fehlt).
_NAME_GROUPS = (
    ("Beine", ("beinpresse", "waden", "beinbeuger", "beinstrecker", "adduktion",
               "abduktion", "squat", "kniebeuge", "wadenheben")),
    ("Core", ("klappsitz", "rotation", "core", "bauch", "crunch", "plank")),
    ("Oberkörper", ("latzug", "rücken", "ruecken", "bizeps", "trizeps", "schulter",
                    "dip", "brust", "press", "row", "rudern", "pull")),
)


def _fail(msg, **extra):
    out = {"ok": False, "error": msg}
    out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(2)


def _f(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _r(x, nd=1):
    return round(x, nd) if isinstance(x, (int, float)) else None


# ════════════════════════════════════════════════════════════════════════
#  1) Übungs-Text-Parser (SKILL §3 — tolerant, aber deterministisch)
# ════════════════════════════════════════════════════════════════════════
_SET_TOKEN = re.compile(r"(?:(\d+)\s*[×x]\s*)?(\d+(?:[.,]\d+)?)")
_REPS_NOTE = re.compile(r"^(\d+)\s*x$", re.IGNORECASE)


def parse_exercise_line(line):
    """Eine Zeile '3030 - Beinpresse - 80, 85, 90, 95 kg (max)' →
    {device, name, sets:[{weight, reps}], notes, pr_claimed} oder None."""
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    parts = [p.strip() for p in re.split(r"\s+-\s+|\s+–\s+", raw) if p.strip()]
    if len(parts) < 2:
        return None
    if len(parts) >= 3 and re.fullmatch(r"\d{3,5}", parts[0]):
        device, name, weights_part = parts[0], parts[1], " - ".join(parts[2:])
    else:
        device, name, weights_part = None, parts[0], " - ".join(parts[1:])

    notes = re.findall(r"\(([^)]*)\)", weights_part)
    weights_clean = re.sub(r"\([^)]*\)", " ", weights_part)
    weights_clean = re.sub(r"\bkg\b", " ", weights_clean, flags=re.IGNORECASE)

    sets = []
    for m in _SET_TOKEN.finditer(weights_clean):
        n = int(m.group(1)) if m.group(1) else 1
        w = float(m.group(2).replace(",", "."))
        for _ in range(n):
            sets.append({"weight": w, "reps": DEFAULT_REPS})
    if not sets:
        return None

    pr_claimed = any(("max" in n.lower() or "holy" in n.lower() or "!!!" in n)
                     for n in notes)
    for n in notes:                       # "(6x)" → Reps-Override für den LETZTEN Satz
        m = _REPS_NOTE.match(n.strip())
        if m:
            sets[-1]["reps"] = int(m.group(1))

    return {"device": device, "name": name, "sets": sets,
            "notes": notes, "pr_claimed": pr_claimed}


def parse_exercises(text):
    out = []
    for line in text.splitlines():
        ex = parse_exercise_line(line)
        if ex:
            out.append(ex)
    return out


def classify_group(device, name, device_map):
    if device and device in device_map:
        return device_map[device][1]
    low = (name or "").lower()
    for group, keys in _NAME_GROUPS:
        if any(k in low for k in keys):
            return group
    return "Unklassifiziert"


# ════════════════════════════════════════════════════════════════════════
#  2) Segmente-CSV-Reader (autodetektiert: Segment-Zeilen ODER Master-Sampling)
# ════════════════════════════════════════════════════════════════════════
def _ts(v):
    if not v:
        return None
    s = str(v).strip().replace("Z", "+00:00")
    for cand in (s, s.replace(" ", "T", 1)):
        try:
            return datetime.fromisoformat(cand)
        except ValueError:
            continue
    return None


def _find_col(headers, *keyword_sets):
    """Erste Spalte, deren Name ALLE Keywords eines Sets enthält (lowercase)."""
    for kws in keyword_sets:
        for h in headers:
            hl = (h or "").lower()
            if all(k in hl for k in kws):
                return h
    return None


def read_segments(csv_path):
    """→ Liste [{idx, dur_s, hr_avg, hr_max, start, end}] (chronologisch).

    Autodetect: (a) Master-CSV (Sampling mit Lap-Spalte + Heart Rate je Zeile)
    → Aggregation pro Lap; (b) Segmente-CSV (1 Zeile/Segment mit Ø-/Max-HR).
    """
    with open(csv_path, encoding="utf-8", errors="replace", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=delim)
        headers = reader.fieldnames or []
        rows = list(reader)
    if not rows:
        return []

    hr_col = _find_col(headers, ("heart rate",), ("herzfrequenz",), ("hr",))
    lap_col = _find_col(headers, ("lap",), ("segment",), ("runde",))
    iso_col = _find_col(headers, ("iso8601",), ("zeit",), ("time",), ("start",))

    # (a) Master-Sampling: HR pro Zeile + Lap-Spalte → pro Lap aggregieren.
    hr_vals = [_f(r.get(hr_col)) for r in rows[:50]] if hr_col else []
    sampling = lap_col and hr_col and sum(1 for v in hr_vals if v is not None) >= 10
    if sampling:
        groups, order = {}, []
        for r in rows:
            key = (r.get(lap_col) or "").strip()
            if not key:
                continue
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(r)
        segs = []
        for i, key in enumerate(order):
            g = groups[key]
            hrs = [_f(r.get(hr_col)) for r in g]
            hrs = [h for h in hrs if h is not None]
            t0 = _ts(g[0].get(iso_col)) if iso_col else None
            t1 = _ts(g[-1].get(iso_col)) if iso_col else None
            dur = (t1 - t0).total_seconds() if (t0 and t1) else None
            segs.append({"idx": i + 1, "dur_s": _r(dur, 0),
                         "hr_avg": _r(sum(hrs) / len(hrs), 1) if hrs else None,
                         "hr_max": _r(max(hrs), 0) if hrs else None,
                         "start": t0.isoformat() if t0 else None,
                         "end": t1.isoformat() if t1 else None})
        return segs

    # (b) Segment-Zeilen: Ø-/Max-HR + Dauer als Spalten.
    avg_col = _find_col(headers, ("durchschnitt", "herz"), ("avg", "heart"),
                        ("ø", "herz"), ("herzfrequenz",), ("avg", "hr"))
    max_col = _find_col(headers, ("max", "herz"), ("max", "heart"), ("max", "hr"))
    dur_col = _find_col(headers, ("dauer",), ("duration",), ("zeit", "sek"))
    start_col = _find_col(headers, ("start",), ("beginn",))
    end_col = _find_col(headers, ("ende",), ("end",), ("stop",))
    segs = []
    for i, r in enumerate(rows):
        dur = _f(r.get(dur_col)) if dur_col else None
        t0 = _ts(r.get(start_col)) if start_col else None
        t1 = _ts(r.get(end_col)) if end_col else None
        if dur is None and t0 and t1:
            dur = (t1 - t0).total_seconds()
        segs.append({"idx": i + 1, "dur_s": _r(dur, 0),
                     "hr_avg": _f(r.get(avg_col)) if avg_col else None,
                     "hr_max": _f(r.get(max_col)) if max_col else None,
                     "start": t0.isoformat() if t0 else None,
                     "end": t1.isoformat() if t1 else None})
    return segs


# ════════════════════════════════════════════════════════════════════════
#  3) Segment↔Übungs-Mapping (SKILL §5 — deterministisch)
# ════════════════════════════════════════════════════════════════════════
def map_segments(segments, n_exercises):
    """→ (mapping_liste_pro_übung | None, meta). Kein Raten bei größerer
    Abweichung — dann ehrlich unmapped (HR pro Übung = None) + Hinweis."""
    n_seg = len(segments)
    if n_seg == 0 or n_exercises == 0:
        return None, {"mode": "none", "n_segments": n_seg, "warmup": None,
                      "note": "keine Segmente/Übungen"}
    if n_seg == n_exercises + 1:
        return segments[1:], {"mode": "warmup+1:1", "n_segments": n_seg,
                              "warmup": segments[0], "note": None}
    if n_seg == n_exercises:
        return list(segments), {"mode": "1:1", "n_segments": n_seg,
                                "warmup": None, "note": None}
    if n_seg == n_exercises + 2:
        return segments[1:-1], {"mode": "warmup+1:1+cooldown", "n_segments": n_seg,
                                "warmup": segments[0], "note": "letztes Segment = Cool-Down"}
    return None, {"mode": "unmatched", "n_segments": n_seg, "warmup": None,
                  "note": (f"{n_seg} Segmente vs {n_exercises} Übungen — kein sicheres "
                           "Mapping; HR pro Übung entfällt (kein Raten, SKILL §5.6)")}


# ════════════════════════════════════════════════════════════════════════
#  4) PR-Detection gegen baselines.md (SKILL §6)
# ════════════════════════════════════════════════════════════════════════
_PR_LINE = re.compile(r"([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß /()+-]*?)\s*[:—-]?\s*"
                      r"(\d+(?:[.,]\d+)?)\s*kg", re.UNICODE)


def parse_baselines(md_text):
    """baselines.md → {übungsname_lower: pr_kg}. Nimmt den Gym-PR-Abschnitt,
    fällt sonst auf alle '<Name> … <N> kg'-Zeilen zurück (Format ist user-owned
    → tolerant parsen, aber deterministisch: erster Treffer pro Name gewinnt)."""
    text = md_text
    m = re.search(r"^#{1,6}[^\n]*gym[^\n]*pr[^\n]*$", md_text,
                  re.IGNORECASE | re.MULTILINE)
    if m:
        rest = md_text[m.end():]
        nxt = re.search(r"^#{1,6}\s", rest, re.MULTILINE)
        text = rest[:nxt.start()] if nxt else rest
    prs = {}
    for name, val in _PR_LINE.findall(text):
        key = name.strip().lower()
        if key and key not in prs:
            prs[key] = float(val.replace(",", "."))
    return prs


def match_pr(name, prs):
    """Übungsname ↔ Baseline-Key (Substring in beide Richtungen, normalisiert)."""
    low = name.strip().lower()
    if low in prs:
        return low
    for key in prs:
        if key in low or low in key:
            return key
    return None


# ════════════════════════════════════════════════════════════════════════
#  5) Ampeln (Bedtime §12, Volumen §7)
# ════════════════════════════════════════════════════════════════════════
def bedtime_ampel(end_iso):
    """Session-Ende (lokale Zeit im ISO-String) → Do-Gym-Bedtime-Ampel."""
    if not end_iso:
        return {"end": None, "ampel": None, "label": "kein Endzeitpunkt in den Daten"}
    hhmm = str(end_iso)[11:16]
    if not re.fullmatch(r"\d{2}:\d{2}", hhmm):
        return {"end": end_iso, "ampel": None, "label": "Endzeit nicht lesbar"}
    if hhmm <= GYM_END_GREEN:
        amp, label = "🟢", "im V3-Slot (≤21:30)"
    elif hhmm <= GYM_END_YELLOW:
        amp, label = "🟡", "leicht überzogen, Bedtime-Risk"
    elif hhmm <= GYM_END_ORANGE:
        amp, label = "🟠", "Bedtime-Risk real, Casein-Timing schwierig"
    else:
        amp, label = "🔴", "V3-Bruch — HRV-Crash-Risiko, Sleep-Compliance unmöglich"
    return {"end": hhmm, "ampel": amp, "label": label}


def _band_ampel(pct, band):
    if pct is None:
        return None
    lo, hi = band
    return "🟢" if lo <= pct <= hi else "🟡"


# ════════════════════════════════════════════════════════════════════════
#  6) Analyse
# ════════════════════════════════════════════════════════════════════════
def analyze(exercises_text, segments_path=None, baselines_text=None, as_of=None,
            days_since_last=None, device_map=None):
    device_map = device_map or DEVICE_MAP
    exercises = parse_exercises(exercises_text)
    if not exercises:
        _fail("Keine Übungen im Text erkannt — erwartet Zeilen wie "
              "'3030 - Beinpresse - 80, 85, 90, 95 kg'.")

    segments = read_segments(segments_path) if segments_path else []
    mapped, map_meta = map_segments(segments, len(exercises))

    prs = parse_baselines(baselines_text) if baselines_text else {}

    # Re-Entry (SKILL §11): >7 Tage Pause → 80 %-Regel für Session 1.
    reentry = None
    if days_since_last is not None and days_since_last > REENTRY_GAP_DAYS:
        reentry = {"active": True, "days_since_last": days_since_last,
                   "target_factor": REENTRY_FACTORS[0],
                   "note": "Re-Entry-Session: Ziel = 80 % der PRs, kein PR-Versuch"}

    # Warmup-Baseline für den Belastungs-Score (HR-Peak − Baseline).
    hr_baseline = None
    if map_meta.get("warmup") and map_meta["warmup"].get("hr_avg") is not None:
        hr_baseline = map_meta["warmup"]["hr_avg"]
    elif segments:
        vals = [s["hr_avg"] for s in segments if s.get("hr_avg") is not None]
        hr_baseline = min(vals) if vals else None

    rows, new_prs, matched_prs, updates = [], [], [], []
    tonnage_total = 0.0
    by_group = {}
    for i, ex in enumerate(exercises):
        group = classify_group(ex["device"], ex["name"], device_map)
        tonnage = sum(s["weight"] * s["reps"] for s in ex["sets"])
        max_w = max(s["weight"] for s in ex["sets"])
        tonnage_total += tonnage
        by_group[group] = by_group.get(group, 0.0) + tonnage

        pr_key = match_pr(ex["name"], prs)
        if pr_key is None:
            pr_status, pr_old = ("no_baseline", None)
        elif max_w > prs[pr_key]:
            pr_status, pr_old = ("🏆 PR", prs[pr_key])
            new_prs.append(ex["name"])
            updates.append({"exercise": ex["name"], "old_kg": prs[pr_key],
                            "new_kg": max_w,
                            "delta_kg": _r(max_w - prs[pr_key], 1),
                            "delta_pct": _r(100.0 * (max_w - prs[pr_key]) / prs[pr_key], 1)})
        elif max_w == prs[pr_key]:
            pr_status, pr_old = ("🟢 PB matched", prs[pr_key])
            matched_prs.append(ex["name"])
        else:
            pr_status, pr_old = ("🟡 normal", prs[pr_key])

        seg = mapped[i] if (mapped and i < len(mapped)) else None
        strain = None
        if seg and seg.get("hr_max") is not None and hr_baseline is not None:
            strain = _r(seg["hr_max"] - hr_baseline, 0)

        rows.append({
            "idx": i + 1,
            "device": ex["device"],
            "name": ex["name"],
            "group": group,
            "n_sets": len(ex["sets"]),
            "sets": [{"kg": s["weight"], "reps": s["reps"]} for s in ex["sets"]],
            "tonnage_kg": _r(tonnage, 1),
            "max_kg": max_w,
            "pr_status": pr_status,
            "pr_baseline_kg": pr_old,
            "pr_claimed_in_text": ex["pr_claimed"],
            "reentry_over_target": (bool(reentry) and pr_old is not None
                                    and max_w > REENTRY_FACTORS[0] * pr_old) or None,
            "hr": ({"avg": seg["hr_avg"], "peak": seg["hr_max"],
                    "dur_s": seg["dur_s"]} if seg else None),
            "strain_hr_over_baseline": strain,
            "notes": ex["notes"] or None,
        })

    dist = {}
    band_by_group = {"Beine": LEG_BAND_PCT, "Oberkörper": UPPER_BAND_PCT,
                     "Core": CORE_BAND_PCT}
    for group, kg in sorted(by_group.items()):
        pct = _r(100.0 * kg / tonnage_total, 1) if tonnage_total else None
        dist[group] = {"kg": _r(kg, 1), "pct": pct,
                       "band_pct": band_by_group.get(group),
                       "ampel": _band_ampel(pct, band_by_group[group])
                       if group in band_by_group else None}

    # Session-Aggregate + Bedtime aus den Segmenten.
    hr_all = [s["hr_avg"] for s in segments if s.get("hr_avg") is not None]
    hr_maxs = [s["hr_max"] for s in segments if s.get("hr_max") is not None]
    dur_total = sum(s["dur_s"] for s in segments if s.get("dur_s")) if segments else None
    end_iso = segments[-1].get("end") if segments else None

    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "as_of": as_of,
            "mode": "voll" if segments else "text-only (keine HR-Daten)",
            "n_exercises": len(exercises),
            "skill": "gym-bundle-skill v2.0",
        },
        "session": {
            "n_segments": len(segments),
            "duration_s": _r(dur_total, 0),
            "hr_avg": _r(sum(hr_all) / len(hr_all), 1) if hr_all else None,
            "hr_max": _r(max(hr_maxs), 0) if hr_maxs else None,
            "end": end_iso,
        },
        "bedtime": bedtime_ampel(end_iso),
        "segment_mapping": map_meta,
        "hr_baseline_for_strain": hr_baseline,
        "exercises": rows,
        "tonnage": {"total_kg": _r(tonnage_total, 1), "by_group": dist,
                    "bands": {"Beine": LEG_BAND_PCT, "Oberkörper": UPPER_BAND_PCT,
                              "Core": CORE_BAND_PCT}},
        "pr": {
            "new": new_prs,
            "matched": matched_prs,
            "baseline_updates": updates,   # → baselines.md (SSoT, autonom + sichtbar)
            "n_baselines_loaded": len(prs),
            "reentry": reentry,
        },
    }


def main():
    ap = argparse.ArgumentParser(
        description="Gym-Analyse-Engine (gym-bundle-skill v2.0) — Aggregate-JSON auf stdout.")
    ap.add_argument("--exercises", required=True,
                    help="Übungs-Text-Datei oder '-' (stdin).")
    ap.add_argument("--segments", default=None,
                    help="Segmente-/Master-CSV (optional — sonst Text-Only-Modus).")
    ap.add_argument("--baselines", default=None,
                    help="./data/baselines.md für die PR-Detection (optional).")
    ap.add_argument("--as-of", required=True, dest="as_of", metavar="YYYY-MM-DD",
                    help="Bezugstag (deterministische Pipeline, keine Wall-Clock).")
    ap.add_argument("--days-since-last", type=int, default=None, dest="days_since_last",
                    help="Tage seit der letzten Gym-Session (Re-Entry-Regel §11).")
    ap.add_argument("--device-map", default=None, dest="device_map",
                    help="JSON-Datei {gerät: [name, gruppe]} aus athlete.md (überschreibt die Referenz-Map).")
    args = ap.parse_args()

    try:
        text = sys.stdin.read() if args.exercises == "-" else \
            open(args.exercises, encoding="utf-8").read()
    except OSError as e:
        _fail(f"Übungs-Text nicht lesbar: {e}")
    baselines = None
    if args.baselines:
        try:
            baselines = open(args.baselines, encoding="utf-8").read()
        except OSError as e:
            _fail(f"baselines.md nicht lesbar: {e}", baselines_path=args.baselines)
    dmap = None
    if args.device_map:
        try:
            raw = json.loads(open(args.device_map, encoding="utf-8").read())
            dmap = {str(k): (v[0], v[1]) for k, v in raw.items()}
        except (OSError, ValueError, IndexError, TypeError) as e:
            _fail(f"--device-map nicht lesbar/valide: {e}")
    if args.segments:
        try:
            open(args.segments, encoding="utf-8").close()
        except OSError as e:
            _fail(f"Segmente-CSV nicht lesbar: {e}", segments_path=args.segments)

    res = analyze(text, segments_path=args.segments, baselines_text=baselines,
                  as_of=args.as_of, days_since_last=args.days_since_last,
                  device_map=dmap)
    print(json.dumps(res, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
