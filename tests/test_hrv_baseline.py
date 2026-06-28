"""Regression tests for hrv_baseline.py (Garmin-style rolling HRV-Status).

hrv_baseline turns CLAUDE.md §5's HRV traffic-light into a HARD, testable status
relative to a rolling 60-day robust (median/MAD) baseline. Inputs are tiny synthetic
already-reduced aggregates (one HRV value per day) — no real data, no raw series,
mirroring the sentinel / safety_gate tests.

Locks:
  * "low" reuses safety_gate.HRV_RED as LOW_FLOOR (no new hardcoded number).
  * latest within band + >= floor -> "balanced".
  * latest clearly outside band + >= floor -> "unbalanced".
  * n < MIN_DAYS -> "insufficient_data" (still emits median/band/n).
  * --as-of cuts the trailing window deterministically; future days are ignored.
  * bad input -> non-zero exit + JSON error object.
  * CSV reader e2e: German 'Tägliche Kennzahlen' headers (HFV/Ruheherzfrequenz)
    parse via the reused sentinel.read_health_csv and drive a "balanced" verdict.
"""

import json
import subprocess
import sys
from pathlib import Path

import hrv_baseline as hb
import safety_gate

SCRIPT = (Path(__file__).resolve().parents[1] / ".claude" / "skills"
          / "daily-check-skill" / "scripts" / "hrv_baseline.py")


def _rows(values, start="2026-05-01"):
    """Build [{date,hrv}] from a list, one consecutive day each (synthetic)."""
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    return [{"date": (d0 + dt.timedelta(days=i)).isoformat(), "hrv": v}
            for i, v in enumerate(values)]


# ----------------------------------------------------------------- 1. low floor
def test_low_floor_reuses_safety_gate_constant():
    # The "low" floor must BE safety_gate.HRV_RED — not a re-invented number.
    assert hb.LOW_FLOOR == safety_gate.HRV_RED


def test_latest_below_floor_is_low():
    # 20 days, latest dips under HRV_RED (50) -> "low" regardless of the band.
    vals = [65] * 19 + [44]
    out = hb.compute_baseline(_rows(vals), as_of=_rows(vals)[-1]["date"])
    assert out["status"] == "low"
    assert out["latest"]["value"] == 44
    assert out["n"] == 20


# ----------------------------------------------------------------- 2. balanced
def test_latest_within_band_is_balanced():
    vals = [64, 66, 65, 67, 63, 66, 65, 64, 67, 65,
            66, 63, 68, 65, 66, 64, 67, 65, 66, 65]
    out = hb.compute_baseline(_rows(vals), as_of=_rows(vals)[-1]["date"])
    assert out["status"] == "balanced"
    assert out["latest_vs_band"] == "within"
    assert out["band"]["low"] <= out["latest"]["value"] <= out["band"]["high"]


# ----------------------------------------------------------------- 3. unbalanced
def test_latest_above_band_is_unbalanced():
    # Tight cluster at 60 (so MAD is small) then a spike well above the band,
    # but still >= floor -> "unbalanced" (not "low").
    vals = [60] * 19 + [80]
    out = hb.compute_baseline(_rows(vals), as_of=_rows(vals)[-1]["date"])
    assert out["status"] == "unbalanced"
    assert out["latest_vs_band"] == "above"
    assert out["latest"]["value"] >= hb.LOW_FLOOR


# ----------------------------------------------------------------- 4. insufficient
def test_too_few_days_is_insufficient_but_still_emits_band():
    vals = [65, 66, 64]            # n=3 < MIN_DAYS=14
    out = hb.compute_baseline(_rows(vals), as_of=_rows(vals)[-1]["date"])
    assert out["status"] == "insufficient_data"
    assert out["n"] == 3
    # median/band/n must still be present even when insufficient.
    assert out["median"] == 65
    assert "low" in out["band"] and "high" in out["band"]
    assert out["min_days"] == hb.MIN_DAYS


# ----------------------------------------------------------------- 5. as_of window
def test_as_of_ignores_future_days_and_sets_latest():
    rows = _rows([65] * 20, start="2026-05-01")
    # Cut off at the 10th day -> only 10 days count, latest = that day.
    out = hb.compute_baseline(rows, as_of="2026-05-10")
    assert out["n"] == 10
    assert out["latest"]["date"] == "2026-05-10"
    assert out["as_of"] == "2026-05-10"


def test_bad_as_of_raises():
    import pytest
    with pytest.raises(hb.HrvBaselineError):
        hb.compute_baseline(_rows([65, 66]), as_of="2026-13-99")


def test_no_hrv_before_as_of_raises():
    import pytest
    with pytest.raises(hb.HrvBaselineError):
        hb.compute_baseline(_rows([65, 66], start="2026-05-01"), as_of="2026-04-01")


# ----------------------------------------------------------------- 6. CLI / error
def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True)


def test_cli_missing_file_errors_nonzero_json():
    r = _run("--health-csv", "/no/such/file.csv")
    assert r.returncode != 0
    assert json.loads(r.stdout)["error"]


# ----------------------------------------------------------------- 7. CSV e2e
def test_csv_reader_e2e_on_synthetic_fixture(fixtures_dir):
    csv_path = fixtures_dir / "hrv_history_synthetic.csv"
    import sentinel
    rows = sentinel.read_health_csv(str(csv_path))
    assert len(rows) >= hb.MIN_DAYS
    as_of = max(r["date"] for r in rows)
    out = hb.compute_baseline(rows, as_of=as_of)
    assert out["status"] == "balanced"
    assert out["n"] >= hb.MIN_DAYS

    # ...and the same fixture drives the CLI end-to-end.
    r = _run("--health-csv", str(csv_path))
    assert r.returncode == 0
    cli = json.loads(r.stdout)
    assert cli["status"] == "balanced"
    assert "latest" not in cli or isinstance(cli["latest"]["value"], (int, float))
