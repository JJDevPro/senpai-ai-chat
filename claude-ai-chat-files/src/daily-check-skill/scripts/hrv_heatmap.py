#!/usr/bin/env python3
"""hrv_heatmap.py — Multi-Tag-HRV-Heatmap (Stunde × Wochentag), rollende 7 Nächte.

Liest die bereits in ./data gecachten HAE-Tagesdateien (HealthAutoExport-YYYY-MM-DD.json),
merged sie EINMAL und zieht je Nacht (sleepEnd==Tag) die stündliche HRV über die
slice_hae_day-Logik (`_hrv_night`). **PROGRESSIV:** nutzt nur vorhandene Files, zieht
NICHTS nach — fehlende Nächte erscheinen als „—" und im „N/7 Nächte"-Label. (Den Voll-
Backfill macht der Skill via `pull_drive.py`, nicht dieses Script.)

Default = Markdown-Tabelle (Ampel-Emoji je Zelle); `--chart out.png` = PNG (Ampel-Hex,
deutsche Achsen/Titel). Die Nacht wird dem **Aufwach-Tag** (sleepEnd-Datum) zugeordnet —
identisch zur WHOOP-/Daily-Check-Logik (`sleepEnd==as_of`).

§0: gibt NIE Roh-Minuten-Arrays aus — nur die gebucketete Stunden-Matrix.

CLI:  python3 hrv_heatmap.py --as-of YYYY-MM-DD [--data-dir ./data] [--days 7] [--chart out.png]
"""
import argparse
import os
import sys
from datetime import date, timedelta

# slice_hae_day liegt im selben scripts/-Ordner → Slicer-Logik wiederverwenden (kein Dup).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slice_hae_day as S  # noqa: E402

WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _night_order(h):
    """Sortier-Key: Abendstunden (12–23) vor Morgenstunden (0–11), damit die Y-Achse
    Bettzeit → Aufwachen liest (…22, 23, 00, 01 …)."""
    return h if h >= 12 else h + 24


def _pick_night(merged, ds):
    """Schlaf-Record der Nacht, die AM Tag `ds` endet (sleepEnd==ds) — KEIN Fallback
    (sonst würde dieselbe Nacht über mehrere Spalten dupliziert)."""
    for r in S._series(merged, "sleep_analysis"):
        if S._day(r.get("sleepEnd")) == ds:
            return r
    return None


def build(as_of, data_dir, days=7):
    """Baut die Heatmap-Matrix aus den gecachten Files im Fenster [as_of−(days−1) … as_of]."""
    end = date.fromisoformat(as_of)
    window = [end - timedelta(days=i) for i in range(days - 1, -1, -1)]  # alt → neu
    # Auch den Tag VOR dem ältesten Fenster-Tag laden: die Vor-Mitternacht-HRV einer Nacht
    # steht in der Datei des Vortags.
    load_dates = [window[0] - timedelta(days=1)] + window
    maps, present = [], set()
    for d in load_dates:
        p = os.path.join(data_dir, f"HealthAutoExport-{d.isoformat()}.json")
        if os.path.exists(p):
            maps.append(S._load_metrics(p))
            present.add(d.isoformat())
    if not maps:
        return None
    merged = S._merge(*maps)

    columns = []  # (date_str, weekday_label, cells|None)  cells: {hour:int -> (hrv, ampel)}
    for d in window:
        ds = d.isoformat()
        if ds not in present:                       # Datei dieses Tags nicht gecached
            columns.append((ds, WD[d.weekday()], None))
            continue
        rec = _pick_night(merged, ds)
        night = S._hrv_night(merged, rec) if rec else None
        if not night or not night.get("hourly"):
            columns.append((ds, WD[d.weekday()], None))
            continue
        cells = {int(h["t"][:2]): (h["hrv"], h["ampel"]) for h in night["hourly"]}
        columns.append((ds, WD[d.weekday()], cells))

    return {
        "as_of": as_of,
        "days": days,
        "columns": columns,
        "found": sum(1 for _, _, c in columns if c),
    }


def _hours_axis(columns):
    hours = set()
    for _, _, c in columns:
        if c:
            hours |= set(c.keys())
    return sorted(hours, key=_night_order)


