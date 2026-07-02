#!/usr/bin/env python3
"""
body_battery.py — Garmin/WHOOP-artiger "Body Battery"-Surrogat (0..100) für daily-check.

WARUM dieses Skript existiert:
  Garmin meldet eine kontinuierliche "Body Battery": Schlaf LÄDT, Tages-Last + Stress
  ENTLADEN. Der Daily Check (SKILL.md) bzw. die readiness/readiness_history-Pipeline
  wollen genau diese eine, leicht lesbare 0..100-Zahl als Tages-Energie-Proxy —
  NICHT die rohe Minuten-für-Minuten-Kurve. Wie `safety_gate.py`, `sentinel.py` und
  `hrv_baseline.py` macht dieses Skript CLAUDE.md-Prosa (§5 HRV/Recovery-Ampel) zu
  einem harten, deterministischen Urteil — KEIN LLM-Rauschen.

⛔ HEURISTIK / SURROGAT (kein gemessener Garmin-Wert):
  Body Battery ist KEIN von Apple Health gemeldetes Feld. Diese Zahl ist ein
  TRANSPARENT zusammengesetzter Surrogat aus bereits reduzierten Aggregaten:
    • Recharge (Schlaf)  : Dauer + Tiefe + REM + HRV-Status → wie voll der Akku morgens ist.
    • Drain (Tag)        : Trainings-Last (Banister ATL/TSB) + Aktiv-Energie + Atmungs-/
                           Stress-Last in der Nacht → wie stark der Tag den Akku zieht.
  Sie ERSETZT die §5-Ampel NICHT, sie verdichtet sie zu einer Akku-Anzeige.

⛔ KERNREGEL (CLAUDE.md §0): Dieses Skript konsumiert NUR bereits reduzierte Outputs
  anderer Skripte (hrv_baseline-Status, slice_hae_day Schlaf/Stress/Aktivität,
  banister TSB/ATL) und gibt NUR ein kompaktes Tages-Aggregat aus — NIE die Minuten-
  Serie, NIE Roh-Per-Sekunde-/Per-Minute-Daten. Output = Tagesstart/Tagesende, kein
  Minute-für-Minute-Verlauf.

⛔ PERSONAL-DATA-FREI (CLAUDE.md Kopf): Keine Körper-Schwelle hartkodiert. Die HRV-
  Bewertung kommt aus dem übergebenen hrv_baseline-Status (der seinerseits
  safety_gate.HRV_RED §5 wiederverwendet), nicht aus neuen Zahlen. Schlaf-Ziele +
  Last-Skalen sind generische, gelabelte Modell-Konstanten (kein Personen-Fakt).

ENTKOPPLUNG (wie readiness): compute_body_battery(inputs) nimmt EIN dict mit bereits
  reduzierten Teil-Outputs — es liest keine Dateien, ruft keine Siblings auf. Der CLI-
  Layer verdrahtet die echten Quellen (slice_hae_day, hrv_baseline, banister) und reicht
  deren JSON gebündelt rein. Das hält die Compute-Funktion ohne echte Daten testbar.

ERWARTETE INPUT-KEYS (alle optional; fehlt einer, neutralisiert das Modell ihn):
  inputs = {
    "as_of": "YYYY-MM-DD",                       # Stichtag (deterministisch, kein Wall-Clock)
    "sleep":   {total_h, deep_h, rem_h, awake_h},# slice_hae_day.heute_sleep
    "hrv":     {status: balanced|unbalanced|low|insufficient_data},  # hrv_baseline-Output
    "load":    {tsb, atl},                        # banister-Output (Form/Ermüdung)
    "activity":{active_energy_kcal, physical_effort_peak},  # slice_hae_day.gestern_load
    "stress":  {respiratory_rate_night_avg, breathing_disturbances},# slice_hae_day.recovery
  }

Output (kompaktes JSON, NIE Roh-Arrays / Minuten-Serie — §0):
  {as_of, bb_start, bb_end, recharged, drained, low_point, status, surrogate:true, ...}
    bb_start  = Akku am Tagesstart (nach der Nacht-Aufladung), 0..100.
    bb_end    = Akku am Tagesende (nach Tages-Entladung), 0..100.
    recharged = wie viele Punkte die Nacht geladen hat (vs. Vortags-Rest).
    drained   = wie viele Punkte der Tag gezogen hat.
    low_point = bb_end (Tages-Tiefpunkt-Proxy; ohne Minuten-Serie = Tagesende).
    status    ∈ {high, ok, low, critical} (Akku-Ampel, abgeleitet von bb_end).
Bei Fehl-Input (kaputtes --as-of, kein parsbares Input-JSON) → exit!=0 + JSON-Error.

Kernfunktion compute_body_battery(inputs) ist rein → testbar OHNE echte Daten
(siehe tests/test_body_battery.py).
"""
import argparse
import json
import os
import sys

