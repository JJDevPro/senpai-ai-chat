#!/usr/bin/env python3
"""
running_tolerance.py — Lauf-Toleranz-Klon (Garmin FR970 "Running Tolerance")

WARUM dieses Skript existiert:
  Die FR970-Uhr deckelt das Wochen-Volumen über einen Ramp-Rate-Guard: zu schnell
  hochgefahrene Wochen-KM = Verletzungs-Risiko. Für diesen Athleten (hohes Körper-
  gewicht → Gelenkschutz, CLAUDE.md §1 "Kadenz nie <160" / §4) ist ein harter
  Volumen-Deckel + Ramp-Wächter besonders wichtig. Wie `safety_gate.py`/`sentinel.py`
  macht dieses Skript die Prosa-Regel "nicht zu schnell rampen" zu einem
  DETERMINISTISCHEN, testbaren Urteil — kein LLM-Rauschen.

METHODE (ACWR — Acute:Chronic Workload Ratio):
  - Acute   = Last der JÜNGSTEN Woche (7-Tage-Fenster).
  - Chronic = rollender Mittelwert der letzten 4 Wochen (28-Tage-Fenster) =
              die eingeschwungene Gewohnheits-Last.
  - ACWR    = acute / chronic. Der "Sweet Spot" liegt im Band ~0.8–1.3; über 1.3
              steigt das Verletzungs-Risiko (etablierte Sportwissenschafts-Heuristik,
              Gabbett). RAMP_FLAG feuert bei ACWR > RAMP_MAX (1.3).
  - Ceiling = CEILING_FACTOR (1.3) × Chronic = empfohlene Obergrenze der nächsten
              Wochen-Last, damit man im Sweet Spot bleibt (1.3 = oberer Rand des Bands).

⛔ KERNREGEL (CLAUDE.md §0): Dieses Skript konsumiert NUR reduzierte Aggregate —
  eine Liste Wochen-Lasten ODER eine Tages-Last-Reihe (1 Wert/Tag), die zu Wochen
  aggregiert wird. NIE rohe Per-Sekunde-/Per-Minute-Serien. Ausgabe = kompaktes JSON.

Last-Einheit ist frei (km ODER TRIMP/Load) — die ACWR-Mathematik ist einheitsneutral;
`week_km`/`ceiling_km` heißen so, weil der Default-Use-Case Wochen-KM ist (FR970-Mileage).

CLI:
  python running_tolerance.py --weekly 28,30,32,34 [--as-of YYYY-MM-DD]
  python running_tolerance.py --daily 5,0,8,...      # 1 Wert/Tag, wird zu Wochen aggregiert
  python running_tolerance.py --trainings <dump.csv> # aus Trainings_v5 (dedup+TRIMP)
  "-" als --weekly/--daily liest die Liste von stdin.

API:
  from running_tolerance import compute_tolerance
  res = compute_tolerance([28, 30, 32, 34], as_of="2026-06-28")
"""
import argparse
import json
import sys

from datetime import date, datetime, timedelta

# ── Schwellen (dokumentiert, NICHT willkürlich) ──────────────────────────────
ACUTE_WEEKS = 1     # Acute-Fenster = jüngste Woche (7 d)
CHRONIC_WEEKS = 4   # Chronic-Fenster = 4 Wochen (28 d rollender Mittel)
RAMP_MAX = 1.3      # ACWR-Obergrenze des Sweet Spots (Gabbett); darüber = Ramp-Alarm
ACWR_LOW = 0.8      # untere Sweet-Spot-Grenze; darunter = Detraining/Unterlast
CEILING_FACTOR = 1.3  # Ceiling = Faktor × Chronic (= oberer Rand des Sweet Spots)

_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d.%m.%y",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M",
)


