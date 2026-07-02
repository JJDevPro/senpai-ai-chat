#!/usr/bin/env python3
"""
readiness.py — Garmin-artiger morgendlicher Training-Readiness-Score (0..100).

WARUM dieses Skript existiert:
  Garmin/WHOOP melden morgens EINE Readiness-Zahl, die HRV-Status, Schlaf, Form
  (TSB) und Ruhepuls-Abweichung zu einem einzigen Urteil verdichtet. Der Daily Check
  (SKILL.md) braucht genau dieses deterministische 0..100-Verdict, NICHT eine erneute
  LLM-Interpretation der Einzelmetriken. Wie `safety_gate.py`, `sentinel.py` und
  `hrv_baseline.py` macht dieses Skript CLAUDE.md-Prosa (§5 Ampel / §6 Overrides) zu
  einem harten, testbaren Urteil — KEIN LLM-Rauschen.

⛔ KERNREGEL (CLAUDE.md §0): Dieses Skript KONSUMIERT NUR bereits reduzierte Outputs
  der Upstream-Skripte (kompakte JSONs) — NIE rohe Per-Sekunde-/Per-Minute-Serien,
  NIE Roh-CSVs. Es importiert KEIN schweres Modul (kein numpy/scipy/statsmodels), es
  liest nur fertige Aggregate. Output = ein kompaktes Score-JSON, nie Roh-Arrays.

⛔ PERSONAL-DATA-FREI (CLAUDE.md Kopf): Keine Körper-/Health-Schwelle ist hartkodiert.
  Die einzigen Zahlen sind die GEWICHTE der Readiness-Komponenten (Methode, kein
  Körper-Fakt) und die BAND-Grenzen (Garmin-artige Anzeige-Stufen). Sicherheits-
  Schwellen werden NICHT dupliziert — der HARTE Override liest nur das fertige
  `safety_gate`-Urteil (level/training_allowed).

KONSUMIERTE UPSTREAM-OUTPUTS (jeweils das kompakte JSON des Skripts, exakte Keys):
  • hrv_baseline.py   → {"status": ...}              (balanced/unbalanced/low/insufficient_data)
  • slice_hae_day.py  → {"heute_sleep": {"total_h": ...}}   (Schlafdauer der HEUTE-Nacht)
  • banister.py       → {"tsb": ...}                 (Form am Morgen von as_of)
  • safety_gate.py    → {"level": ..., "training_allowed": ...}   (HARTER Override)
  • sentinel.py       → {"alerts": [{"level": ...}, ...]}   (WARN-Penalty)
  • rhr_deviation     → eine ABGELEITETE Zahl (bpm Ruhepuls über rollendem Baseline-
                        Median; vom Aufrufer aus sentinel/stats-Daten abgeleitet, z. B.
                        latest_rhr − Trailing-Median). Positiv = erhöht = schlechter.

GEWICHTUNG (100 Punkte, CLAUDE.md §5 priorisiert HRV+Schlaf vor Form):
  HRV-Status 35 · Schlaf 30 · TSB 20 · RHR 15.
  − Sentinel-Penalty: −5 je WARN-Alert, gedeckelt bei −15 (CRITICAL/WATCH zählen NICHT
    in die Penalty — CRITICAL fließt über den safety_gate-Override, WATCH ist nur Hinweis).
  HRV-Status "insufficient_data" → neutraler 0.6×-Faktor auf die HRV-Komponente
    (kein Voll-Score bei dünner Datenlage, aber auch NICHT 0 — Abwesenheit ≠ schlecht).

HARTER OVERRIDE (nach der gewichteten Summe, NUR floor-end / deckelnd):
  safety_gate.level ∈ {CRITICAL} (red) ODER training_allowed == False
    → score = min(score, 35), safety_override = True, band = "red".
  Der Override kann den Score nur SENKEN, nie heben (ein gestrichenes Training ist
  niemals "high readiness", egal wie gut die Einzelwerte aussehen).

BÄNDER (Garmin-artig):
  ≥75 high 🟢 · 50–74 moderate 🟡 · 35–49 low 🟠 · <35 very_low 🔴.

BRUSTGURT (Chest Strap) — BEWUSST OHNE EFFEKT auf den Score:
  Readiness basiert auf RUHE-/Nacht-Signalen (HRV-Nacht, Schlaf, RHR, Form). Die
  Zuverlässigkeit eines Brustgurt-/optischen HR-Sensors während eines INTERVALL-/
  Aktivitäts-Laufs ist eine Lauf-Diagnostik (run-bundle-skill), KEIN Morgen-Recovery-
  Signal. readiness.py liest daher KEIN Brustgurt-/Aktivitäts-HR-Feld; ein solcher
  Input verändert den Score nicht (Test lockt das). Das hält Readiness sauber auf der
  Erholungs-Achse und vermeidet Doppelzählung von Tages-Last (die steckt schon im TSB).

OUTPUT (kompaktes JSON, NIE Roh-Arrays — §0):
  {score, band, top_driver, top_limiter, safety_override, components:{...}}
    score           : 0..100 (int)
    band            : high/moderate/low/very_low (+ Ampel-Emoji im Header-Text)
    top_driver      : Name der STÄRKSTEN Komponente (höchster erreichter Anteil)
    top_limiter     : Name der SCHWÄCHSTEN Komponente (niedrigster erreichter Anteil)
    safety_override : bool (True, wenn das harte Gate gedeckelt hat)
    components      : je Komponente {weight, score01, points} + meta (penalty, gate)

Reine Funktion compute_readiness(inputs) nimmt native Python-Strukturen → testbar OHNE
echte Daten (siehe tests/test_readiness.py). Bei Fehl-Input → exit!=0 + JSON-Error-Objekt.
"""
import argparse
import json
import sys