# Sibling-Imports (slice_hae_day/hrv_baseline/banister liegen im selben scripts/-Ordner;
# beim Standalone-Lauf ist dieser Ordner sys.path[0]).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- Modell-Konstanten (generisch/gelabelt, KEIN Personen-Fakt) -----------------
BB_MIN, BB_MAX = 0, 100
PREV_REST = 35              # Vortags-Rest-Akku, wenn kein --prev-bb übergeben (neutraler Start)
FULL_RECHARGE = 65          # max. Nacht-Ladung (Punkte) bei perfekter Nacht → Akku Richtung 100
TARGET_SLEEP_H = 7.5        # generisches Schlaf-Ziel (Modell-Anker, kein Körper-Fakt)
MIN_USEFUL_SLEEP_H = 4.0    # darunter zählt die Nacht kaum als Aufladung
TARGET_DEEP_H = 1.2         # generischer Tiefschlaf-Anker für volle Qualitäts-Gutschrift
TARGET_REM_H = 1.5          # generischer REM-Anker
BASE_DRAIN = 18             # Grund-Entladung eines normalen Wachtags (Punkte)
MAX_LOAD_DRAIN = 45         # max. zusätzliche Last-Entladung (Training/Aktiv/Stress)
ACTIVE_KCAL_FULL = 900      # Aktiv-Energie, ab der die Aktivitäts-Last voll zieht
EFFORT_FULL = 7.0           # physical_effort-Peak, ab dem die Effort-Last voll zieht
ATL_FULL = 80               # Banister-ATL, ab der die Ermüdungs-Last voll zieht
BREATHING_DRAIN_AT = 10     # §3c/§11: grünes Ceiling der Bänder (≤10🟢); >10 zählt als Stress-Last

# HRV-Status (aus hrv_baseline) → Lade-Modulator: balanced lädt voll, low/unbalanced dämpft.
HRV_RECHARGE_FACTOR = {
    "balanced": 1.0,
    "insufficient_data": 0.95,
    "unbalanced": 0.85,
    "low": 0.7,
}


class BodyBatteryError(ValueError):
    """Eingabefehler (kaputtes --as-of / Input-JSON) → JSON-Error + non-zero Exit."""


def _valid_iso(s):
    """YYYY-MM-DD strikt validieren (deterministisch, keine Wall-Clock)."""
    if not isinstance(s, str) or len(s) != 10 or s[4] != "-" or s[7] != "-":
        return False
    y, m, d = s[:4], s[5:7], s[8:10]
    if not (y.isdigit() and m.isdigit() and d.isdigit()):
        return False
    return 1 <= int(m) <= 12 and 1 <= int(d) <= 31


