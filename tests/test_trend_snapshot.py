"""Tests für trend_snapshot.py — Woche+Monat-Rollup aus readiness-history.csv.

ZWECK: sichern, dass der Snapshot (a) die Tageszeilen korrekt zu Wochen/Monaten
aggregiert (SoT = letzter Wert, HRV/RHR = Ø), (b) zwei saubere Markdown-Tabellen
mit dem CTL(Fitness)/ATL(Fatigue)/TSB(Form)-Gloss rendert, und (c) der Backfill
dieselbe EWMA-Reihe wie banister produziert (Snapshot ≠ Ersatz, aber genau).

DRIVE-FREI: nur die puren rollup/render/backfill-Funktionen, kein Google-Drive.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / ".claude" / "skills" / "daily-check-skill" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import readiness_history as rh  # noqa: E402
import trend_snapshot as ts  # noqa: E402
import banister as b  # noqa: E402


def _csv(rows):
    """rows = Liste von dicts (HEADER-Subset) → CSV-Text mit kanonischem Header."""
    text = ",".join(rh.HEADER) + "\n"
    for r in rows:
        text = rh.append_row(text, {k: r.get(k) for k in rh.HEADER})
    return text


SAMPLE = [
    {"date": "2026-05-04", "weight": 116.2, "kfa": 28.1, "hrv_ms": 52, "rhr": 55,
     "vo2": 35.5, "ctl": 40.1, "atl": 38.0, "tsb": 2.0, "week_km": 30},
    {"date": "2026-05-07", "weight": 115.8, "kfa": 27.9, "hrv_ms": 56, "rhr": 53,
     "vo2": 35.6, "ctl": 41.0, "atl": 39.5, "tsb": 1.5, "week_km": 30},
    {"date": "2026-06-22", "weight": 115.1, "kfa": 27.2, "hrv_ms": 54, "rhr": 53,
     "vo2": 36.2, "ctl": 45.0, "atl": 42.0, "tsb": 3.0, "week_km": 38},
    {"date": "2026-06-25", "weight": 116.0, "kfa": 27.0, "hrv_ms": 54, "rhr": 53,
     "vo2": 36.2, "ctl": 45.5, "atl": 43.0, "tsb": 2.5, "week_km": 38},
]


# --------------------------------------------------------------------------- #
# Rollup
# --------------------------------------------------------------------------- #
def test_weekly_buckets_by_iso_week():
    rows = rh.read_history(_csv(SAMPLE))
    weekly = ts.rollup_weekly(rows, n_weeks=8)
    labels = [w["label"] for w in weekly]
    # KW19 (04.+07.05), KW26 (22.+25.06)
    assert labels == ["2026-KW19", "2026-KW26"], labels


def test_agg_last_for_sot_avg_for_hrv():
    rows = rh.read_history(_csv(SAMPLE))
    kw19 = ts.rollup_weekly(rows, n_weeks=8)[0]
    # Gewicht/CTL/KFA = LETZTER Wert im Bucket (SoT/Form am Ende)
    assert kw19["weight"] == 115.8
    assert kw19["ctl"] == 41.0
    assert kw19["kfa"] == 27.9
    # HRV/RHR = Ø über den Bucket
    assert kw19["hrv_ms"] == 54.0       # (52+56)/2
    assert kw19["rhr"] == 54.0          # (55+53)/2
    assert kw19["n_days"] == 2


def test_monthly_buckets():
    rows = rh.read_history(_csv(SAMPLE))
    monthly = ts.rollup_monthly(rows, n_months=12)
    labels = [m["label"] for m in monthly]
    assert labels == ["2026-05", "2026-06"], labels
    assert monthly[-1]["weight"] == 116.0   # letzter Juni-Wert


def test_window_rolls_to_n():
    # 10 verschiedene Wochen → nur die letzten 8 bleiben
    from datetime import date, timedelta
    rows = []
    d = date(2026, 1, 5)   # Montag KW02
    for i in range(10):
        rows.append({"date": (d + timedelta(days=i * 7)).isoformat(), "ctl": float(i)})
    weekly = ts.rollup_weekly(rh.read_history(_csv(rows)), n_weeks=8)
    assert len(weekly) == 8


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def test_render_has_both_tables_and_gloss():
    md = ts.build_from_csv_text(_csv(SAMPLE), as_of="2026-06-29")
    assert "### 📅 Letzte Wochen" in md
    assert "### 🗓️ Letzte Monate" in md
    assert "CTL (Fitness)" in md and "ATL (Fatigue)" in md and "TSB (Form)" in md
    assert "Stand 2026-06-29" in md
    # echte Markdown-Tabelle (keine Code-Fence)
    assert "| 2026-KW26 |" in md


def test_render_empty_cells_as_dash():
    md = ts.build_from_csv_text(_csv([{"date": "2026-06-25", "ctl": 45.5}]), as_of="2026-06-29")
    # fehlendes Gewicht/HRV → "—", kein Crash, kein erfundener Wert
    assert "—" in md


def test_render_includes_prs_when_given():
    md = ts.build_from_csv_text(_csv(SAMPLE), as_of="2026-06-29", prs="- 5k PR: 28:30")
    assert "🏆 PRs / Meilensteine" in md and "5k PR: 28:30" in md


# --------------------------------------------------------------------------- #
# Backfill-Parser (DD.MM.YYYY + Withings-Fett-Bruch)
# --------------------------------------------------------------------------- #
def test_gewicht_parser_handles_german_date_and_fraction():
    text = (" Datum , Gewicht , Quelle , Fett , Quelle \n"
            "25.06.2026,115.34,Withings,0.272,Withings\n")
    out = ts._daily_from_gewicht(text)
    from datetime import date
    assert date(2026, 6, 25) in out
    row = out[date(2026, 6, 25)]
    assert row["weight"] == 115.3
    assert row["kfa"] == 27.2          # 0.272 → 27.2 %


def test_kennzahlen_parser_hrv_rhr_vo2():
    text = (" Datum , Ruheenergie , Ruheherzfrequenz , HFV , VO₂ max \n"
            "27.06.2026,2730,64,52.35,38.5\n")
    out = ts._daily_from_kennzahlen(text)
    from datetime import date
    row = out[date(2026, 6, 27)]
    assert row["rhr"] == 64
    assert row["hrv_ms"] == 52.4       # gerundet
    assert row["vo2"] == 38.5
    # Ruheenergie darf NICHT als RHR durchrutschen
    assert row["rhr"] != 2730


# --------------------------------------------------------------------------- #
# Backfill-CTL ≙ banister-Vollrechnung (Snapshot ≠ Ersatz, aber genau)
# PR-7: läuft auf dem SYNTHETISCHEN Fixture statt echter data/-CSV — kein Skip,
# keine echten Gesundheitsdaten im Test-Pfad.
# --------------------------------------------------------------------------- #
def test_backfill_series_matches_banister_full_recompute(trainings_csv_text):
    """Eine zurückgerechnete Tageszeile muss CTL/ATL/TSB einer frischen
    compute_from_sheet-Vollrechnung desselben Stichtags treffen (±0,15)."""
    as_of = "2026-06-25"
    series = ts._daily_banister_series(trainings_csv_text)
    from datetime import date
    # banister-Vollrechnung: TSB = Form am Morgen von as_of = Reihe bis (as_of-1)
    full = b.compute_from_sheet(trainings_csv_text, as_of=as_of)
    prev = series[date(2026, 6, 24)]   # letzter Tag der Reihe vor as_of
    assert abs(prev[0] - full["ctl"]) <= 0.15
    assert abs(prev[1] - full["atl"]) <= 0.15
    assert abs(prev[2] - full["tsb"]) <= 0.15


def test_backfill_csv_appends_rows_with_canonical_header(trainings_csv_text):
    out = ts.backfill_csv("", trainings_csv_text, "", "", as_of="2026-06-29")
    lines = out.splitlines()
    assert lines[0] == ",".join(rh.HEADER)
    # Fixture-Sessions 20.–24.06 → 5 Tageszeilen (Zerofill wirkt in der
    # CTL/ATL-Reihe, geschrieben werden nur Tage mit Daten)
    assert len(lines) == 1 + 5
    # Chronologie-Invariante (PR-3-Sort-Fix) + Spaltenzahl jeder Zeile
    dates = [ln.split(",")[0] for ln in lines[1:]]
    assert dates == sorted(dates)
    assert all(len(ln.split(",")) == len(rh.HEADER) for ln in lines if ln.strip())


# --------------------------------------------------------------------------- #
# Local-Mode (--local --history --out-file): KEIN Drive, kein pull_drive-Import
# --------------------------------------------------------------------------- #
def _write_history(tmp_path):
    """Synthetische readiness-history.csv nach tmp_path schreiben (data-free)."""
    hist = tmp_path / "readiness-history.csv"
    hist.write_text(_csv(SAMPLE), encoding="utf-8")
    return hist


def test_local_mode_writes_snapshot_and_prints_summary(tmp_path, capsys):
    hist = _write_history(tmp_path)
    out = tmp_path / "trend_snapshot.md"
    rc = ts.main(["--local", "--history", str(hist), "--out-file", str(out),
                  "--as-of", "2026-06-29"])
    assert rc == 0
    md = out.read_text(encoding="utf-8")
    # identische Logik wie Drive-Modus: byte-gleich zu build_from_csv_text
    assert md == ts.build_from_csv_text(_csv(SAMPLE), as_of="2026-06-29")
    assert "### 📅 Letzte Wochen" in md and "### 🗓️ Letzte Monate" in md
    # KW19 = abgeschlossen (kein Marker), Juni = LAUFENDER Monat bei as_of → ⏳-Marker
    assert "| 2026-KW19 |" in md and "| 2026-06 ⏳2d (laufend) |" in md
    assert "Stand 2026-06-29" in md
    # CLI druckt Pfad + kompakte Zusammenfassung
    printed = capsys.readouterr().out
    assert str(out) in printed
    assert "4 Tageszeilen" in printed and "2 Wochen-Buckets" in printed


def test_local_mode_never_imports_pull_drive(tmp_path, monkeypatch):
    """Forbidden-Token-Simulation: Umgebung OHNE google-Libs — jeder
    pull_drive-Import würde ImportError werfen. Local-Mode muss trotzdem laufen."""
    monkeypatch.delitem(sys.modules, "pull_drive", raising=False)
    monkeypatch.setitem(sys.modules, "pull_drive", None)  # import → ImportError
    hist = _write_history(tmp_path)
    out = tmp_path / "sub" / "trend_snapshot.md"   # Parent-Ordner wird angelegt
    rc = ts.main(["--local", "--history", str(hist), "--out-file", str(out),
                  "--as-of", "2026-06-29"])
    assert rc == 0
    assert out.is_file()


def test_local_mode_missing_history_exits_2(tmp_path):
    with pytest.raises(SystemExit) as exc:
        ts.main(["--local", "--history", str(tmp_path / "gibts-nicht.csv"),
                 "--out-file", str(tmp_path / "snap.md")])
    assert exc.value.code == 2
    assert not (tmp_path / "snap.md").exists()


def test_local_mode_requires_history_and_out_file(tmp_path):
    hist = _write_history(tmp_path)
    assert ts.main(["--local"]) == 1
    assert ts.main(["--local", "--history", str(hist)]) == 1
    assert ts.main(["--local", "--out-file", str(tmp_path / "snap.md")]) == 1