# --- Gewichte: Methode, kein Körper-Fakt (CLAUDE.md §5 priorisiert HRV+Schlaf) ---
WEIGHTS = {"hrv": 35, "sleep": 30, "tsb": 20, "rhr": 15}

# Sentinel-Penalty (Methode): −5 je WARN, gedeckelt bei −15.
PENALTY_PER_WARN = 5
PENALTY_CAP = 15

# Bei dünner HRV-Datenlage neutral dämpfen statt nullen (Abwesenheit ≠ schlecht).
INSUFFICIENT_HRV_FACTOR = 0.6

# Harter Override deckelt auf diesen Score (CLAUDE.md §6: Training STREICHEN).
SAFETY_CAP_SCORE = 35

# HRV-Status → 0..1 (Garmin-artige Stufen; "insufficient" wird separat gedämpft).
HRV_STATUS_SCORE = {
    "balanced": 1.0,
    "unbalanced": 0.5,
    "low": 0.15,
    "insufficient_data": 1.0,   # Roh-Score; INSUFFICIENT_HRV_FACTOR wirkt danach
}

# Band-Grenzen (Garmin-artige Anzeige-Stufen, kein Körper-Fakt).
BAND_HIGH = 75
BAND_MODERATE = 50
BAND_LOW = 35

# safety_gate.level-Werte, die den harten Override auslösen (red/critical).
SAFETY_RED_LEVELS = {"CRITICAL"}


class ReadinessError(ValueError):
    """Eingabefehler (fehlende/kaputte Inputs) → JSON-Error + non-zero Exit."""


def _clamp01(x):
    """Auf [0, 1] beschneiden."""
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


# ================================================================ component maps (pure)
def _hrv_component(hrv_baseline):
    """hrv_baseline-Output → (score01, insufficient_flag).

    Liest NUR `status` (balanced/unbalanced/low/insufficient_data). Fehlt das Dict
    oder der Status, behandeln wir es wie insufficient_data (neutral gedämpft, nicht 0).
    """
    status = (hrv_baseline or {}).get("status")
    if status not in HRV_STATUS_SCORE:
        status = "insufficient_data"
    base = HRV_STATUS_SCORE[status]
    if status == "insufficient_data":
        return _clamp01(base * INSUFFICIENT_HRV_FACTOR), True
    return _clamp01(base), False


def _sleep_component(daily):
    """slice_hae_day-Output → score01 aus heute_sleep.total_h.

    Linear gemappt: 8 h+ = 1.0, 5 h = 0.0 (darunter geclamped). 5..8 h ist das Band,
    in dem Schlafdauer den Recovery-Score realistisch differenziert. Fehlt der Wert →
    neutral 0.5 (kein Voll-Score, aber keine Strafe bei fehlendem Signal)."""
    total_h = ((daily or {}).get("heute_sleep") or {}).get("total_h")
    if total_h is None:
        return 0.5, False
    return _clamp01((float(total_h) - 5.0) / 3.0), True