def render_md(res):
    cols = res["columns"]
    hours = _hours_axis(cols)
    title = (f"💓 **HRV-Heatmap — rollende {res['days']} Nächte (Stunde × Tag)** · "
             f"{res['found']}/{res['days']} Nächte gecached")
    if not hours:
        return (title + "\n\n_Keine gecachten Nächte mit HRV._ "
                "→ »HRV-Heatmap voll« zieht die fehlenden Tage nach.")
    head = "| 🕒 |" + "".join(f" {wd} {ds[8:10]}. |" for ds, wd, _ in cols)
    sep = "|---|" + "---|" * len(cols)
    lines = [title, "", head, sep]
    for h in hours:
        row = [f"| {h:02d}:00 |"]
        for _, _, c in cols:
            if c and h in c:
                hrv, amp = c[h]
                row.append(f" {amp}{hrv} |")
            else:
                row.append(" — |")
        lines.append("".join(row))
    if res["found"] < res["days"]:
        missing = res["days"] - res["found"]
        lines += ["", f"> ⚠️ {missing} Nacht/Nächte nicht gecached → »HRV-Heatmap voll« für Backfill."]
    return "\n".join(lines)


def render_png(res, out):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import BoundaryNorm, ListedColormap
        import numpy as np
    except ImportError:
        return None   # matplotlib/numpy nicht verfügbar → Aufrufer fällt auf Markdown zurück

    cols = res["columns"]
    hours = _hours_axis(cols)
    if not hours:
        return False
    cat = np.zeros((len(hours), len(cols)))
    txt = [["" for _ in cols] for _ in hours]
    for j, (ds, wd, c) in enumerate(cols):
        for i, h in enumerate(hours):
            if c and h in c:
                hrv, _ = c[h]
                cat[i, j] = 3 if hrv >= 60 else (2 if hrv >= 50 else 1)
                txt[i][j] = str(hrv)
            else:
                cat[i, j] = 0   # missing → grau
    # Ampel-Schema (CLAUDE.md §10): grau=keine Daten · rot<50 · gelb 50–59 · grün≥60
    cmap = ListedColormap(["#95a5a6", "#e74c3c", "#f1c40f", "#2ecc71"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)
    fig, ax = plt.subplots(figsize=(max(6, len(cols) * 1.1), max(4, len(hours) * 0.5)))
    ax.imshow(cat, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([f"{wd}\n{ds[8:10]}.{ds[5:7]}." for ds, wd, _ in cols])
    ax.set_yticks(range(len(hours)))
    ax.set_yticklabels([f"{h:02d}:00" for h in hours])
    ax.set_xlabel("Wochentag (Nacht, Aufwach-Tag)")
    ax.set_ylabel("Stunde")
    ax.set_title(f"HRV-Heatmap — rollende {res['days']} Nächte ({res['found']}/{res['days']} gecached)")
    for i in range(len(hours)):
        for j in range(len(cols)):
            if txt[i][j]:
                ax.text(j, i, txt[i][j], ha="center", va="center", fontsize=8, color="#2c3e50")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return True


def main():
    ap = argparse.ArgumentParser(description="Multi-Tag-HRV-Heatmap (Stunde × Tag), rollende N Nächte.")
    ap.add_argument("--as-of", required=True, help="Bezugstag YYYY-MM-DD (jüngste Nacht).")
    ap.add_argument("--data-dir", default="./data", help="Ordner mit den HAE-Tagesdateien (default ./data).")
    ap.add_argument("--days", type=int, default=7, help="Fenstergröße in Nächten (default 7).")
    ap.add_argument("--chart", default=None, help="PNG-Ausgabepfad; ohne = Markdown auf stdout.")
    args = ap.parse_args()

    try:
        date.fromisoformat(args.as_of)
    except ValueError:
        print(f"--as-of muss YYYY-MM-DD sein, war: {args.as_of!r}", file=sys.stderr)
        return 2

    res = build(args.as_of, args.data_dir, args.days)
    if res is None:
        print(f"💓 HRV-Heatmap: keine gecachten HAE-Tagesdateien in {args.data_dir} (0/{args.days}).")
        return 0
    if args.chart:
        ok = render_png(res, args.chart)
        if ok is None:
            print("⚠️ matplotlib/numpy nicht installiert → Markdown-Fallback (Default ohne --chart):\n")
            print(render_md(res))
        elif ok:
            print(f"PNG geschrieben: {args.chart} ({res['found']}/{res['days']} Nächte)")
        else:
            print("Keine HRV-Daten für Chart.")
    else:
        print(render_md(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