def _num(x):
    """Robuster Float-Cast; None/nicht-parsbar → None."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


def _clamp01(x):
    """Auf [0,1] begrenzen (für normierte Last-/Qualitäts-Anteile)."""
    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return x


def _clamp_bb(x):
    """Auf den gültigen Akku-Bereich [BB_MIN, BB_MAX] begrenzen."""
    return max(BB_MIN, min(BB_MAX, x))


def _recharge_points(sleep, hrv):
    """Nacht-Aufladung in Punkten + Begründung.

    Modell: Aufladung = FULL_RECHARGE × Schlaf-Qualität × HRV-Modulator.
    Schlaf-Qualität = Mix aus Dauer (vs. Ziel), Tiefschlaf, REM, abzüglich Wachzeit.
    Fehlt der Schlaf-Block komplett → neutrale Teil-Aufladung (kein Crash, aber kein Bonus).
    """
    sleep = sleep or {}
    total_h = _num(sleep.get("total_h"))
    deep_h = _num(sleep.get("deep_h"))
    rem_h = _num(sleep.get("rem_h"))
    awake_h = _num(sleep.get("awake_h"))

    if total_h is None:
        duration_q = 0.5            # unbekannte Dauer → neutrale halbe Gutschrift
    elif total_h <= MIN_USEFUL_SLEEP_H:
        duration_q = _clamp01((total_h / MIN_USEFUL_SLEEP_H) * 0.4)
    else:
        duration_q = _clamp01(total_h / TARGET_SLEEP_H)

    # Tiefschlaf + REM heben die Qualität, Wachzeit zieht sie. Nur anwenden, wenn bekannt.
    quality = duration_q
    if deep_h is not None:
        quality = quality * 0.7 + _clamp01(deep_h / TARGET_DEEP_H) * 0.3
    if rem_h is not None:
        quality = quality * 0.8 + _clamp01(rem_h / TARGET_REM_H) * 0.2
    if awake_h is not None and total_h:
        quality *= _clamp01(1 - (awake_h / (total_h + awake_h)))
    quality = _clamp01(quality)

    status = (hrv or {}).get("status")
    hrv_factor = HRV_RECHARGE_FACTOR.get(status, 0.9)

    points = FULL_RECHARGE * quality * hrv_factor
    return points, {"sleep_quality": round(quality, 3), "hrv_status": status,
                    "hrv_factor": hrv_factor}


def _drain_points(load, activity, stress):
    """Tages-Entladung in Punkten + Begründung.

    Modell: Entladung = BASE_DRAIN + MAX_LOAD_DRAIN × Last-Anteil.
    Last-Anteil = Maximum aus normierter Trainings-Last (ATL), Aktiv-Energie, Effort-Peak,
    plus additivem Stress-Aufschlag (Atemstörungen über §3c/§11-Schwelle).
    Negativer TSB (Ermüdung) hebt die Last leicht an — frische Form (TSB>0) dämpft sie.
    """
    load = load or {}
    activity = activity or {}
    stress = stress or {}

    atl = _num(load.get("atl"))
    tsb = _num(load.get("tsb"))
    active_kcal = _num(activity.get("active_energy_kcal"))
    effort_peak = _num(activity.get("physical_effort_peak"))
    breathing = _num(stress.get("breathing_disturbances"))

    load_components = []
    if atl is not None:
        load_components.append(_clamp01(atl / ATL_FULL))
    if active_kcal is not None:
        load_components.append(_clamp01(active_kcal / ACTIVE_KCAL_FULL))
    if effort_peak is not None:
        load_components.append(_clamp01(effort_peak / EFFORT_FULL))
    load_share = max(load_components) if load_components else 0.4  # unbekannt → moderater Tag

    # TSB-Nudge: tiefe Ermüdung (TSB stark negativ) zieht mehr, Frische zieht weniger.
    tsb_nudge = 0.0
    if tsb is not None:
        if tsb < -15:
            tsb_nudge = 0.1
        elif tsb > 5:
            tsb_nudge = -0.05
    load_share = _clamp01(load_share + tsb_nudge)

    # Stress-Aufschlag: Atemstörungen über der §3c/§11-Schwelle = zusätzliche Last.
    stress_share = 0.0
    if breathing is not None and breathing > BREATHING_DRAIN_AT:
        stress_share = _clamp01((breathing - BREATHING_DRAIN_AT) / BREATHING_DRAIN_AT) * 0.25

    points = BASE_DRAIN + MAX_LOAD_DRAIN * _clamp01(load_share + stress_share)
    return points, {"load_share": round(load_share, 3),
                    "stress_share": round(stress_share, 3),
                    "tsb_nudge": tsb_nudge}


def _bb_status(bb_end):
    """Akku-Ampel aus dem Tagesende-Wert (verdichtet §5-Recovery-Logik)."""
    if bb_end >= 60:
        return "high"
    if bb_end >= 40:
        return "ok"
    if bb_end >= 20:
        return "low"
    return "critical"


def compute_body_battery(inputs):
    """Reine Funktion: gebündelte reduzierte Outputs → Tages-Akku-Aggregat. Keine I/O.

    inputs: dict mit den oben dokumentierten (optionalen) Teil-Outputs + as_of + prev_bb.
    Modell: Nacht LÄDT (recharged), Tag ENTLÄDT (drained).
      bb_start = clamp(prev_rest + recharged)   # Akku am Morgen
      bb_end   = clamp(bb_start − drained)       # Akku am Abend
    Gibt NUR das Tages-Aggregat zurück (Start/Ende + Punkte), NIE eine Minuten-Serie.
    Wirft BodyBatteryError bei kaputtem --as-of.
    """
    inputs = inputs or {}
    as_of = inputs.get("as_of")
    if as_of is not None and not _valid_iso(as_of):
        raise BodyBatteryError(f"Ungültiges as_of '{as_of}' (erwartet YYYY-MM-DD).")

    prev = _num(inputs.get("prev_bb"))
    prev_rest = prev if prev is not None else PREV_REST
    prev_rest = _clamp_bb(prev_rest)

    recharged, recharge_why = _recharge_points(inputs.get("sleep"), inputs.get("hrv"))
    drained, drain_why = _drain_points(inputs.get("load"), inputs.get("activity"),
                                       inputs.get("stress"))

    bb_start = _clamp_bb(prev_rest + recharged)
    bb_end = _clamp_bb(bb_start - drained)
    # Tatsächlich realisierte Punkte nach Clamping (für ehrliche recharged/drained-Anzeige).
    recharged_real = round(bb_start - prev_rest)
    drained_real = round(bb_start - bb_end)

    out = {
        "as_of": as_of,
        "surrogate": True,
        "bb_start": round(bb_start),
        "bb_end": round(bb_end),
        "recharged": recharged_real,
        "drained": drained_real,
        "low_point": round(bb_end),   # ohne Minuten-Serie = Tagesende als Tiefpunkt-Proxy
        "status": _bb_status(bb_end),
        "prev_rest": round(prev_rest),
        "recharge_basis": recharge_why,
        "drain_basis": drain_why,
        "note": ("Heuristischer Body-Battery-SURROGAT (kein gemessener Apple-Health-Wert): "
                 "Schlaf lädt, Tages-Last/Stress entlädt. Tages-Aggregat (Start/Ende), "
                 "keine Minuten-Serie. Ergänzt die §5-Ampel, ersetzt sie nicht."),
    }
    return out


# ---------------------------------------------------------------- CLI input assembly
def _build_inputs_from_cli(args):
    """Verdrahtet die echten Quell-JSONs (slice_hae_day / hrv_baseline / banister) zu
    EINEM reduzierten Input-dict. Liest NUR die schon-reduzierten Aggregate aus —
    nie eine Roh-Serie."""
    def _load(path):
        if not path:
            return None
        if path == "-":
            return json.loads(sys.stdin.read())
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    slice_d = _load(args.slice) or {}
    hrv_d = _load(args.hrv) or {}
    banister_d = _load(args.banister) or {}

    sleep = slice_d.get("heute_sleep") or {}
    gl = slice_d.get("gestern_load") or {}
    pe = gl.get("physical_effort") or {}
    recovery = slice_d.get("recovery") or {}
    rr = recovery.get("respiratory_rate") or {}
    bd = recovery.get("breathing_disturbances") or {}

    as_of = args.as_of or slice_d.get("as_of")

    inputs = {
        "as_of": as_of,
        "sleep": {"total_h": sleep.get("total_h"), "deep_h": sleep.get("deep_h"),
                  "rem_h": sleep.get("rem_h"), "awake_h": sleep.get("awake_h")},
        "hrv": {"status": hrv_d.get("status")},
        "load": {"tsb": banister_d.get("tsb"), "atl": banister_d.get("atl")},
        "activity": {"active_energy_kcal": gl.get("active_energy_kcal"),
                     "physical_effort_peak": pe.get("peak")},
        "stress": {"respiratory_rate_night_avg": rr.get("night_avg"),
                   "breathing_disturbances": bd.get("value")},
    }
    if args.prev_bb is not None:
        inputs["prev_bb"] = args.prev_bb
    return inputs


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Heuristischer Body-Battery-Surrogat (0..100) für daily-check. "
                    "Konsumiert NUR reduzierte Outputs, gibt ein Tages-Aggregat aus (§0).")
    ap.add_argument("--slice", help="slice_hae_day-Ausgabe (heute_sleep/gestern_load/recovery). "
                                     "Datei oder '-' für stdin.")
    ap.add_argument("--hrv", help="hrv_baseline-Ausgabe (status). Datei.")
    ap.add_argument("--banister", help="banister-Ausgabe (tsb/atl). Datei.")
    ap.add_argument("--inputs-json", help="Vorgebündeltes Input-dict (Datei oder '-'). "
                                          "Überschreibt --slice/--hrv/--banister.")
    ap.add_argument("--prev-bb", type=float, default=None, dest="prev_bb",
                    help="Vortags-Rest-Akku 0..100 (sonst neutraler Default).")
    ap.add_argument("--as-of", default=None, dest="as_of",
                    help="Stichtag YYYY-MM-DD (Default: as_of aus dem Slice).")
    args = ap.parse_args(argv)

    try:
        if args.inputs_json:
            raw = sys.stdin.read() if args.inputs_json == "-" else \
                open(args.inputs_json, encoding="utf-8").read()
            inputs = json.loads(raw)
            if args.prev_bb is not None:
                inputs["prev_bb"] = args.prev_bb
            if args.as_of is not None:
                inputs["as_of"] = args.as_of
        else:
            inputs = _build_inputs_from_cli(args)
        out = compute_body_battery(inputs)
    except BodyBatteryError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, separators=(",", ":")))
        return 1
    except (OSError, ValueError) as e:  # noqa: BLE001 — kaputte Datei/JSON → JSON-Error
        print(json.dumps({"error": f"{type(e).__name__}: {e}"},
                         ensure_ascii=False, separators=(",", ":")))
        return 1

    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