def _tsb_component(banister):
    """banister-Output → score01 aus tsb (Form). Mappt die §-Form-Stufen weich:
    TSB ≥ +5 (frisch/Peak) = 1.0 · TSB ≤ −30 (tiefe Ermüdung) = 0.0 · linear dazwischen.
    Fehlt tsb → neutral 0.5 (keine Trainingshistorie ≠ schlechte Form)."""
    tsb = (banister or {}).get("tsb")
    if tsb is None:
        return 0.5, False
    return _clamp01((float(tsb) + 30.0) / 35.0), True


def _rhr_component(rhr_deviation):
    """Abgeleitete RHR-Abweichung (bpm über Baseline-Median) → score01.

    0 bpm (oder darunter, also unter Baseline) = 1.0 · +10 bpm = 0.0 (geclamped).
    CLAUDE.md §6 markiert RHR Baseline+5 als Erholungs-Warnung — bei +5 liegt der
    Score-Beitrag dann bei 0.5, was den Hebel sauber abbildet, OHNE eine neue Schwelle
    zu erfinden. Fehlt der Wert → neutral 0.5."""
    if rhr_deviation is None:
        return 0.5, False
    return _clamp01(1.0 - (float(rhr_deviation) / 10.0)), True


def _sentinel_penalty(sentinel):
    """sentinel-Output → Penalty-Punkte (negativ): −5 je WARN, Cap −15.

    Liest NUR alerts[].level == "WARN". CRITICAL fließt über den safety_gate-Override
    (nicht doppelt zählen), WATCH ist nur ein Hinweis (kein actionable Penalty)."""
    alerts = (sentinel or {}).get("alerts") or []
    n_warn = sum(1 for a in alerts if isinstance(a, dict) and a.get("level") == "WARN")
    return min(n_warn * PENALTY_PER_WARN, PENALTY_CAP), n_warn


# ================================================================ orchestrator (pure)
def compute_readiness(inputs):
    """Reine Funktion: dict der Upstream-Outputs → Readiness-Dict. Keine I/O.

    inputs (alle optional, robust gegen Abwesenheit):
      hrv_baseline   : hrv_baseline.py-Output      (liest .status)
      daily          : slice_hae_day.py-Output     (liest .heute_sleep.total_h)
      banister       : banister.py-Output          (liest .tsb)
      safety_gate    : safety_gate.py-Output       (liest .level, .training_allowed)
      sentinel       : sentinel.py-Output          (liest .alerts[].level)
      rhr_deviation  : abgeleitete Zahl (bpm über Baseline) ODER None

    Brustgurt-/Aktivitäts-HR-Felder werden BEWUSST NICHT gelesen → kein Score-Effekt.
    """
    if not isinstance(inputs, dict):
        raise ReadinessError("inputs muss ein dict der Upstream-Outputs sein.")

    hrv01, hrv_insufficient = _hrv_component(inputs.get("hrv_baseline"))
    sleep01, sleep_present = _sleep_component(inputs.get("daily"))
    tsb01, tsb_present = _tsb_component(inputs.get("banister"))
    # RHR-Zubringer: expliziter Wert gewinnt; sonst die von sentinel.py mit-emittierte
    # Abweichung (latest − Trailing-Median) — so ist die RHR-Komponente in JEDEM
    # Daily Check gefüllt, ohne dass der Aufrufer selbst rechnen muss (EIN Score überall).
    rhr_dev = inputs.get("rhr_deviation")
    if rhr_dev is None:
        rhr_dev = (inputs.get("sentinel") or {}).get("rhr_deviation")
    rhr01, rhr_present = _rhr_component(rhr_dev)

    score01 = {"hrv": hrv01, "sleep": sleep01, "tsb": tsb01, "rhr": rhr01}
    points = {k: WEIGHTS[k] * score01[k] for k in WEIGHTS}
    weighted = sum(points.values())

    penalty, n_warn = _sentinel_penalty(inputs.get("sentinel"))
    raw_score = weighted - penalty

    # --- harter Override NACH der Summe, NUR deckelnd (floor-only) ---
    gate = inputs.get("safety_gate") or {}
    gate_level = gate.get("level")
    training_allowed = gate.get("training_allowed")
    safety_override = (gate_level in SAFETY_RED_LEVELS) or (training_allowed is False)

    score = raw_score
    if safety_override:
        score = min(score, SAFETY_CAP_SCORE)

    score = int(round(_clamp_score(score)))

    if safety_override:
        band = "red"
    else:
        band = _band(score)

    # top_driver = stärkster Anteil am erreichbaren Gewicht; top_limiter = schwächster.
    fraction = {k: score01[k] for k in WEIGHTS}
    top_driver = max(fraction, key=lambda k: (fraction[k], WEIGHTS[k]))
    top_limiter = min(fraction, key=lambda k: (fraction[k], -WEIGHTS[k]))

    return {
        "score": score,
        "band": band,
        "top_driver": top_driver,
        "top_limiter": top_limiter,
        "safety_override": safety_override,
        "components": {
            k: {
                "weight": WEIGHTS[k],
                "score01": round(score01[k], 3),
                "points": round(points[k], 1),
                "present": {"hrv": not hrv_insufficient, "sleep": sleep_present,
                            "tsb": tsb_present, "rhr": rhr_present}[k],
            }
            for k in WEIGHTS
        },
        "meta": {
            "weighted_subtotal": round(weighted, 1),
            "sentinel_penalty": penalty,
            "sentinel_warn_count": n_warn,
            "hrv_insufficient": hrv_insufficient,
            "safety_gate_level": gate_level,
            "training_allowed": training_allowed,
            "safety_cap_score": SAFETY_CAP_SCORE,
            "note": "Brustgurt-/Aktivitäts-HR ohne Effekt — Readiness = Ruhe-/Nacht-Achse.",
        },
    }


