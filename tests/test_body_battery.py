"""Regression tests for body_battery.py (heuristic Body-Battery surrogate 0..100).

body_battery turns the reduced daily-check outputs (hrv_baseline status, slice
sleep/stress/activity, banister tsb/atl) into ONE WHOOP/Garmin-style 0..100 energy
gauge: sleep RECHARGES, daytime load/stress DRAINS. Like the safety_gate / sentinel /
hrv_baseline tests, the inputs here are tiny SYNTHETIC already-reduced dicts — no real
data, no raw per-minute series, mirroring the rest of the suite.

Locks:
  * good sleep + low load -> bb_end UP vs prev rest, recharged > drained.
  * heavy load -> bb_end DOWN, drained dominates.
  * output is a DAY AGGREGATE: only the documented keys, NO minute-by-minute series.
  * 0..100 bounds are always respected (clamped).
  * status ampel tracks bb_end; HRV 'low' status damps the recharge.
  * bad --as-of -> compute raises; CLI exits non-zero with a JSON error object.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import body_battery as bb

SCRIPT = (Path(__file__).resolve().parents[1] / ".claude" / "skills" /
          "daily-check-skill" / "scripts" / "body_battery.py")

# The only keys the aggregate is allowed to expose (NO minute series / raw arrays).
ALLOWED_KEYS = {
    "as_of", "surrogate", "bb_start", "bb_end", "recharged", "drained",
    "low_point", "status", "prev_rest", "recharge_basis", "drain_basis", "note",
}

GOOD_SLEEP = {"total_h": 8.0, "deep_h": 1.4, "rem_h": 1.7, "awake_h": 0.2}
POOR_SLEEP = {"total_h": 4.5, "deep_h": 0.3, "rem_h": 0.4, "awake_h": 1.2}
LOW_LOAD = {"tsb": 8.0, "atl": 15.0}
HEAVY_LOAD = {"tsb": -22.0, "atl": 95.0}
HEAVY_ACTIVITY = {"active_energy_kcal": 1100, "physical_effort_peak": 8.5}
REST_ACTIVITY = {"active_energy_kcal": 120, "physical_effort_peak": 1.0}
HRV_BALANCED = {"status": "balanced"}
HRV_LOW = {"status": "low"}


# ----------------------------------------------------------------- 1. recharge wins
def test_good_sleep_low_load_recharges():
    out = bb.compute_body_battery({
        "as_of": "2026-06-28",
        "prev_bb": 30,
        "sleep": GOOD_SLEEP,
        "hrv": HRV_BALANCED,
        "load": LOW_LOAD,
        "activity": REST_ACTIVITY,
    })
    # Morning is fuller than yesterday's rest, and the easy day drains little.
    assert out["bb_start"] > out["prev_rest"]
    assert out["recharged"] > out["drained"]
    assert out["bb_end"] >= out["prev_rest"]
    assert out["status"] in ("ok", "high")


# ----------------------------------------------------------------- 2. drain wins
def test_heavy_load_drains_battery():
    out = bb.compute_body_battery({
        "as_of": "2026-06-28",
        "prev_bb": 60,
        "sleep": POOR_SLEEP,
        "hrv": HRV_LOW,
        "load": HEAVY_LOAD,
        "activity": HEAVY_ACTIVITY,
        "stress": {"breathing_disturbances": 25},
    })
    # Heavy day pulls the end below the morning charge; drain dominates.
    assert out["bb_end"] < out["bb_start"]
    assert out["drained"] > out["recharged"]
    assert out["status"] in ("low", "critical")


def test_same_morning_heavier_load_ends_lower():
    base = {"as_of": "2026-06-28", "prev_bb": 50, "sleep": GOOD_SLEEP,
            "hrv": HRV_BALANCED}
    easy = bb.compute_body_battery({**base, "load": LOW_LOAD, "activity": REST_ACTIVITY})
    hard = bb.compute_body_battery({**base, "load": HEAVY_LOAD, "activity": HEAVY_ACTIVITY})
    # Identical recharge -> the heavier day must end lower.
    assert hard["bb_start"] == easy["bb_start"]
    assert hard["bb_end"] < easy["bb_end"]
    assert hard["drained"] > easy["drained"]


# ----------------------------------------------------------------- 3. aggregate only
def test_output_is_aggregate_only_no_minute_series():
    out = bb.compute_body_battery({
        "as_of": "2026-06-28", "sleep": GOOD_SLEEP, "hrv": HRV_BALANCED,
        "load": LOW_LOAD, "activity": REST_ACTIVITY,
    })
    # Exactly the documented day-aggregate keys, nothing else.
    assert set(out) <= ALLOWED_KEYS
    assert {"bb_start", "bb_end", "drained", "recharged", "low_point", "status"} <= set(out)
    # No value in the output is a long array (would smell of a minute/second series).
    for v in out.values():
        assert not (isinstance(v, list) and len(v) > 8)
    # The basis dicts are small explanations, not series.
    assert isinstance(out["recharge_basis"], dict)
    assert all(not isinstance(x, list) for x in out["drain_basis"].values())


# ----------------------------------------------------------------- 4. bounds
def test_values_clamped_to_0_100():
    # Perfect night on top of an already-full battery -> capped at 100, never above.
    full = bb.compute_body_battery({
        "as_of": "2026-06-28", "prev_bb": 95, "sleep": GOOD_SLEEP,
        "hrv": HRV_BALANCED, "load": LOW_LOAD, "activity": REST_ACTIVITY,
    })
    assert 0 <= full["bb_start"] <= 100
    assert 0 <= full["bb_end"] <= 100
    assert full["bb_start"] == 100

    # Empty battery + brutal day -> floored at 0, never negative.
    empty = bb.compute_body_battery({
        "as_of": "2026-06-28", "prev_bb": 3, "sleep": POOR_SLEEP,
        "hrv": HRV_LOW, "load": HEAVY_LOAD, "activity": HEAVY_ACTIVITY,
        "stress": {"breathing_disturbances": 40},
    })
    assert empty["bb_end"] == 0
    assert empty["status"] == "critical"


# ----------------------------------------------------------------- 5. hrv damps recharge
def test_low_hrv_status_damps_recharge():
    base = {"as_of": "2026-06-28", "prev_bb": 30, "sleep": GOOD_SLEEP,
            "load": LOW_LOAD, "activity": REST_ACTIVITY}
    balanced = bb.compute_body_battery({**base, "hrv": HRV_BALANCED})
    low = bb.compute_body_battery({**base, "hrv": HRV_LOW})
    # A 'low' HRV status recharges the battery less than a 'balanced' one.
    assert low["recharged"] < balanced["recharged"]


# ----------------------------------------------------------------- 6. robust to gaps
def test_missing_blocks_are_neutralized_not_crashing():
    out = bb.compute_body_battery({"as_of": "2026-06-28"})
    assert 0 <= out["bb_start"] <= 100
    assert 0 <= out["bb_end"] <= 100
    assert out["status"] in ("high", "ok", "low", "critical")


def test_empty_inputs_is_robust():
    out = bb.compute_body_battery({})
    assert set(out) <= ALLOWED_KEYS
    assert out["as_of"] is None


# ----------------------------------------------------------------- 7. bad input
def test_bad_as_of_raises():
    with pytest.raises(bb.BodyBatteryError):
        bb.compute_body_battery({"as_of": "28.06.2026", "sleep": GOOD_SLEEP})


# ----------------------------------------------------------------- 8. CLI end-to-end
def test_cli_inputs_json_roundtrip(tmp_path):
    inputs = {"as_of": "2026-06-28", "prev_bb": 30, "sleep": GOOD_SLEEP,
              "hrv": HRV_BALANCED, "load": LOW_LOAD, "activity": REST_ACTIVITY}
    p = tmp_path / "inputs.json"
    p.write_text(json.dumps(inputs), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "--inputs-json", str(p)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["as_of"] == "2026-06-28"
    assert 0 <= out["bb_end"] <= 100
    assert set(out) <= ALLOWED_KEYS


def test_cli_bad_as_of_exits_nonzero_with_json_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"as_of": "not-a-date"}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "--inputs-json", str(p)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    err = json.loads(r.stdout)
    assert "error" in err
