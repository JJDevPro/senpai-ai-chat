#!/usr/bin/env python3
"""
trend_snapshot.py — rollt readiness-history.csv zu einem kurzen Woche+Monat-Trend.

WARUM (CLAUDE.md §7 Snapshot-Stufe):
  Statt jede Session die vollen Drive-Sheets zu ziehen + banister 126 Tage zu
  replayen, liest Senpai EINEN kompakten, menschenlesbaren Snapshot:
    Tabelle A = letzte ~8 ISO-Wochen, Tabelle B = letzte ~6–12 Monate.
  Quelle ist die granulare `readiness-history.csv` (1 Zeile/Tag, von daily-check/
  run-bundle gepflegt). Die Roh-Sheets in Drive bleiben für den Deep-Dive.

⛔ KERNREGEL (§0): liest NUR schon-reduzierte Tages-Aggregate, schreibt EINEN
  kompakten md-Rollup. Keine Roh-Serien. Pure rollup/render-Logik ist Drive-frei
  und unit-testbar (siehe tests/test_trend_snapshot.py).

⛔ Snapshot ≠ Ersatz: für abgeschlossene Wochen/Monate so genau wie Neurechnung;
  HEUTE wird nie gesnapshottet (immer frisch). Bei Lücke/Zweifel → Drive-Sheets.

MODI:
  (default) rollup:  readiness-history.csv ziehen → trend_snapshot.md bauen + uploaden.
  --backfill:        readiness-history.csv EINMALIG aus der Drive-Historie seeden
                     (Trainings_v5 → tägliche CTL/ATL/TSB; Tägliche Kennzahlen →
                     hrv_ms/rhr; Gewicht → weight/kfa) und uploaden.

CLI:
  python3 trend_snapshot.py --as-of YYYY-MM-DD [--weeks 8] [--months 12] [--out ./data]
  python3 trend_snapshot.py --backfill --trainings ./data/Trainings_v5.csv \
      [--kennzahlen ./data/Taegliche_Kennzahlen.csv] [--gewicht ./data/Gewicht.csv] --as-of YYYY-MM-DD
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
_LIB_DIR = _THIS_DIR.parents[3] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import readiness_history as rh  # Reader + append/Drive-Glue wiederverwenden

DEFAULT_FOLDER_ID = "1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde"
SNAPSHOT_NAME = "trend_snapshot.md"


# --------------------------------------------------------------------------- #
# Pure Rollup-Logik (Drive-frei, testbar)
# --------------------------------------------------------------------------- #
def _f(x):
    if x is None:
        return None
    s = str(x).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%Y/%m/%d")


def _d(s):
    s = str(s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s.split()[0], fmt).date()
        except ValueError:
            continue
    return None


def _avg(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 1) if v else None


def _last(vals):
    """Letzter nicht-leerer Wert (chronologisch)."""
    for x in reversed(vals):
        if x is not None:
            return x
    return None


def _bucket(rows, keyfn):
    """rows (chronologisch) → {bucket_key: [rows]} geordnet."""
    out = {}
    for r in rows:
        d = _d(r.get("date"))
        if d is None:
            continue
        out.setdefault(keyfn(d), []).append(r)
    return out


def _agg_bucket(label, brows):
    """Ein Wochen-/Monats-Aggregat aus den Tageszeilen eines Buckets."""
    def col(c):
        return [_f(r.get(c)) for r in brows]
    return {
        "label": label,
        "weight": _last(col("weight")),    # SoT = letzter Wert im Bucket
        "kfa": _last(col("kfa")),
        "hrv_ms": _avg(col("hrv_ms")),     # Ø über den Bucket
        "rhr": _avg(col("rhr")),
        "vo2": _last(col("vo2")),
        "ctl": _last(col("ctl")),          # Form am Bucket-Ende
        "atl": _last(col("atl")),
        "tsb": _last(col("tsb")),
        "week_km": _last(col("week_km")),
        "n_days": len([r for r in brows if _d(r.get("date"))]),
    }


def _iso_week_label(d):
    iso = d.isocalendar()
    return f"{iso[0]}-KW{iso[1]:02d}"


def rollup_weekly(rows, n_weeks=8):
    buckets = _bucket(rows, _iso_week_label)
    labels = sorted(buckets)[-n_weeks:]
    return [_agg_bucket(lbl, buckets[lbl]) for lbl in labels]


def rollup_monthly(rows, n_months=12):
    buckets = _bucket(rows, lambda d: f"{d.year}-{d.month:02d}")
    labels = sorted(buckets)[-n_months:]
    return [_agg_bucket(lbl, buckets[lbl]) for lbl in labels]


def _cell(v):
    return "—" if v is None else str(v)


def _table(title, buckets, label_col):
    head = (f"| {label_col} | ⚖️ Gewicht | KFA % | 💓 HRV-Ø | ❤️ RHR | 🫁 VO2 | "
            f"CTL (Fitness) | ATL (Fatigue) | TSB (Form) | 🏃 km |")
    sep = "|" + "---|" * 10
    lines = [f"### {title}", head, sep]
    for b in buckets:
        lines.append(
            f"| {b['label']} | {_cell(b['weight'])} | {_cell(b['kfa'])} | {_cell(b['hrv_ms'])} | "
            f"{_cell(b['rhr'])} | {_cell(b['vo2'])} | {_cell(b['ctl'])} | {_cell(b['atl'])} | "
            f"{_cell(b['tsb'])} | {_cell(b['week_km'])} |")
    return "\n".join(lines)


def render_snapshot(weekly, monthly, as_of=None, prs=None):
    """Zwei Markdown-Tabellen (Woche + Monat) + kurze Einordnung."""
    stamp = f" (Stand {as_of})" if as_of else ""
    parts = [
        f"# Senpai · Trend-Snapshot{stamp}",
        "",
        "> Schneller Read statt Sheet-Replay (CLAUDE.md §7). Abgeschlossene Wochen/Monate; HEUTE wird "
        "frisch gerechnet, nie hier gelesen. Bei Lücke/Deep-Dive → Roh-Sheets in Drive. "
        "Abk.: CTL (Fitness) · ATL (Fatigue) · TSB (Form) · KFA (Körperfett-%).",
        "",
        _table("📅 Letzte Wochen", weekly, "ISO-Woche"),
        "",
        _table("🗓️ Letzte Monate", monthly, "Monat"),
    ]
    if prs:
        parts += ["", "### 🏆 PRs / Meilensteine", prs.strip()]
    return "\n".join(parts) + "\n"


def build_from_csv_text(csv_text, as_of=None, weeks=8, months=12, prs=None):
    rows = rh.read_history(csv_text)
    return render_snapshot(rollup_weekly(rows, weeks), rollup_monthly(rows, months),
                           as_of=as_of, prs=prs)


# --------------------------------------------------------------------------- #
# Backfill: readiness-history.csv aus der Drive-Historie seeden (einmalig)
# --------------------------------------------------------------------------- #
def _daily_banister_series(trainings_text):
    """Trainings_v5-Dump → {date: (ctl, atl, tsb)} für JEDEN Kalendertag (Vollreplay
    der gleichen EWMA-Reihe wie banister, aber alle Tage statt nur tail7)."""
    import banister as b
    from dedup_trainings import dedup
    clean, dedup_report = dedup(trainings_text)
    daily, _ = b.extract_daily_trimp(clean, dedup_report.get("header"))
    if not daily:
        return {}
    start, end = min(daily), max(daily)
    ctl = atl = 0.0
    series = {}
    d = start
    while d <= end:
        t = daily.get(d, 0.0)
        ctl += (t - ctl) * b.CTL_LAMBDA
        atl += (t - atl) * b.ATL_LAMBDA
        series[d] = (round(ctl, 1), round(atl, 1), round(ctl - atl, 1))
        d += timedelta(days=1)
    return series


def _daily_from_kennzahlen(text):
    """Tägliche-Kennzahlen-CSV → {date: {hrv_ms, rhr}} (best-effort, Spalten-Heuristik)."""
    out = {}
    if not (text or "").strip():
        return out
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        d = None
        for k, v in r.items():
            if k and any(h in k.lower() for h in ("datum", "date", "tag")):
                d = _d(v)
                break
        if d is None:
            continue
        hrv = rhr = vo2 = None
        for k, v in r.items():
            kl = (k or "").lower()
            if hrv is None and ("hfv" in kl or "hrv" in kl):
                hrv = _f(v)
            if rhr is None and ("ruheherz" in kl or "rhr" in kl or "resting" in kl):
                rhr = _f(v)
            if vo2 is None and "vo" in kl and "max" in kl:
                vo2 = _f(v)
        out[d] = {
            "hrv_ms": round(hrv, 1) if hrv is not None else None,
            "rhr": round(rhr) if rhr is not None else None,
            "vo2": round(vo2, 1) if vo2 is not None else None,
        }
    return out


def _daily_from_gewicht(text):
    """Gewicht-CSV → {date: {weight, kfa}} (best-effort)."""
    out = {}
    if not (text or "").strip():
        return out
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        d = w = k = None
        for key, v in r.items():
            kl = (key or "").lower()
            if d is None and any(h in kl for h in ("datum", "date", "tag")):
                d = _d(v)
            elif w is None and ("gewicht" in kl or "weight" in kl):
                w = _f(v)
            elif k is None and ("fett" in kl or "kfa" in kl or "fat" in kl):
                k = _f(v)
        if k is not None and k < 1:   # Withings liefert Fett als Bruch (0.27 → 27 %)
            k = round(k * 100, 1)
        if d is not None:
            out[d] = {"weight": round(w, 1) if w is not None else None, "kfa": k}
    return out


def backfill_rows(trainings_text, kennzahlen_text="", gewicht_text="", as_of=None):
    """Baut die historischen Tageszeilen (Schema = rh.HEADER) aus den Drive-Quellen."""
    series = _daily_banister_series(trainings_text)
    kz = _daily_from_kennzahlen(kennzahlen_text)
    gw = _daily_from_gewicht(gewicht_text)
    end = _d(as_of) or (max(series) if series else None)
    rows = []
    for d in sorted(series):
        if end and d >= end:
            break  # Backfill nur abgeschlossene Tage (< as_of)
        ctl, atl, tsb = series[d]
        row = rh.build_row(
            d.isoformat(),
            banister={"ctl": ctl, "atl": atl, "tsb": tsb},
            daily={
                "hrv_night": {"avg": kz.get(d, {}).get("hrv_ms")},
                "recovery": {"rhr": kz.get(d, {}).get("rhr")},
                "body_comp": {
                    "weight_body_mass": {"value": gw.get(d, {}).get("weight")},
                    "body_fat_percentage": {"value": gw.get(d, {}).get("kfa")},
                },
            },
            signals={"vo2_max": {"value": kz.get(d, {}).get("vo2")}},
        )
        rows.append(row)
    return rows


def backfill_csv(existing_text, trainings_text, kennzahlen_text="", gewicht_text="", as_of=None):
    """Hängt alle Backfill-Zeilen idempotent an den bestehenden CSV-Text an."""
    text = existing_text if (existing_text or "").strip() else ",".join(rh.HEADER) + "\n"
    for row in backfill_rows(trainings_text, kennzahlen_text, gewicht_text, as_of):
        text = rh.append_row(text, row)
    return text


# --------------------------------------------------------------------------- #
# Drive glue (mirror readiness_history)
# --------------------------------------------------------------------------- #
def _pull_text(svc, pd, folder_id, name, out_dir):
    matches = pd._list_matches(svc, folder_id, name, None)
    exact = [f for f in matches if f["name"] == name]
    if not exact:
        return None, None
    fid = exact[0]["id"]
    local = Path(out_dir) / name
    pd._download_media(svc, fid, local)
    return fid, local.read_text(encoding="utf-8")


def run_snapshot(as_of, weeks, months, folder_id, out_dir, sa_file=None):
    import pull_drive as pd
    creds = pd._load_credentials(sa_file, pd.SCOPES_RW)
    svc = pd._drive(creds)
    _, hist = _pull_text(svc, pd, folder_id, rh.DEFAULT_CSV, out_dir)
    if hist is None:
        rh._eprint(rh._preseed_instruction(rh.DEFAULT_CSV, folder_id))
        raise SystemExit(2)
    md = build_from_csv_text(hist, as_of=as_of, weeks=weeks, months=months)
    local = Path(out_dir) / SNAPSHOT_NAME
    local.write_text(md, encoding="utf-8")
    sfid = pd._list_matches(svc, folder_id, SNAPSHOT_NAME, None)
    if not [f for f in sfid if f["name"] == SNAPSHOT_NAME]:
        rh._eprint(rh._preseed_instruction(SNAPSHOT_NAME, folder_id))
        raise SystemExit(2)
    return pd._upload(svc, str(local), folder_id, SNAPSHOT_NAME)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Woche+Monat-Trend-Rollup aus readiness-history.csv.")
    ap.add_argument("--as-of", dest="as_of", help="Stichtag YYYY-MM-DD (Snapshot-Label / Backfill-Ende).")
    ap.add_argument("--weeks", type=int, default=8)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--out", default="./data")
    ap.add_argument("--folder", default=DEFAULT_FOLDER_ID)
    ap.add_argument("--sa-file", dest="sa_file")
    ap.add_argument("--backfill", action="store_true", help="readiness-history.csv aus Drive-Historie seeden.")
    ap.add_argument("--trainings", help="Trainings_v5.csv (für --backfill).")
    ap.add_argument("--kennzahlen", help="Taegliche_Kennzahlen.csv (für --backfill, optional).")
    ap.add_argument("--gewicht", help="Gewicht.csv (für --backfill, optional).")
    args = ap.parse_args(argv)

    if args.backfill:
        if not args.trainings:
            print("--backfill braucht --trainings", file=sys.stderr)
            return 1
        tr = open(args.trainings, encoding="utf-8", errors="replace").read()
        kz = open(args.kennzahlen, encoding="utf-8", errors="replace").read() if args.kennzahlen else ""
        gw = open(args.gewicht, encoding="utf-8", errors="replace").read() if args.gewicht else ""
        # bestehende CSV ziehen, backfillen, hochladen (mirror run_history)
        import pull_drive as pd
        creds = pd._load_credentials(args.sa_file, pd.SCOPES_RW)
        svc = pd._drive(creds)
        fid, existing = _pull_text(svc, pd, args.folder, rh.DEFAULT_CSV, args.out)
        if fid is None:
            rh._eprint(rh._preseed_instruction(rh.DEFAULT_CSV, args.folder))
            return 2
        updated = backfill_csv(existing, tr, kz, gw, as_of=args.as_of)
        local = Path(args.out) / rh.DEFAULT_CSV
        local.write_text(updated, encoding="utf-8")
        print(pd._upload(svc, str(local), args.folder, rh.DEFAULT_CSV))
        return 0

    print(run_snapshot(args.as_of, args.weeks, args.months, args.folder, args.out, args.sa_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