def _parse_date(s):
    """ISO/dt. Datum → date oder None (Mirror von banister._parse_date)."""
    if isinstance(s, (date, datetime)):
        return s.date() if isinstance(s, datetime) else s
    s = str(s).strip()
    if not s:
        return None
    head = s.split()[0].split("T")[0] if (" " in s or "T" in s) else s
    for cand in (s, head):
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(cand, fmt).date()
            except ValueError:
                continue
    return None


def _to_float(x):
    """Robuste (ggf. deutsche) Dezimalzahl → float oder None."""
    if x is None:
        return None
    try:
        return float(str(x).replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None


def daily_to_weekly(daily_loads):
    """Tages-Last-Reihe (älteste→neueste, 1 Wert/Tag) → Wochen-Summen (7er-Blöcke).

    Aggregiert von HINTEN, damit die jüngste Woche immer ein voller 7-Tage-Block
    am Ende ist (FR970-Logik: 'die letzten 7 Tage'). Ein Rest-Block am Anfang
    (<7 Tage) wird verworfen — eine angebrochene Alt-Woche verzerrt den Chronic-
    Mittelwert sonst nach unten.
    """
    vals = [_to_float(v) for v in daily_loads]
    vals = [v for v in vals if v is not None]
    if not vals:
        return []
    weeks = []
    # von hinten in 7er-Blöcke schneiden
    i = len(vals)
    while i - 7 >= 0:
        weeks.append(sum(vals[i - 7:i]))
        i -= 7
    weeks.reverse()
    return weeks


def tolerance_ampel(acwr):
    """ACWR → Ampel (CLAUDE.md §5-Schema, an den Sweet-Spot gebunden)."""
    if acwr is None:
        return "⚪"
    if acwr > RAMP_MAX:
        return "🔴"           # Ramp zu steil → Verletzungs-Risiko
    if acwr >= ACWR_LOW:
        return "🟢"           # im Sweet Spot
    return "🟡"               # Unterlast / Detraining-Drift (kein Drama)


def tolerance_status(acwr):
    """ACWR → Status-Label (maschinenlesbar, stabil)."""
    if acwr is None:
        return "unknown"
    if acwr > RAMP_MAX:
        return "ramp_too_steep"
    if acwr >= ACWR_LOW:
        return "sweet_spot"
    return "underloaded"


def compute_tolerance(weekly_loads, as_of=None):
    """
    weekly_loads: Liste Wochen-Lasten, älteste→neueste; letzter Wert = aktuelle Woche.
                  (Roh-Tageswerte vorher via daily_to_weekly aggregieren.)
    as_of:        heutiges Datum (str/date), nur fürs Echo — keine Wall-Clock-Logik.

    Rückgabe (kompaktes Aggregat, §0):
      {week_km, ceiling_km, acwr, ramp_flag, status, ampel, chronic_km,
       acute_weeks, chronic_weeks, ramp_max, ceiling_factor, n_weeks, as_of?}
        - week_km     = Last der aktuellen (jüngsten) Woche = Acute.
        - chronic_km  = Mittel der letzten CHRONIC_WEEKS Wochen.
        - acwr        = week_km / chronic_km (None, wenn chronic == 0).
        - ceiling_km  = CEILING_FACTOR × chronic_km.
        - ramp_flag   = acwr > RAMP_MAX (True nur über, NICHT auf der Schwelle).
        - status      ∈ {sweet_spot, ramp_too_steep, underloaded, unknown}.
    """
    if isinstance(as_of, str):
        parsed = _parse_date(as_of)
        if parsed is None:
            raise ValueError(f"--as-of nicht parsebar: {as_of!r}")
        as_of = parsed

    weeks = [_to_float(w) for w in (weekly_loads or [])]
    weeks = [w for w in weeks if w is not None]
    if not weeks:
        raise ValueError("Leere Wochen-Last-Reihe — keine ACWR-Berechnung möglich.")
    if any(w < 0 for w in weeks):
        raise ValueError("Negative Wochen-Last unzulässig.")

    week_km = round(weeks[-1], 1)                       # Acute = jüngste Woche
    chronic_window = weeks[-CHRONIC_WEEKS:]             # bis zu 4 Wochen (auch kürzer)
    chronic = sum(chronic_window) / len(chronic_window)
    ceiling = round(CEILING_FACTOR * chronic, 1)

    acwr = round(weeks[-1] / chronic, 2) if chronic > 0 else None
    ramp_flag = acwr is not None and acwr > RAMP_MAX
    status = tolerance_status(acwr)

    out = {
        "week_km": week_km,
        "ceiling_km": ceiling,
        "acwr": acwr,
        "ramp_flag": ramp_flag,
        "status": status,
        "ampel": tolerance_ampel(acwr),
        "chronic_km": round(chronic, 1),
        "acute_weeks": ACUTE_WEEKS,
        "chronic_weeks": min(CHRONIC_WEEKS, len(chronic_window)),
        "ramp_max": RAMP_MAX,
        "ceiling_factor": CEILING_FACTOR,
        "n_weeks": len(weeks),
        "chronic_full": len(weeks) >= CHRONIC_WEEKS,
    }
    if as_of is not None:
        out["as_of"] = as_of.isoformat()
    return out


def _weekly_from_trainings(raw_text, as_of=None):
    """Trainings_v5-Dump → Wochen-TRIMP-Reihe (Reuse: dedup + banister-TRIMP-Extrakt).

    Baut über die Tages-TRIMP-Summen eine lückenlose Tagesreihe (Ruhetage = 0) bis
    `as_of − 1` (gleiche Konvention wie banister) und aggregiert sie zu Wochen.
    """
    from dedup_trainings import dedup
    from banister import extract_daily_trimp

    clean, rep = dedup(raw_text)
    daily_trimp, _ = extract_daily_trimp(clean, rep.get("header"))
    if not daily_trimp:
        raise ValueError("Keine TRIMP-Tagesdaten im Trainings-Dump erkannt.")

    if isinstance(as_of, str):
        as_of = _parse_date(as_of)
    start = min(daily_trimp)
    end = (as_of - timedelta(days=1)) if as_of else max(daily_trimp)
    if end < start:
        end = start

    series, d = [], start
    while d <= end:
        series.append(daily_trimp.get(d, 0.0))
        d += timedelta(days=1)
    return daily_to_weekly(series)


def _parse_list(spec):
    """'-' = stdin, sonst Komma-/Whitespace-getrennte Zahlen-Liste."""
    if spec == "-":
        spec = sys.stdin.read()
    parts = [p for p in spec.replace("\n", ",").replace(";", ",").split(",")]
    return [p.strip() for p in parts if p.strip() != ""]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Lauf-Toleranz-Klon (FR970): Wochen-Volumen-Deckel + ACWR-Ramp-Wächter. "
                    "Konsumiert NUR Aggregate (Wochen-/Tages-Lasten), nie Roh-Serien.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--weekly", help="Wochen-Lasten, Komma-getrennt (älteste→neueste) oder '-'.")
    src.add_argument("--daily", help="Tages-Lasten, Komma-getrennt (1 Wert/Tag) oder '-'.")
    src.add_argument("--trainings", help="Trainings_v5-Dump (Datei) → Wochen-TRIMP via dedup+banister.")
    ap.add_argument("--as-of", default=None, dest="as_of",
                    help="Heutiges Datum YYYY-MM-DD (deterministisch, keine Wall-Clock).")
    args = ap.parse_args(argv)

    try:
        if args.weekly is not None:
            weekly = _parse_list(args.weekly)
        elif args.daily is not None:
            weekly = daily_to_weekly(_parse_list(args.daily))
        else:
            raw = open(args.trainings, encoding="utf-8", errors="replace").read()
            weekly = _weekly_from_trainings(raw, as_of=args.as_of)
        res = compute_tolerance(weekly, as_of=args.as_of)
    except (ValueError, FileNotFoundError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, separators=(",", ":")))
        return 2

    print(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
