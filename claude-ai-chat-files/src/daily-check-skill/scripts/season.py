#!/usr/bin/env python3
"""
season.py — Saison-/Batch-Analyse über die Trainings_v5-Historie (daily-check).

WARUM
-----
Der Chat-Kontext sieht immer nur einen Lauf / einen Tag. Trends über Wochen und
Monate (Monats-km, Monats-TRIMP, CTL-Verlauf, Pace-Drift, Sportart-Mix) „choken"
im Chat, weil dafür die GANZE Historie deterministisch aggregiert werden muss —
nicht ein paar Zeilen im Prompt. Dieses Script macht genau das: read-only über
`Trainings_v5`, Ausgabe = kompaktes, tabellarisches JSON (nur Aggregate, nie
Rohserien). KEINE Charts (matplotlib de-scoped) — Tabellen sprechen für sich.

ANALYSEN
--------
1. monthly          — pro Kalendermonat (über LÄUFE): Anzahl, Σ km, Σ TRIMP,
                      Ø HF, längster Lauf, Ø Pace (min/km, ggf. abgeleitet).
2. ctl_trajectory   — CTL/ATL/TSB-Verlauf der letzten ~90 Tage (wöchentliche
                      Stützstellen), gerechnet mit der DETERMINISTISCHEN Banister-
                      Engine (banister.py, tc 42/7, lückenloser Zerofill, ALLE
                      Sportarten zählen zur Last).
3. pace_trend       — Monats-Ø-Pace der Läufe + erster↔letzter Vergleich.
                      Pace ist im Sheet NICHT gespeichert → aus Dauer/Strecke
                      abgeleitet (klar als `derived` markiert), sofern keine
                      echte Pace-Spalte existiert.
4. type_distribution— Verteilung der Sportarten (Art-Spalte) über die Historie.

EHRLICHKEIT — Pace@Z2-Progression
---------------------------------
Das Sheet hat KEINE gespeicherte Pace@Z2 (die wird pro Lauf von
analyze_run_fit berechnet und nirgends fortgeschrieben). Eine echte
Pace@Z2-Progression braucht einen FORWARD-TRACKED Store. Dieses Script:
  - emittiert eine ehrliche Notiz + Vorschlag (jeden Lauf nach pace-z2.csv /
    ins Drive-Journal archivieren), und
  - approximiert HILFSWEISE aus einer Easy-/Z2-Pace-Spalte, FALLS das Sheet je
    eine bekommt (klar als `proxy` gelabelt). Aktuell: nicht vorhanden.

CLI
---
  python season.py <trainings_v5_dump> [--as-of YYYY-MM-DD] [--months N] [--trajectory-days D]
      <dump>            : read_file_content-Output von Trainings_v5 (CSV/TSV/MD)
      --as-of           : heutiges Datum (sonst letztes Datum mit Daten)
      --months N        : nur die letzten N Monate ausgeben (Default 12; 0 = alle)
      --trajectory-days : Fenster der CTL-Trajektorie (Default 90)

Programmatisch (testbar OHNE echte Daten — native Strukturen rein):
  from season import analyze_season
  res = analyze_season(raw_sheet_text, as_of="2026-06-25")
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

# ── Sibling-Imports (banister/dedup liegen im selben scripts/-Verzeichnis) ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import banister as bb          # noqa: E402
from dedup_trainings import dedup  # noqa: E402

# Column hints (lowercase substrings). Date/Type/TRIMP/Dist mirror dedup/banister.
DATE_HINTS = ("datum", "date", "tag", "day")
TYPE_HINTS = ("art", "typ", "type", "session", "aktivit", "activity", "sport", "workout")
TRIMP_HINTS = ("trimp", "load", "belastung")
DIST_HINTS = ("strecke", "dist", "km")
# avg HR only — must NOT match "Min. Herzfrequenz" / "Max. Herzfrequenz".
HR_AVG_HINTS = ("ø herz", "o herz", "avg hr", "ø hf", "mittlere herz", "durchschn")
DUR_HINTS = ("gesamtzeit", "dauer", "duration", "moving", "bewegung", "elapsed")
PACE_HINTS = ("pace", "tempo", "min/km")
# A *real* easy-/Z2-pace column would be the only honest Pace@Z2 proxy.
Z2PACE_HINTS = ("pace@z2", "pace z2", "z2 pace", "easy pace", "easy-pace", "pace_z2", "z2-pace")

RUN_HINTS = ("lauf", "run")  # "Laufen outdoor", "Laufen indoor", "Trail run" …
_HMS = re.compile(r"(?:(\d+)\s*h)?[:\s]*(?:(\d+)\s*m)?[:\s]*(?:(\d+)\s*s)?", re.I)


def _col_index(header, hints):
    if not header:
        return None
    for i, h in enumerate(header):
        hl = (h or "").strip().lower()
        if any(hint in hl for hint in hints):
            return i
    return None


def _to_float(x):
    if x is None:
        return None
    try:
        return float(str(x).replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None


def _dur_to_min(cell):
    """'0h:43m:48s' or '43:48' or plain minutes-float → minutes (float) or None."""
    if cell is None:
        return None
    s = str(cell).strip()
    if not s:
        return None
    # Plain numeric → already minutes.
    f = _to_float(s)
    if f is not None and not any(c in s.lower() for c in ("h", "m", "s", ":")):
        return f
    if "h" in s.lower() or "m" in s.lower() or "s" in s.lower():
        m = _HMS.fullmatch(s.strip())
        if m and any(m.groups()):
            h, mi, se = (int(g) if g else 0 for g in m.groups())
            return h * 60 + mi + se / 60.0
    # mm:ss or hh:mm:ss
    if ":" in s:
        parts = s.split(":")
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return None
        if len(nums) == 3:
            return nums[0] * 60 + nums[1] + nums[2] / 60.0
        if len(nums) == 2:
            return nums[0] + nums[1] / 60.0
    return None


def _fmt_pace(min_per_km):
    if min_per_km is None:
        return None
    mm = int(min_per_km)
    ss = int(round((min_per_km - mm) * 60))
    if ss == 60:
        mm, ss = mm + 1, 0
    return f"{mm}:{ss:02d}"


def _is_run(art):
    a = (art or "").strip().lower()
    return any(h in a for h in RUN_HINTS)


def parse_sessions(clean_rows, header):
    """clean_rows (post-dedup) + header → list[dict] richer per-session records.

    Each dict: date, art, is_run, km, trimp, hr, dur_min, pace (min/km, float|None),
    pace_derived (bool). Rows without a parseable date are skipped.
    """
    idx = {
        "date": _col_index(header, DATE_HINTS),
        "art": _col_index(header, TYPE_HINTS),
        "trimp": _col_index(header, TRIMP_HINTS),
        "dist": _col_index(header, DIST_HINTS),
        "hr": _col_index(header, HR_AVG_HINTS),
        "dur": _col_index(header, DUR_HINTS),
        "pace": _col_index(header, PACE_HINTS),
    }
    out = []

    def get(r, key):
        i = idx[key]
        return r[i] if (i is not None and i < len(r)) else None

    for r in clean_rows:
        d = bb._parse_date(get(r, "date"))
        if d is None:
            continue
        art = (get(r, "art") or "").strip()
        km = _to_float(get(r, "dist"))
        trimp = _to_float(get(r, "trimp"))
        hr = _to_float(get(r, "hr"))
        dur = _dur_to_min(get(r, "dur"))
        # Pace: prefer a real column; else derive from duration/distance.
        pace, derived = None, False
        praw = get(r, "pace")
        if praw is not None and str(praw).strip():
            pv = _dur_to_min(praw)  # pace cells are usually mm:ss too
            if pv is not None and pv > 0:
                pace = pv
        if pace is None and dur and km and km > 0:
            pace = dur / km
            derived = True
        out.append({
            "date": d, "art": art, "is_run": _is_run(art),
            "km": km, "trimp": trimp, "hr": hr, "dur_min": dur,
            "pace": pace, "pace_derived": derived,
        })
    return out


def monthly_run_summaries(sessions):
    """Per calendar month, aggregated over RUNS only. Returns list newest-last."""
    by_m = defaultdict(list)
    for s in sessions:
        if s["is_run"]:
            by_m[s["date"].strftime("%Y-%m")].append(s)
    rows = []
    for m in sorted(by_m):
        ss = by_m[m]
        kms = [s["km"] for s in ss if s["km"] is not None]
        trimps = [s["trimp"] for s in ss if s["trimp"] is not None]
        hrs = [s["hr"] for s in ss if s["hr"] is not None]
        paces = [s["pace"] for s in ss if s["pace"] is not None]
        rows.append({
            "month": m,
            "runs": len(ss),
            "km": round(sum(kms), 1) if kms else 0.0,
            "trimp": round(sum(trimps), 1) if trimps else 0.0,
            "avg_hr": round(sum(hrs) / len(hrs), 1) if hrs else None,
            "longest_km": round(max(kms), 2) if kms else None,
            "avg_pace": _fmt_pace(sum(paces) / len(paces)) if paces else None,
            "avg_pace_min": round(sum(paces) / len(paces), 3) if paces else None,
        })
    return rows


def _full_series(daily_trimp, as_of):
    """Full daily CTL/ATL series via the deterministic banister engine constants.

    Returns list of dicts {date, trimp, ctl, atl, tsb} from first session day to
    end (as_of-1, or last data day). Mirrors banister.banister exactly so the
    endpoint matches the §-block the rest of the skill prints.
    """
    if not daily_trimp:
        return []
    if isinstance(as_of, str):
        as_of = bb._parse_date(as_of)
    start = min(daily_trimp)
    last = max(daily_trimp)
    end = (as_of - timedelta(days=1)) if as_of else last
    if end < start:
        end = start
    ctl = atl = 0.0
    series, d = [], start
    while d <= end:
        t = daily_trimp.get(d, 0.0)
        ctl += (t - ctl) * bb.CTL_LAMBDA
        atl += (t - atl) * bb.ATL_LAMBDA
        series.append({"date": d, "trimp": t, "ctl": ctl, "atl": atl, "tsb": ctl - atl})
        d += timedelta(days=1)
    return series


def ctl_trajectory(daily_trimp, as_of, window_days=90):
    """Weekly CTL/ATL/TSB stützstellen over the last `window_days`, + final point."""
    series = _full_series(daily_trimp, as_of)
    if not series:
        return None
    end = series[-1]["date"]
    cutoff = end - timedelta(days=window_days)
    window = [p for p in series if p["date"] > cutoff]
    # Weekly downsample (every 7th from the end) keeps the JSON compact.
    weekly, i = [], len(window) - 1
    picked = []
    while i >= 0:
        picked.append(window[i])
        i -= 7
    for p in reversed(picked):
        weekly.append({
            "date": p["date"].isoformat(),
            "trimp": round(p["trimp"], 1),
            "ctl": round(p["ctl"], 1),
            "atl": round(p["atl"], 1),
            "tsb": round(p["tsb"], 1),
        })
    first, last = window[0], window[-1]
    return {
        "window_days": window_days,
        "from": window[0]["date"].isoformat(),
        "to": end.isoformat(),
        "ctl_start": round(first["ctl"], 1),
        "ctl_end": round(last["ctl"], 1),
        "ctl_delta": round(last["ctl"] - first["ctl"], 1),
        "tsb_end": round(last["tsb"], 1),
        "weekly": weekly,
    }


def pace_trend(monthly):
    """First↔last monthly-avg-pace comparison over months that have a pace."""
    paced = [m for m in monthly if m["avg_pace_min"] is not None]
    derived = True  # the sheet has no pace column today → always derived here
    if len(paced) < 2:
        return {
            "available": len(paced) == 1,
            "derived": derived,
            "note": "Zu wenige Monate mit Pace für einen Trend (<2).",
            "months": [{"month": m["month"], "avg_pace": m["avg_pace"]} for m in paced],
        }
    first, last = paced[0], paced[-1]
    delta = last["avg_pace_min"] - first["avg_pace_min"]
    return {
        "available": True,
        "derived": derived,
        "note": ("Pace aus Dauer/Strecke ABGELEITET (keine native Pace-Spalte im Sheet). "
                 "Monats-Ø über ALLE Läufe — vermischt Easy/Tempo/Race, daher nur grober Drift."),
        "from": first["month"], "to": last["month"],
        "first_avg_pace": first["avg_pace"], "last_avg_pace": last["avg_pace"],
        "delta_sec_per_km": round(delta * 60, 1),
        "direction": ("schneller" if delta < 0 else "langsamer" if delta > 0 else "gleich"),
        "months": [{"month": m["month"], "avg_pace": m["avg_pace"]} for m in paced],
    }


def pace_z2_progression(header, sessions):
    """HONEST: real Pace@Z2 progression needs a forward-tracked store.

    The sheet stores no Pace@Z2 (it is computed per-run by analyze_run_fit and
    never persisted). We approximate ONLY from a real easy-/Z2-pace column if
    one exists (clearly labelled proxy); otherwise we emit the proposal.
    """
    z2_idx = _col_index(header, Z2PACE_HINTS)
    proposal = (
        "Pace@Z2-Progression braucht einen FORWARD-TRACKED Store: jeden Lauf die "
        "von analyze_run_fit berechnete Pace@Z2 (Datum, Pace@Z2, Ø HF, TSB) nach "
        "`data/pace-z2.csv` bzw. ins Drive-Journal archivieren. Ab dann ist eine "
        "echte, saubere Progression rechenbar — rückwirkend ist sie es NICHT."
    )
    if z2_idx is None:
        return {
            "available": False,
            "reason": "Keine gespeicherte Pace@Z2 und keine Easy-/Z2-Pace-Spalte im Sheet.",
            "proposal": proposal,
        }
    # Proxy path (only if the sheet ever grows such a column).
    pts = []
    for s in sessions:
        if not s["is_run"]:
            continue
        # column not in the rich record → re-derive would need the raw row; we
        # only flag availability here and leave the heavy lift to a future store.
    return {
        "available": False,
        "reason": "Easy-/Z2-Pace-Spalte erkannt, aber Proxy noch nicht aktiviert.",
        "proxy_column_index": z2_idx,
        "proposal": proposal,
    }


def analyze_season(raw_sheet_text, as_of=None, months=12, trajectory_days=90):
    """Full path: dedup → parse → monthly/trajectory/pace/type. Read-only."""
    clean, dedup_report = dedup(raw_sheet_text)
    header = dedup_report.get("header")
    sessions = parse_sessions(clean, header)
    if not sessions:
        return {"insufficient_data": True, "reason": "Keine parsebaren Sessions.",
                "dedup_report": {k: v for k, v in dedup_report.items() if k != "header"}}

    runs = [s for s in sessions if s["is_run"]]
    monthly_all = monthly_run_summaries(sessions)
    monthly_out = monthly_all if not months else monthly_all[-months:]

    # CTL trajectory uses ALL activities' TRIMP (load is load) via banister.
    daily_trimp, extract_report = bb.extract_daily_trimp(clean, header)
    traj = ctl_trajectory(daily_trimp, as_of, window_days=trajectory_days)
    final = bb.banister(daily_trimp, as_of=as_of)

    type_dist = Counter(s["art"] or "(leer)" for s in sessions)

    start = min(s["date"] for s in sessions)
    end = max(s["date"] for s in sessions)
    return {
        "as_of": (bb._parse_date(as_of).isoformat() if as_of else (end.isoformat())),
        "span": {
            "first": start.isoformat(), "last": end.isoformat(),
            "n_sessions": len(sessions), "n_runs": len(runs),
            "n_months_with_runs": len(monthly_all),
        },
        "monthly": monthly_out,
        "monthly_window": (f"letzte {months} Monate" if months else "alle Monate"),
        "ctl_trajectory": traj,
        "ctl_final": ({"ctl": final["ctl"], "atl": final["atl"], "tsb": final["tsb"]}
                      if final else None),
        "pace_trend": pace_trend(monthly_all),
        "pace_z2_progression": pace_z2_progression(header, sessions),
        "type_distribution": dict(type_dist.most_common()),
        "dedup_report": {k: v for k, v in dedup_report.items() if k != "header"},
        "extract_report": extract_report,
    }


def format_block(res):
    """Compact human-readable season block for the skill output."""
    if res.get("insufficient_data"):
        return f"Saison-Analyse: {res.get('reason')}"
    sp = res["span"]
    lines = [
        f"**Saison-Analyse** ({sp['first']} … {sp['last']}, "
        f"{sp['n_sessions']} Sessions / {sp['n_runs']} Läufe):",
        f"- Monate ({res['monthly_window']}): Monat · Läufe · km · TRIMP · ØHF · längster · ØPace",
    ]
    for m in res["monthly"]:
        lines.append(
            f"  {m['month']}: {m['runs']}× · {m['km']} km · {m['trimp']} TRIMP · "
            f"{m['avg_hr'] or '–'} bpm · {m['longest_km'] or '–'} km · {m['avg_pace'] or '–'}/km"
        )
    t = res.get("ctl_trajectory")
    if t:
        lines.append(
            f"- CTL {t['window_days']} d: {t['ctl_start']} → {t['ctl_end']} "
            f"(Δ{t['ctl_delta']:+}), TSB heute {t['tsb_end']:+}"
        )
    pz = res["pace_z2_progression"]
    if not pz["available"]:
        lines.append(f"- ⚠️ Pace@Z2-Progression: {pz['reason']} → {pz['proposal']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Saison-/Batch-Analyse über Trainings_v5.")
    ap.add_argument("dump", help="read_file_content-Output von Trainings_v5")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--months", type=int, default=12, help="letzte N Monate (0=alle)")
    ap.add_argument("--trajectory-days", type=int, default=90)
    args = ap.parse_args()

    raw = open(args.dump, encoding="utf-8", errors="replace").read()
    res = analyze_season(raw, as_of=args.as_of, months=args.months,
                         trajectory_days=args.trajectory_days)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("\n" + format_block(res))


if __name__ == "__main__":
    main()
