#!/usr/bin/env python3
"""
hrv_baseline.py — Garmin-artiger "HRV Status" über einen rollenden 60-Tage-Baseline.

WARUM dieses Skript existiert:
  Garmin meldet keinen nackten HRV-Wert, sondern einen STATUS (balanced / unbalanced /
  low / insufficient) relativ zu einem persönlichen, rollenden Baseline. Der Daily Check
  (SKILL.md) bzw. die readiness.py/readiness_history.py-Pipeline brauchen genau dieses
  deterministische Status-Urteil, NICHT die rohe HRV-Tagesreihe. Wie `safety_gate.py`
  und `sentinel.py` macht dieses Skript CLAUDE.md-Prosa (§5 HRV-Ampel) zu einem harten,
  testbaren Urteil — KEIN LLM-Rauschen.

⛔ KERNREGEL (CLAUDE.md §0): Dieses Skript konsumiert NUR bereits reduzierte Aggregate
  (die HRV/RHR-Tages-CSV via `sentinel.read_health_csv`, 1 Zeile/Tag) und gibt NUR ein
  kompaktes Status-JSON aus — NIE die Per-Tag-Serie, NIE Roh-Per-Sekunde-/Per-Minute-Daten.

⛔ PERSONAL-DATA-FREI (CLAUDE.md Kopf): Es ist KEINE persönliche Schwelle hartkodiert.
  Das "low"-Floor ist NICHT neu erfunden, sondern 1:1 aus `safety_gate.HRV_RED` (CLAUDE.md
  §5: 🔴 <50 ms) wiederverwendet. Die Band-Breite ist eine robuste Statistik (Median/MAD),
  kein Körper-Fakt.

METHODE (robuster Baseline-Band):
  Fenster = die jüngsten WINDOW_DAYS=60 Tage mit HRV ≤ as_of. Aus diesen Tagen:
    median + MAD (Median Absolute Deviation, robust gegen Einzel-Spikes).
    Band = [median − K·MAD, median + K·MAD], K=1.0.
  Status (vom jüngsten HRV-Wert im Fenster):
    n < MIN_DAYS (14)        → "insufficient_data"  (Median/Band/n trotzdem emittiert)
    latest  < LOW_FLOOR      → "low"                (= safety_gate.HRV_RED, §5)
    latest innerhalb Band    → "balanced"
    sonst                    → "unbalanced"

CLI:  hrv_baseline.py --health-csv CSV [--as-of YYYY-MM-DD]
      --health-csv : Gesundheitsdaten 'Tägliche Kennzahlen' CSV (Datum, HFV[=HRV], RHR …).
      --as-of      : Stichtag (deterministisch). Default = jüngstes Datum in der CSV.

Output (kompaktes JSON, NIE Roh-Arrays — §0):
  {as_of, window_days, n, median, mad, band:{low,high},
   latest:{value,date}, latest_vs_band, status, k, min_days}
Bei Fehl-Input (Datei fehlt, keine HRV-Werte, kaputtes --as-of) → exit!=0 + JSON-Error-Objekt.

Kernfunktion compute_baseline(rows, as_of) nimmt native Python-Strukturen → testbar OHNE
echte Daten (siehe tests/test_hrv_baseline.py).
"""
import argparse
import json
import os
import statistics
import sys

# Sibling-Imports (sentinel/safety_gate liegen im selben scripts/-Verzeichnis;
# beim Standalone-Lauf ist dieser Ordner sys.path[0]).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import safety_gate  # noqa: E402  — HRV_RED (§5) als LOW_FLOOR wiederverwenden, NICHT neu erfinden
import sentinel  # noqa: E402  — read_health_csv reuse

# --- Parameter ------------------------------------------------------------------
WINDOW_DAYS = 60          # rollender Baseline-Horizont (Garmin "HRV Status")
K = 1.0                   # MAD-Multiplikator für die Band-Breite
MIN_DAYS = 14             # unter so vielen Tagen kein belastbarer Baseline → insufficient
LOW_FLOOR = safety_gate.HRV_RED   # §5: 🔴 <50 ms — REUSE, keine neue Zahl


class HrvBaselineError(ValueError):
    """Eingabefehler (fehlende/kaputte Daten) → JSON-Error + non-zero Exit."""


