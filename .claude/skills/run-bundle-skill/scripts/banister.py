#!/usr/bin/env python3
"""
banister.py — Deterministische CTL/ATL/TSB-Berechnung (run-bundle + daily-check)

PROBLEM
-------
Ad-hoc gerechnet schwankte der TSB zwischen Läufen für DENSELBEN Tag (z. B.
+10,3 vs −0,5) bei identischen Rohdaten. Ursachen: (a) Ruhetage wurden NICHT
mit TRIMP 0 aufgefüllt (nur Session-Zeilen ge-EWMA-t → keine Decay-Tage →
ATL/CTL überhöht & instabil), (b) wechselnde Seeds/Anker, (c) Rundung.

LÖSUNG (deterministisch, reproduzierbar)
----------------------------------------
1. Dedup (via dedup_trainings) → eindeutige Sessions.
2. TRIMP pro KALENDERTAG summieren.
3. Lückenlose Tagesreihe `start … (as_of − 1)` bauen, **Ruhetage = TRIMP 0**.
4. Feste Decay-Konstanten: CTL 42 d, ATL 7 d. Seed CTL=ATL=0 vor `start`.
5. TSB = CTL − ATL am Ende der Reihe = **Form am Morgen von `as_of` (= heute)**,
   entspricht der Daily-Check-Definition „TSB = CTL_gestern − ATL_gestern".

Gleiche Reihe → gleiche Zahl, Lauf für Lauf. Read-only (kein Sheet-Write).

KONVENTION
----------
- `as_of` = heutiges Datum (aus Claude-Kontext; Datum ist zuverlässig, nur die
  Uhrzeit nicht). Reihe läuft bis `as_of − 1` (gestern). TSB = Form für heute.
- Ohne `as_of`: `end` = letztes Datum mit Daten; TSB = Form am Folgetag.

CLI:  python banister.py <trainings_v5_dump>  [YYYY-MM-DD]
API:  from banister import compute_from_sheet
      res = compute_from_sheet(raw_sheet_text, as_of="2026-06-24")
"""

import sys
import math
from datetime import date, datetime, timedelta

CTL_TC = 42          # Tage (Fitness)
ATL_TC = 7           # Tage (Ermüdung)
CTL_LAMBDA = 1 - math.exp(-1 / CTL_TC)   # ≈ 0.023525
ATL_LAMBDA = 1 - math.exp(-1 / ATL_TC)   # ≈ 0.133280
WARMUP_DAYS = 3 * CTL_TC                  # 126 = volle CTL-Konvergenz

DATE_HINTS = ("datum", "date", "tag", "day")
TRIMP_HINTS = ("trimp", "load", "belastung")

_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d.%m.%y",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M",
)


def _parse_date(s):
    if isinstance(s, (date, datetime)):
        return s.date() if isinstance(s, datetime) else s
    s = str(s).strip()
    if not s:
        return None
    # ISO-Datum am Zeilenanfang herausschneiden (z. B. "2026-06-14 ...")
    head = s.split()[0].split("T")[0] if (" " in s or "T" in s) else s
    for cand in (s, head):
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(cand, fmt).date()
            except ValueError:
                continue
    return None


def _to_float(x):
    if x is None:
        return None
    try:
        return float(str(x).replace(",", ".").strip())
    except ValueError:
        return None


def _col_index(header, hints):
    if not header:
        return None
    for i, h in enumerate(header):
        if any(hint in (h or "").strip().lower() for hint in hints):
            return i
    return None


def extract_daily_trimp(clean_rows, header):
    """clean_rows (aus dedup) + header → {date: TRIMP-Summe}, plus Skip-Report."""
    di = _col_index(header, DATE_HINTS)
    ti = _col_index(header, TRIMP_HINTS)
    daily, skipped = {}, 0
    if di is None or ti is None:
        return daily, {"skipped": len(clean_rows), "reason": "Datum-/TRIMP-Spalte nicht erkannt"}
    for r in clean_rows:
        if di >= len(r) or ti >= len(r):
            skipped += 1
            continue
        d = _parse_date(r[di])
        t = _to_float(r[ti])
        if d is None or t is None:
            skipped += 1
            continue
        daily[d] = daily.get(d, 0.0) + t
    return daily, {"skipped": skipped, "reason": None}


