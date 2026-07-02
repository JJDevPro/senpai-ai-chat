"""analyze_run.py — CSV-Fallback-Engine (v3.14, PR-4).

Vorher war das ein Referenz-Stub mit ROHEN Mittelwerten inkl. Gehen (NEVER-
Regel-Bruch). Jetzt: gleicher Aggregat-Kontrakt wie die FIT-Engine über die
GETEILTEN Funktionen. Diese Tests pinnen den Kontrakt auf einer synthetischen
HealthFit-CSV (Semicolon, Komma-Dezimal) mit bekannten Werten.
"""

import json
import subprocess
import sys
from pathlib import Path

import analyze_run as ar

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / ".claude" / "skills" / "run-bundle-skill" / "scripts" / "analyze_run.py"

HEADER = ("Time;Timestamp;ISO8601;Heart Rate (bpm);Power (watt);Cadence (count/min);"
          "Latitude (°);Longitude (°);Elevation (meter);Horizontal accuracy (meter);"
          "Vertical accuracy (meter);Distance (meter);Speed (m/s);Stride length (mm);"
          "VO (mm);GCT (ms);Lap;Intensity;Since start (second)")


def _row(sec, hr, cad_single, spd, dist, lap="1", gct="250", stride="800", vo="80"):
    iso = f"2026-06-28T07:{sec // 60:02d}:{sec % 60:02d}+02:00"
    spd_s = str(spd).replace(".", ",")
    return (f";;{iso};{hr};200;{cad_single};;;300;;;{dist};{spd_s};{stride};{vo};{gct};"
            f"{lap};active;{sec}")


def _write_csv(tmp_path, rows):
    p = tmp_path / "run.csv"
    p.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def _mixed_run_rows():
    """60 s Laufen (85 single-foot = 170 spm, 3,0 m/s) + 20 s Gehen (55 = 110 spm,
    1,2 m/s) + 10 s Stillstand (0 spm, 0,1 m/s). Distanz kumulativ."""
    rows, dist = [], 0.0
    for i in range(60):
        dist += 3.0
        rows.append(_row(i, 140 + (i % 3), 85, 3.0, f"{dist:.0f}"))
    for i in range(60, 80):
        dist += 1.2
        rows.append(_row(i, 120, 55, 1.2, f"{dist:.0f}", lap="2", gct="", stride="", vo=""))
    for i in range(80, 90):
        rows.append(_row(i, 100, 0, 0.1, f"{dist:.0f}", lap="2", gct="", stride="", vo=""))
    return rows


def test_walking_filter_applies_to_csv(tmp_path):
    recs, _ = ar.read_csv_records(str(_write_csv(tmp_path, _mixed_run_rows())))
    assert len(recs) == 90
    assert sum(1 for r in recs if r["run"]) == 60
    assert sum(1 for r in recs if r["walk"]) == 20
    assert sum(1 for r in recs if r["stand"]) == 10
    assert recs[0]["spm"] == 170.0                      # single-foot × 2


def test_cadence_absence_speed_only_fallback(tmp_path):
    rows = [_row(0, 130, "", 1.0, "0"),                 # leere Kadenz-Zelle, langsam → walk
            _row(1, 150, "", 2.5, "3")]                 # leere Kadenz-Zelle, schnell → run
    recs, _ = ar.read_csv_records(str(_write_csv(tmp_path, rows)))
    assert recs[0]["spm"] is None and recs[0]["walk"] is True
    assert recs[1]["spm"] is None and recs[1]["run"] is True


def test_analyze_contract_matches_fit_engine(tmp_path):
    res = ar.analyze(str(_write_csv(tmp_path, _mixed_run_rows())), "2026-06-28")
    assert res["ok"] is True and res["schema_version"] == "3.14"
    # gleiche Top-Level-Keys wie die FIT-Engine (Kontrakt)
    for key in ("summary", "splits_km", "splits_lap", "hr_zones", "run_form",
                "best_values", "decoupling", "pace_at_z2", "v3_ampeln", "topography"):
        assert key in res, f"Kontrakt-Key {key} fehlt"
    # running-only-Kadenz = 170, NICHT der geh-gemischte Schnitt
    assert res["run_form"]["cadence_spm"] == 170.0
    # walk_pct aus dem Filter (20/90)
    assert abs(res["summary"]["walk_pct"] - 22.2) < 0.2
    # Lap-Splits aus der Lap-Spalte
    assert len(res["splits_lap"]) == 2
    assert res["splits_lap"][0]["cadence"] == 170
    # Ampeln engine-seitig vorhanden
    assert res["v3_ampeln"]["cadence"]["ampel"] in ("🟢", "🟡", "🟠", "🔴")


def test_cli_emits_compact_json(tmp_path):
    p = _write_csv(tmp_path, _mixed_run_rows())
    out = subprocess.run([sys.executable, str(SCRIPT), str(p), "--as-of", "2026-06-28"],
                         capture_output=True, text=True, check=True)
    res = json.loads(out.stdout)
    assert res["ok"] is True
    assert res["meta"]["record_count"] == 90
    # §0-Kernregel: kein Roh-Sample-Array im Output
    assert "records" not in res


def test_empty_csv_fails_loudly(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text(HEADER + "\n", encoding="utf-8")
    out = subprocess.run([sys.executable, str(SCRIPT), str(p), "--as-of", "2026-06-28"],
                         capture_output=True, text=True)
    assert out.returncode != 0
    assert json.loads(out.stdout)["ok"] is False