def _clamp_score(x):
    """Score auf [0, 100] beschneiden."""
    return 0.0 if x < 0 else (100.0 if x > 100 else x)


def _band(score):
    """0..100 → Garmin-artiges Band (ohne Override)."""
    if score >= BAND_HIGH:
        return "high"
    if score >= BAND_MODERATE:
        return "moderate"
    if score >= BAND_LOW:
        return "low"
    return "very_low"


BAND_EMOJI = {"high": "🟢", "moderate": "🟡", "low": "🟠", "very_low": "🔴", "red": "🔴"}


# ================================================================ CLI
def _load_json_arg(value, label):
    """CLI-Arg: Pfad ODER '-' (stdin) → geparstes JSON (oder None bei leerem Arg)."""
    if value is None:
        return None
    try:
        raw = sys.stdin.read() if value == "-" else open(value, encoding="utf-8").read()
    except OSError as e:
        raise ReadinessError(f"{label}: Datei nicht lesbar ({e}).")
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except ValueError as e:
        raise ReadinessError(f"{label}: kein gültiges JSON ({e}).")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Garmin-artiger Training-Readiness-Score 0..100 (CLAUDE.md §5/§6). "
                    "Konsumiert NUR fertige Upstream-Outputs (hrv_baseline/slice_hae_day/"
                    "banister/safety_gate/sentinel), nie Roh-Serien.")
    ap.add_argument("--hrv-baseline", help="hrv_baseline.py-Output (Datei oder '-' für stdin).")
    ap.add_argument("--daily", help="slice_hae_day.py-Output (Datei oder '-' für stdin).")
    ap.add_argument("--banister", help="banister.py-Output (Datei oder '-' für stdin).")
    ap.add_argument("--safety-gate", help="safety_gate.py-Output (Datei oder '-' für stdin).")
    ap.add_argument("--sentinel", help="sentinel.py-Output (Datei oder '-' für stdin).")
    ap.add_argument("--rhr-deviation", type=float, default=None,
                    help="Abgeleitete Ruhepuls-Abweichung in bpm über Baseline-Median "
                         "(positiv = erhöht). Aus sentinel/stats-Daten abgeleitet.")
    args = ap.parse_args(argv)

    # Höchstens EIN '-'-Input (stdin lässt sich nur einmal lesen).
    stdin_args = [v for v in (args.hrv_baseline, args.daily, args.banister,
                              args.safety_gate, args.sentinel) if v == "-"]
    try:
        if len(stdin_args) > 1:
            raise ReadinessError("Nur EIN Input darf '-' (stdin) sein.")
        inputs = {
            "hrv_baseline": _load_json_arg(args.hrv_baseline, "--hrv-baseline"),
            "daily": _load_json_arg(args.daily, "--daily"),
            "banister": _load_json_arg(args.banister, "--banister"),
            "safety_gate": _load_json_arg(args.safety_gate, "--safety-gate"),
            "sentinel": _load_json_arg(args.sentinel, "--sentinel"),
            "rhr_deviation": args.rhr_deviation,
        }
        out = compute_readiness(inputs)
    except ReadinessError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, separators=(",", ":")))
        return 1

    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
