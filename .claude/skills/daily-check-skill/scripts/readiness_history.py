#!/usr/bin/env python3
"""
readiness_history.py — hängt EINE Tages-Trend-Zeile an readiness-history.csv (Drive-State).

WARUM dieses Skript existiert:
  Der Daily Check (SKILL.md) produziert jeden Morgen ein verdichtetes Urteil
  (readiness.py-Score + body_battery.py-Akku + safety/banister-Kontext). Diese
  Einzel-Zahlen sind nur im jeweiligen Chat sichtbar — ein KW-/Monats-Trend
  (Readiness steigt? Body-Battery sinkt? top_limiter immer derselbe?) geht verloren.
  Dieses Skript persistiert pro Tag GENAU EINE kompakte Zeile in eine rollende CSV
  im privaten `Senpai-AI-Chat`-Drive-Ordner — der Daily Check kann sie später als
  Trend zurücklesen. Wie `lib/archive.py` (rollendes Journal) hält es EINE Datei und
  *appended* deterministisch, statt Dateien zu streuen.

⛔ KERNREGEL (CLAUDE.md §0): Es wird NUR ein Aggregat geschrieben — eine 1-Zeile/Tag-
  CSV-Zeile aus den schon-reduzierten Upstream-Outputs (readiness/body_battery/
  banister/hrv_baseline). NIE rohe Per-Sekunde-/Per-Minute-Serien. Die reine
  append_row-Logik bekommt nur Strings/Dicts und fasst Drive nie an (testbar lokal).

⛔ PERSONAL-DATA-FREI (CLAUDE.md Kopf): Keine Körper-/Health-Schwelle ist hartkodiert.
  Die Zeile enthält nur abgeleitete Score-/Band-/Status-Aggregate, die die Upstream-
  Skripte (mit ihren §5/§6-Schwellen) bereits berechnet haben.

HARTE DRIVE-REGEL (1:1 zu lib/archive.py): Der Service-Account hat KEINE My-Drive-
  Quota — er kann eine Datei nur UPDATEN, nicht ANLEGEN. readiness-history.csv MUSS
  also vom User EINMAL vor-seeded werden (Drive-Seed-Template mit der Header-Zeile).
  Fehlt sie, druckt dieses Skript eine klare Vor-Seed-Anweisung und beendet mit
  non-zero — es legt sie NIE selbst an.

Flow (gespiegelt von lib/archive.py):
  1. aktuelle CSV aus dem Ordner ziehen (lib/pull_drive.py read path)
  2. die Tages-Zeile anhängen (rein, idempotent auf Datum: append_row)
  3. zurück-uploaden (lib/pull_drive.py --upload → Drive files.update auf die
     bereits existierende Datei)

CSV-SCHEMA (matcht den Drive-Seed-Header EXAKT; v2 = +8 Trend-/Inkrement-Spalten):
  date,readiness_score,band,hrv_status,bb_start,bb_end,tsb,top_limiter,
  ctl,atl,hrv_ms,rhr,weight,kfa,vo2,week_km

CLI:
  python3 readiness_history.py --as-of YYYY-MM-DD \
      [--readiness <file|->] [--body-battery <file>] [--banister <file>] \
      [--hrv-baseline <file>] [--csv readiness-history.csv] [--folder <ID>] [--out ./data]

Die append/format-Logik (`append_row`, `build_row`) nimmt nur native Strukturen und
fasst Drive nie an — die Tests prüfen sie gegen In-Memory-Strings (siehe
tests/test_readiness_history.py).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

# readiness_history.py liegt im daily-check scripts/-Ordner; beim Standalone-Lauf ist
# dieser Ordner sys.path[0]. lib/ (für pull_drive) wird wie in archive.py addiert.
_THIS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _THIS_DIR.parents[3] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

# Privater State-Ordner (Senpai-AI-Chat). Überschreibbar via --folder.
DEFAULT_FOLDER_ID = "1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde"
DEFAULT_CSV = "readiness-history.csv"

# Spalten-Reihenfolge = Drive-Seed-Header (EXAKT, nicht umsortieren).
# v2: ctl/atl (für inkrementelles Banister) + hrv_ms/rhr/weight/kfa/vo2/week_km
# (Trend-Snapshot-Quelle). Neue Spalten ANGEHÄNGT → alte Zeilen bleiben gültig
# (csv.DictReader füllt fehlende Felder mit None → leere Zelle).
HEADER = ["date", "readiness_score", "band", "hrv_status",
          "bb_start", "bb_end", "tsb", "top_limiter",
          "ctl", "atl", "hrv_ms", "rhr", "weight", "kfa", "vo2", "week_km"]


def _eprint(*a):
    print(*a, file=sys.stderr)


# --------------------------------------------------------------------------- #
# Reine Row-/CSV-Logik (kein Drive, voll unit-testbar)
# --------------------------------------------------------------------------- #
def _valid_iso(s):
    """YYYY-MM-DD strikt validieren (deterministisch, keine Wall-Clock)."""
    if not isinstance(s, str) or len(s) != 10 or s[4] != "-" or s[7] != "-":
        return False
    y, m, d = s[:4], s[5:7], s[8:10]
    if not (y.isdigit() and m.isdigit() and d.isdigit()):
        return False
    return 1 <= int(m) <= 12 and 1 <= int(d) <= 31


def _cell(value):
    """Skalar → CSV-Zellenstring; None → "" (leere Zelle, kein 'None'-Literal)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _dig(obj, *path):
    """Sicher durch verschachtelte dicts greifen; None bei jedem Fehltritt."""
    cur = obj
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _num(v):
    """Entpackt ein `{'value': x, ...}`-Aggregat auf den Skalar; Skalare unverändert.

    Manche slice-Felder (z. B. recovery.rhr) liefern ein `{value,date}`-Dict statt
    eines nackten Werts. Ohne dieses Unwrapping landete der ganze Dict-String in der
    CSV-Zelle (`"{'value': 61.0, ...}"`) und der Trend-Snapshot las ihn als leer.
    """
    if isinstance(v, dict):
        return v.get("value")
    return v