def banister(daily_trimp, as_of=None):
    """
    daily_trimp: {date: TRIMP-Summe je Kalendertag}
    as_of:       heutiges Datum (str/date) — Reihe läuft bis as_of-1. Optional.
    Rückgabe:    dict mit ctl/atl/tsb (gerundet) + Metadaten + 7-Tage-Tail.
    """
    if not daily_trimp:
        return None
    if isinstance(as_of, str):
        as_of = _parse_date(as_of)

    start = min(daily_trimp)
    last_data = max(daily_trimp)
    end = (as_of - timedelta(days=1)) if as_of else last_data
    if end < start:
        end = start  # as_of liegt vor jeder Session → mind. ein Tag

    ctl = atl = 0.0
    tail = []
    d = start
    n_days = 0
    while d <= end:
        t = daily_trimp.get(d, 0.0)
        ctl += (t - ctl) * CTL_LAMBDA
        atl += (t - atl) * ATL_LAMBDA
        tail.append((d.isoformat(), round(t, 1), round(ctl, 1), round(atl, 1), round(ctl - atl, 1)))
        d += timedelta(days=1)
        n_days += 1

    tsb = ctl - atl
    span = (end - start).days
    return {
        "ctl": round(ctl, 1),
        "atl": round(atl, 1),
        "tsb": round(tsb, 1),
        "as_of": (as_of.isoformat() if as_of else (end + timedelta(days=1)).isoformat()),
        "series_start": start.isoformat(),
        "series_end": end.isoformat(),
        "n_calendar_days": n_days,
        "n_session_days": len(daily_trimp),
        "warmup_ok": span >= WARMUP_DAYS,
        "warmup_days_needed": WARMUP_DAYS,
        "span_days": span,
        "tail7": tail[-7:],
        "seed": "CTL=ATL=0 vor series_start (deterministisch)",
    }


def compute_from_sheet(raw_sheet_text, as_of=None):
    """Komplettpfad: dedup → extract → banister. Liefert Banister-Ergebnis + Reports."""
    from dedup_trainings import dedup
    clean, dedup_report = dedup(raw_sheet_text)
    daily, extract_report = extract_daily_trimp(clean, dedup_report.get("header"))
    res = banister(daily, as_of=as_of)
    if res is not None:
        res["dedup_report"] = dedup_report
        res["extract_report"] = extract_report
    return res


def tsb_ampel(tsb):
    if tsb > 5:
        return "🟢"      # frisch/Peak
    if tsb >= -10:
        return "🟡"      # neutral/ausbalanciert
    if tsb >= -30:
        return "🟠"      # ermüdet
    return "🔴"          # tiefe Ermüdung


def format_block(res):
    """Report-fertiger CTL/ATL/TSB-Block."""
    if res is None:
        return "CTL/ATL/TSB: keine Trainingsdaten verfügbar."
    amp = tsb_ampel(res["tsb"])
    lines = [
        f"- Fitness (CTL): {res['ctl']} · Ermüdung (ATL): {res['atl']} · "
        f"**Form (TSB heute): {res['tsb']:+}** {amp} (= Readiness am Morgen von {res['as_of']})",
    ]
    if not res["warmup_ok"]:
        lines.append(
            f"  ⚠️ Historie nur {res['span_days']} d (<{res['warmup_days_needed']} d) → "
            f"CTL evtl. unter-eingeschwungen, TSB-Trend belastbarer als Absolutwert."
        )
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    as_of = sys.argv[2] if len(sys.argv) > 2 else None
    res = compute_from_sheet(raw, as_of=as_of)
    if res is None:
        print("Keine Daten."); return
    import json
    show = {k: v for k, v in res.items() if k not in ("dedup_report", "tail7")}
    print(json.dumps(show, ensure_ascii=False, indent=2))
    print("\nLetzte 7 Tage (Datum, TRIMP, CTL, ATL, TSB):")
    for row in res["tail7"]:
        print("  ", row)
    print("\n" + format_block(res))


if __name__ == "__main__":
    main()
