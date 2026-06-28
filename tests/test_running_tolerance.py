"""Regression tests for running_tolerance.py (FR970 "Running Tolerance" clone).

The module turns the "don't ramp weekly volume too fast" rule into a HARD,
deterministic verdict the readiness layer can reference. ACWR = acute (newest
week) / chronic (4-week rolling mean); ramp_flag fires when ACWR > 1.3; the
ceiling = 1.3 × chronic.

DATA-FREE: every input is a tiny SYNTHETIC weekly-load list authored here — no
real personal/health values. All math is unit-neutral (km or TRIMP).

Locks:
  * ramp_flag fires when ACWR > 1.3, and NOT on/below the threshold (boundary).
  * ceiling math = 1.3 × chronic; week_km = newest week; chronic = 4-week mean.
  * status ampel mapping (sweet_spot / ramp_too_steep / underloaded).
  * daily->weekly aggregation (trailing 7-day blocks).
  * bad input -> ValueError (CLI -> JSON error object, non-zero exit).
  * --as-of is echoed; no wall-clock dependence (deterministic).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import running_tolerance as rt

SCRIPT = (Path(__file__).resolve().parents[1] / ".claude" / "skills"
          / "daily-check-skill" / "scripts" / "running_tolerance.py")


# --------------------------------------------------------------------------- #
# Pure compute_tolerance
# --------------------------------------------------------------------------- #
def test_steady_load_is_sweet_spot_no_ramp():
    # Flat 30/wk -> chronic 30, acute 30, ACWR 1.0 -> sweet spot, no ramp.
    res = rt.compute_tolerance([30, 30, 30, 30])
    assert res["acwr"] == 1.0
    assert res["ramp_flag"] is False
    assert res["status"] == "sweet_spot"
    assert res["ampel"] == "🟢"
    assert res["chronic_km"] == 30.0
    assert res["week_km"] == 30.0


def test_ceiling_is_factor_times_chronic():
    # chronic = mean(20,20,20,20) = 20 -> ceiling = 1.3 * 20 = 26.0
    res = rt.compute_tolerance([20, 20, 20, 20])
    assert res["chronic_km"] == 20.0
    assert res["ceiling_km"] == 26.0
    assert res["ceiling_factor"] == 1.3


def test_ramp_flag_fires_above_threshold():
    # weeks 20,20,20,40 -> chronic mean(20,20,20,40)=25, acute 40 -> ACWR 1.6 > 1.3
    res = rt.compute_tolerance([20, 20, 20, 40])
    assert res["acwr"] == 1.6
    assert res["ramp_flag"] is True
    assert res["status"] == "ramp_too_steep"
    assert res["ampel"] == "🔴"


def test_ramp_flag_not_on_threshold_boundary():
    # Construct ACWR exactly 1.3: acute / chronic == 1.3 must NOT flag (> not >=).
    # weeks a,a,a,b with chronic=(3a+b)/4 ; pick a=10,b=18 -> chronic=12, acwr=18/12=1.5 (no).
    # Use exact boundary: chronic=10, acute=13 -> need 4-week mean 10 with last 13.
    # weeks 9,9,9,13 -> mean=10.0, acwr=13/10=1.3 exactly.
    res = rt.compute_tolerance([9, 9, 9, 13])
    assert res["chronic_km"] == 10.0
    assert res["acwr"] == 1.3
    assert res["ramp_flag"] is False          # exactly 1.3 is allowed (sweet-spot edge)
    assert res["status"] == "sweet_spot"


def test_underloaded_when_below_band():
    # Big drop: chronic high, acute low -> ACWR < 0.8 -> underloaded (yellow, no drama).
    res = rt.compute_tolerance([40, 40, 40, 10])
    # chronic = mean(40,40,40,10)=32.5 ; acwr = 10/32.5 = 0.31
    assert res["acwr"] < rt.ACWR_LOW
    assert res["status"] == "underloaded"
    assert res["ampel"] == "🟡"
    assert res["ramp_flag"] is False


def test_chronic_uses_only_last_four_weeks():
    # 8 weeks; chronic must ignore the oldest 4.
    res = rt.compute_tolerance([100, 100, 100, 100, 20, 20, 20, 20])
    assert res["chronic_km"] == 20.0     # mean of last 4, not all 8
    assert res["chronic_full"] is True
    assert res["chronic_weeks"] == 4


def test_short_history_uses_available_weeks():
    res = rt.compute_tolerance([30, 30])
    assert res["chronic_km"] == 30.0
    assert res["chronic_full"] is False
    assert res["chronic_weeks"] == 2


def test_single_week_acwr_is_one():
    res = rt.compute_tolerance([25])
    assert res["acwr"] == 1.0
    assert res["status"] == "sweet_spot"
    assert res["ramp_flag"] is False


# --------------------------------------------------------------------------- #
# daily -> weekly aggregation
# --------------------------------------------------------------------------- #
def test_daily_to_weekly_trailing_blocks():
    # 14 days, two clean weeks of 7 days each.
    daily = [1] * 7 + [2] * 7
    weeks = rt.daily_to_weekly(daily)
    assert weeks == [7.0, 14.0]


def test_daily_to_weekly_drops_leading_partial():
    # 10 days -> one full trailing week (7), 3 leading days dropped.
    daily = [9, 9, 9] + [1, 2, 3, 4, 5, 6, 7]
    weeks = rt.daily_to_weekly(daily)
    assert weeks == [28.0]   # sum(1..7), leading partial discarded


# --------------------------------------------------------------------------- #
# determinism / as_of
# --------------------------------------------------------------------------- #
def test_as_of_is_echoed_and_deterministic():
    a = rt.compute_tolerance([30, 30, 30, 30], as_of="2026-06-28")
    b = rt.compute_tolerance([30, 30, 30, 30], as_of="2026-06-28")
    assert a == b
    assert a["as_of"] == "2026-06-28"


# --------------------------------------------------------------------------- #
# bad input -> ValueError (pure) / JSON error + non-zero exit (CLI)
# --------------------------------------------------------------------------- #
def test_empty_list_raises():
    with pytest.raises(ValueError):
        rt.compute_tolerance([])


def test_negative_load_raises():
    with pytest.raises(ValueError):
        rt.compute_tolerance([30, -5, 30, 30])


def test_bad_as_of_raises():
    with pytest.raises(ValueError):
        rt.compute_tolerance([30, 30], as_of="not-a-date")


# --------------------------------------------------------------------------- #
# CLI smoke (subprocess) — exit codes + JSON shape
# --------------------------------------------------------------------------- #
def test_cli_weekly_ok():
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--weekly", "20,20,20,40", "--as-of", "2026-06-28"],
        capture_output=True, text=True)
    assert out.returncode == 0
    res = json.loads(out.stdout)
    assert res["ramp_flag"] is True
    assert res["as_of"] == "2026-06-28"


def test_cli_bad_input_nonzero_with_error_object():
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--weekly", "30,-5"],
        capture_output=True, text=True)
    assert out.returncode != 0
    res = json.loads(out.stdout)
    assert "error" in res