def build_row(as_of, readiness=None, body_battery=None, banister=None, hrv_baseline=None,
              daily=None, signals=None, tolerance=None):
    """Reduzierte Upstream-Outputs → eine Trend-Zeile als dict (Schema = HEADER).

    Liest NUR kompakte Aggregat-Keys der Sibling-Skripte:
      readiness.py     → score, band, top_limiter
      body_battery.py  → bb_start, bb_end
      banister.py      → tsb, ctl, atl          (ctl/atl: inkrementeller Pfad-Anker)
      hrv_baseline.py  → status
      daily (slice)    → hrv_night.avg, recovery.rhr, body_comp.{weight,kfa}
      signals          → vo2_max.value
      tolerance        → week_km
    Fehlt eine Quelle, bleibt die Zelle leer (kein Crash, kein erfundener Wert).
    Wirft ValueError bei kaputtem --as-of (CLI fängt → JSON-Error + non-zero Exit).
    """
    if not _valid_iso(as_of):
        raise ValueError(f"Ungültiges as_of {as_of!r} (erwartet YYYY-MM-DD).")
    r = readiness or {}
    bb = body_battery or {}
    ba = banister or {}
    hrv = hrv_baseline or {}
    return {
        "date": as_of,
        "readiness_score": r.get("score"),
        "band": r.get("band"),
        "hrv_status": hrv.get("status"),
        "bb_start": bb.get("bb_start"),
        "bb_end": bb.get("bb_end"),
        "tsb": ba.get("tsb"),
        "top_limiter": r.get("top_limiter"),
        "ctl": ba.get("ctl"),
        "atl": ba.get("atl"),
        "hrv_ms": _num(_dig(daily, "hrv_night", "avg")),
        "rhr": _num(_dig(daily, "recovery", "rhr")),
        "weight": _num(_dig(daily, "body_comp", "weight_body_mass", "value")),
        "kfa": _num(_dig(daily, "body_comp", "body_fat_percentage", "value")),
        "vo2": _num(_dig(signals, "vo2_max", "value")),
        "week_km": (tolerance or {}).get("week_km"),
    }