def _valid_iso(s):
    """YYYY-MM-DD strikt validieren (deterministisch, keine Wall-Clock)."""
    if not isinstance(s, str) or len(s) != 10 or s[4] != "-" or s[7] != "-":
        return False
    y, m, d = s[:4], s[5:7], s[8:10]
    if not (y.isdigit() and m.isdigit() and d.isdigit()):
        return False
    return 1 <= int(m) <= 12 and 1 <= int(d) <= 31


def compute_baseline(rows, as_of):
    """Reine Funktion: HRV-Tagesreihe + Stichtag → kompaktes Status-Dict. Keine I/O.

    rows:  iterable von {date, hrv, ...} (z. B. sentinel.read_health_csv-Ausgabe).
           Zeilen ohne Datum oder ohne HRV-Wert werden ignoriert.
    as_of: ISO-Stichtag (YYYY-MM-DD). Nur Tage mit date <= as_of zählen.
    Wirft HrvBaselineError, wenn as_of kaputt ist oder gar kein HRV-Wert ≤ as_of existiert.
    """
    if not _valid_iso(as_of):
        raise HrvBaselineError(f"Ungültiges --as-of '{as_of}' (erwartet YYYY-MM-DD).")

    # Pro Tag genau ein HRV-Wert (jüngste Zeile gewinnt), nur Tage <= as_of.
    hrv_by_day = {}
    for r in rows or []:
        d = r.get("date")
        v = r.get("hrv")
        if not d or v is None or d > as_of:
            continue
        hrv_by_day[d] = float(v)

    if not hrv_by_day:
        raise HrvBaselineError(f"Keine HRV-Werte mit Datum <= {as_of} gefunden.")

    days = sorted(hrv_by_day)
    window_days_list = days[-WINDOW_DAYS:]            # jüngste <=60 Tage
    window_vals = [hrv_by_day[d] for d in window_days_list]
    n = len(window_vals)

    median = statistics.median(window_vals)
    mad = statistics.median([abs(v - median) for v in window_vals])
    band_low = median - K * mad
    band_high = median + K * mad

    latest_day = window_days_list[-1]
    latest_val = hrv_by_day[latest_day]

    if latest_val < band_low:
        latest_vs_band = "below"
    elif latest_val > band_high:
        latest_vs_band = "above"
    else:
        latest_vs_band = "within"

    if n < MIN_DAYS:
        status = "insufficient_data"
    elif latest_val < LOW_FLOOR:
        status = "low"
    elif latest_vs_band == "within":
        status = "balanced"
    else:
        status = "unbalanced"

    return {
        "as_of": as_of,
        "window_days": WINDOW_DAYS,
        "n": n,
        "median": round(median, 2),
        "mad": round(mad, 2),
        "band": {"low": round(band_low, 2), "high": round(band_high, 2)},
        "latest": {"value": round(latest_val, 2), "date": latest_day},
        "latest_vs_band": latest_vs_band,
        "status": status,
        "k": K,
        "min_days": MIN_DAYS,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Garmin-artiger HRV-Status über rollenden 60-Tage-Baseline "
                    "(CLAUDE.md §5). Konsumiert NUR reduzierte Aggregate, nie Roh-Serien.")
    ap.add_argument("--health-csv", required=True,
                    help="Gesundheitsdaten 'Tägliche Kennzahlen' CSV (HFV/HRV-Trend).")
    ap.add_argument("--as-of", default=None, dest="as_of",
                    help="Stichtag YYYY-MM-DD (Default: jüngstes Datum in der CSV).")
    args = ap.parse_args(argv)

    try:
        if not os.path.isfile(args.health_csv):
            raise HrvBaselineError(f"CSV nicht gefunden: {args.health_csv}")
        rows = sentinel.read_health_csv(args.health_csv)

        as_of = args.as_of
        if as_of is None:
            dated = [r["date"] for r in rows if r.get("date") and r.get("hrv") is not None]
            if not dated:
                raise HrvBaselineError("Keine datierten HRV-Werte in der CSV.")
            as_of = max(dated)

        out = compute_baseline(rows, as_of)
    except HrvBaselineError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, separators=(",", ":")))
        return 1
    except (OSError, ValueError) as e:  # noqa: BLE001 — kaputte Datei/Parsing → JSON-Error
        print(json.dumps({"error": f"{type(e).__name__}: {e}"},
                         ensure_ascii=False, separators=(",", ":")))
        return 1

    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
