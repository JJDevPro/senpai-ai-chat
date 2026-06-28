"""Regression tests for readiness.py (Garmin-style morning Training-Readiness 0..100).

readiness.py verdichtet die fertigen Upstream-Outputs (hrv_baseline/slice_hae_day/
banister/safety_gate/sentinel + eine abgeleitete RHR-Abweichung) zu EINER 0..100-Zahl.
Inputs sind tiny SYNTHETIC already-reduced aggregates (kleine Dicts, genau die Keys,
die die Upstream-Skripte ausgeben) — no real data, no raw series, mirroring the
sentinel / safety_gate / hrv_baseline tests.

Locks:
  * Score liegt immer in 0..100.
  * Harter Safety-Override (gate red/critical ODER training_allowed False) deckelt
    auf <=35, setzt safety_override=True + band "red" — und kann nur SENKEN, nie heben.
  * top_limiter benennt die schwächste Komponente, top_driver die stärkste.
  * Brustgurt-/Aktivitäts-HR ("interval HR unreliable") verändert den Score NICHT.
  * insufficient HRV ist NEUTRAL gedämpft (0.6x), nicht 0.
  * Sentinel-WARN-Penalty: −5 je WARN, gedeckelt bei −15; CRITICAL/WATCH zählen nicht.
  * CLI: gültige Inputs -> JSON-Score; kaputtes JSON -> non-zero exit + error object.
"""

import json
import subprocess
import sys
from pathlib import Path

import readiness as rd

SCRIPT = (Path(__file__).resolve().parents[1] / ".claude" / "skills"
          / "daily-check-skill" / "scripts" / "readiness.py")


# ----------------------------------------------------------------- helpers
def _strong():
    """Alle Komponenten stark → hoher Score, kein Override."""
    return {
        "hrv_baseline": {"status": "balanced"},
        "daily": {"heute_sleep": {"total_h": 8.2}},
        "banister": {"tsb": 8.0},
        "safety_gate": {"level": "OK", "training_allowed": True},
        "sentinel": {"alerts": []},
        "rhr_deviation": 0.0,
    }


def _weak():
    """Alle Komponenten schwach (aber gate OK) → niedriger Score ohne Override."""
    return {
        "hrv_baseline": {"status": "low"},
        "daily": {"heute_sleep": {"total_h": 5.0}},
        "banister": {"tsb": -28.0},
        "safety_gate": {"level": "OK", "training_allowed": True},
        "sentinel": {"alerts": []},
        "rhr_deviation": 9.0,
    }


# ----------------------------------------------------------------- 1. score range
def test_score_always_in_0_100_strong():
    out = rd.compute_readiness(_strong())
    assert 0 <= out["score"] <= 100
    assert out["score"] >= 75
    assert out["band"] == "high"
    assert out["safety_override"] is False


def test_score_always_in_0_100_weak():
    out = rd.compute_readiness(_weak())
    assert 0 <= out["score"] <= 100
    # weak but not safety-capped -> low/very_low band, no override
    assert out["safety_override"] is False


def test_empty_inputs_is_robust_and_in_range():
    # No upstream data at all -> neutral components, still a valid 0..100 score.
    out = rd.compute_readiness({})
    assert 0 <= out["score"] <= 100
    assert out["safety_override"] is False


# ----------------------------------------------------------------- 2. safety override (floor-only)
def test_safety_override_caps_at_35_when_training_not_allowed():
    inp = _strong()
    inp["safety_gate"] = {"level": "CRITICAL", "training_allowed": False}
    out = rd.compute_readiness(inp)
    assert out["score"] <= 35
    assert out["safety_override"] is True
    assert out["band"] == "red"


def test_safety_override_via_red_level_alone():
    inp = _strong()
    # training_allowed not explicitly False, but level is CRITICAL -> still caps.
    inp["safety_gate"] = {"level": "CRITICAL", "training_allowed": None}
    out = rd.compute_readiness(inp)
    assert out["score"] <= 35
    assert out["safety_override"] is True
    assert out["band"] == "red"


def test_override_can_only_lower_never_raise():
    # A weak case that already scores below the cap must NOT be lifted up to 35.
    inp = _weak()
    base = rd.compute_readiness(inp)["score"]
    inp["safety_gate"] = {"level": "CRITICAL", "training_allowed": False}
    capped = rd.compute_readiness(inp)["score"]
    assert capped <= 35
    assert capped <= base  # floor-only: never raises a low score


def test_warn_level_gate_does_not_override():
    inp = _strong()
    inp["safety_gate"] = {"level": "WARN", "training_allowed": True}
    out = rd.compute_readiness(inp)
    assert out["safety_override"] is False
    assert out["score"] >= 75  # WARN is not a hard cap


# ----------------------------------------------------------------- 3. top_driver / top_limiter
def test_top_limiter_names_the_weakest_factor():
    # Everything strong except sleep (4h -> sleep01 = 0) -> sleep is the limiter.
    inp = _strong()
    inp["daily"] = {"heute_sleep": {"total_h": 4.0}}
    out = rd.compute_readiness(inp)
    assert out["top_limiter"] == "sleep"
    assert out["top_driver"] != "sleep"