def _read_rows(csv_text):
    """CSV-Text → (header_list, [row_dict]). Leerer/whitespace-Text → (None, [])."""
    if not (csv_text or "").strip():
        return None, []
    reader = csv.DictReader(io.StringIO(csv_text))
    header = list(reader.fieldnames or [])
    rows = [dict(r) for r in reader]
    return header, rows


def append_row(csv_text, row_dict):
    """Hängt EINE Zeile an den CSV-Text an, gibt den neuen Text zurück (rein).

    Header-aware: nutzt den bestehenden Header (Reihenfolge bleibt), bei leerer/
    nur-Header-Datei wird HEADER geschrieben. IDEMPOTENT auf `date`: existiert die
    Datums-Zeile bereits, wird der Text UNVERÄNDERT zurückgegeben (kein Duplikat,
    keine stille Überschreibung — derselbe Tag ist ein No-op).
    """
    if not isinstance(row_dict, dict) or not row_dict.get("date"):
        raise ValueError("row_dict braucht mindestens ein nicht-leeres 'date'.")

    header, rows = _read_rows(csv_text)
    if not header:
        header = list(HEADER)

    date_key = header[0] if header else "date"
    new_date = row_dict.get("date")
    if any((r.get(date_key) or "").strip() == new_date for r in rows):
        return csv_text  # Datum schon vorhanden → unverändert (idempotent)

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    for r in rows:
        writer.writerow([_cell(r.get(c)) for c in header])
    writer.writerow([_cell(row_dict.get(c)) for c in header])
    return out.getvalue()


# --------------------------------------------------------------------------- #
# Reader (der Trend-Reader, den der Docstring immer versprach — jetzt aktiviert)
# --------------------------------------------------------------------------- #
def read_history(csv_text):
    """CSV-Text → [row_dict] in Datei-Reihenfolge (= chronologisch, append-only). Leer → []."""
    _, rows = _read_rows(csv_text)
    return rows


def last_row(csv_text):
    """Jüngste Zeile als dict (oder None). Speist den inkrementellen Banister-Pfad
    (gestriger ctl/atl/date) + den Frische-Check (Lücke → Fallback auf Vollrechnung)."""
    rows = read_history(csv_text)
    return rows[-1] if rows else None


def tail(csv_text, n):
    """Letzte n Zeilen (Trend-Reader / Rollup-Quelle). n<=0 → alle."""
    rows = read_history(csv_text)
    return rows[-n:] if (n and n > 0) else rows


# --------------------------------------------------------------------------- #
# Drive glue (spiegelt lib/archive.py — reuse von lib/pull_drive.py)
# --------------------------------------------------------------------------- #
def _preseed_instruction(csv_name, folder_id):
    return (
        f"ERROR: readiness-history CSV {csv_name!r} not found in Drive folder {folder_id}.\n"
        f"The service-account has no My-Drive quota and CANNOT create it.\n"
        f"PRE-SEED it ONCE yourself: drop the drive-seed template named {csv_name!r}\n"
        f"(a single header line: {','.join(HEADER)}) into the 'Senpai-AI-Chat' folder\n"
        f"(drag-drop in Drive). After that, readiness_history.py keeps appending to it."
    )