def test_top_driver_names_the_strongest_factor():
    # HRV balanced (1.0) is the only maxed component; others below 1.0 -> hrv drives.
    inp = {
        "hrv_baseline": {"status": "balanced"},
        "daily": {"heute_sleep": {"total_h": 6.5}},   # 0.5
        "banister": {"tsb": -12.0},                    # ~0.51
        "rhr_deviation": 4.0,                          # 0.6
    }
    out = rd.compute_readiness(inp)
    assert out["top_driver"] == "hrv"


# ----------------------------------------------------------------- 4. chest strap = no effect
def test_chest_strap_unreliable_input_does_not_change_score():
    base = rd.compute_readiness(_strong())
    inp = _strong()
    # An "interval HR unreliable" style signal from an activity / chest strap.
    inp["interval_hr_reliable"] = False
    inp["chest_strap"] = {"interval_hr": 178, "reliable": False, "note": "strap dropout"}
    inp["activity_hr"] = {"avg": 165, "max": 188}
    out = rd.compute_readiness(inp)
    assert out["score"] == base["score"]
    assert out["band"] == base["band"]
    assert out["components"] == base["components"]


# ----------------------------------------------------------------- 5. insufficient HRV neutral
def test_insufficient_hrv_is_neutral_not_zero():
    inp = _strong()
    inp["hrv_baseline"] = {"status": "insufficient_data"}
    out = rd.compute_readiness(inp)
    c = out["components"]["hrv"]
    # 0.6x of the raw 1.0 -> dampened but clearly positive, not zero.
    assert c["score01"] == 0.6
    assert c["points"] > 0
    assert out["meta"]["hrv_insufficient"] is True


def test_missing_hrv_status_treated_as_insufficient():
    inp = _strong()
    inp["hrv_baseline"] = {}   # no status key
    out = rd.compute_readiness(inp)
    assert out["components"]["hrv"]["score01"] == 0.6
    assert out["meta"]["hrv_insufficient"] is True


def test_low_hrv_scores_below_insufficient():
    low = rd.compute_readiness({**_strong(), "hrv_baseline": {"status": "low"}})
    insuf = rd.compute_readiness({**_strong(), "hrv_baseline": {"status": "insufficient_data"}})
    # "low" (real bad reading) must score the HRV component below a merely-thin one.
    assert low["components"]["hrv"]["score01"] < insuf["components"]["hrv"]["score01"]


# ----------------------------------------------------------------- 6. sentinel penalty
def test_warn_penalty_is_minus5_each_capped_at_15():
    no_warn = rd.compute_readiness(_strong())["score"]
    one_warn = rd.compute_readiness({**_strong(),
                                     "sentinel": {"alerts": [{"level": "WARN"}]}})["score"]
    assert no_warn - one_warn == 5

    many = {"alerts": [{"level": "WARN"}] * 5}   # 5 WARN -> would be -25, capped -15
    capped = rd.compute_readiness({**_strong(), "sentinel": many})
    assert no_warn - capped["score"] == 15
    assert capped["meta"]["sentinel_penalty"] == 15


def test_watch_and_critical_alerts_do_not_penalize():
    no_pen = rd.compute_readiness(_strong())["score"]
    inp = {**_strong(),
           "sentinel": {"alerts": [{"level": "WATCH"}, {"level": "CRITICAL"}]}}
    out = rd.compute_readiness(inp)
    assert out["meta"]["sentinel_penalty"] == 0
    assert out["score"] == no_pen


# ----------------------------------------------------------------- 7. CLI
def test_cli_emits_score_json(tmp_path):
    hb = tmp_path / "hrv.json"
    hb.write_text(json.dumps({"status": "balanced"}), encoding="utf-8")
    daily = tmp_path / "daily.json"
    daily.write_text(json.dumps({"heute_sleep": {"total_h": 8.0}}), encoding="utf-8")
    ban = tmp_path / "ban.json"
    ban.write_text(json.dumps({"tsb": 6.0}), encoding="utf-8")

    res = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--hrv-baseline", str(hb), "--daily", str(daily),
         "--banister", str(ban), "--rhr-deviation", "0"],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert 0 <= out["score"] <= 100
    assert out["band"] == "high"
    assert set(out) >= {"score", "band", "top_driver", "top_limiter",
                        "safety_override", "components"}


def test_cli_bad_json_exits_nonzero_with_error_object(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--daily", str(bad)],
        capture_output=True, text=True)
    assert res.returncode != 0
    err = json.loads(res.stdout)
    assert "error" in err


def test_cli_safety_gate_override_caps(tmp_path):
    hb = tmp_path / "hrv.json"
    hb.write_text(json.dumps({"status": "balanced"}), encoding="utf-8")
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"level": "CRITICAL", "training_allowed": False}),
                    encoding="utf-8")
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--hrv-baseline", str(hb),
         "--safety-gate", str(gate), "--rhr-deviation", "0"],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["safety_override"] is True
    assert out["score"] <= 35
    assert out["band"] == "red"