def run_history(row_dict, csv_name, folder_id, out_dir, sa_file=None):
    """CSV ziehen → Zeile anhängen → zurück-uploaden. Gibt die Drive-File-ID zurück.

    Wirft SystemExit(non-zero) mit einer Vor-Seed-Anweisung, falls die CSV fehlt
    (wir legen sie NIE an — gespiegelt von lib/archive.run_archive).
    """
    import pull_drive as pd

    creds = pd._load_credentials(sa_file, pd.SCOPES_RW)
    svc = pd._drive(creds)

    matches = pd._list_matches(svc, folder_id, csv_name, None)
    exact = [f for f in matches if f["name"] == csv_name]
    if not exact:
        _eprint(_preseed_instruction(csv_name, folder_id))
        raise SystemExit(2)

    fid = exact[0]["id"]
    out = Path(out_dir)
    local = out / csv_name
    pd._download_media(svc, fid, local)

    current = local.read_text(encoding="utf-8")
    updated = append_row(current, row_dict)
    local.write_text(updated, encoding="utf-8")

    # Upload zurück: Datei existiert → pull_drive._upload macht Drive files.update.
    return pd._upload(svc, str(local), folder_id, csv_name)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_json_arg(value, label):
    """CLI-Arg: Pfad ODER '-' (stdin) → geparstes JSON (None bei leerem Arg/Inhalt)."""
    if value is None:
        return None
    raw = sys.stdin.read() if value == "-" else open(value, encoding="utf-8").read()
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except ValueError as e:
        raise ValueError(f"{label}: kein gültiges JSON ({e}).")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Hängt EINE Tages-Trend-Zeile an readiness-history.csv (Drive-State). "
                    "Konsumiert NUR reduzierte Upstream-Outputs, schreibt 1 Aggregat-Zeile/Tag (§0).")
    ap.add_argument("--as-of", required=True, dest="as_of",
                    help="Stichtag YYYY-MM-DD (deterministisch, keine Wall-Clock).")
    ap.add_argument("--readiness", help="readiness.py-Output (Datei oder '-' für stdin).")
    ap.add_argument("--body-battery", dest="body_battery",
                    help="body_battery.py-Output (Datei oder '-' für stdin).")
    ap.add_argument("--banister", help="banister.py-Output (Datei oder '-' für stdin).")
    ap.add_argument("--hrv-baseline", dest="hrv_baseline",
                    help="hrv_baseline.py-Output (Datei oder '-' für stdin).")
    ap.add_argument("--daily", help="slice_hae_day-Output (hrv_night/recovery/body_comp; Datei oder '-').")
    ap.add_argument("--signals", help="daily_signals.py-Output (vo2_max; Datei oder '-').")
    ap.add_argument("--tolerance", help="running_tolerance.py-Output (week_km; Datei oder '-').")
    ap.add_argument("--csv", default=DEFAULT_CSV, help=f"CSV-Dateiname (Default: {DEFAULT_CSV}).")
    ap.add_argument("--folder", default=DEFAULT_FOLDER_ID, help="Drive-Ordner-ID (Default: Senpai-AI-Chat).")
    ap.add_argument("--out", default="./data", help="lokaler Scratch-Ordner für die gezogene CSV.")
    ap.add_argument("--sa-file", dest="sa_file", help="Pfad zur Service-Account-JSON (sonst env).")
    args = ap.parse_args(argv)

    # Höchstens EIN '-'-Input (stdin lässt sich nur einmal lesen).
    stdin_args = [v for v in (args.readiness, args.body_battery, args.banister,
                              args.hrv_baseline, args.daily, args.signals, args.tolerance)
                  if v == "-"]
    try:
        if len(stdin_args) > 1:
            raise ValueError("Nur EIN Input darf '-' (stdin) sein.")
        row = build_row(
            args.as_of,
            readiness=_load_json_arg(args.readiness, "--readiness"),
            body_battery=_load_json_arg(args.body_battery, "--body-battery"),
            banister=_load_json_arg(args.banister, "--banister"),
            hrv_baseline=_load_json_arg(args.hrv_baseline, "--hrv-baseline"),
            daily=_load_json_arg(args.daily, "--daily"),
            signals=_load_json_arg(args.signals, "--signals"),
            tolerance=_load_json_arg(args.tolerance, "--tolerance"),
        )
    except (ValueError, OSError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, separators=(",", ":")))
        return 1

    fid = run_history(
        row_dict=row,
        csv_name=args.csv,
        folder_id=args.folder,
        out_dir=args.out,
        sa_file=args.sa_file,
    )
    print(fid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
