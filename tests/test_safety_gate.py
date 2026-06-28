"""Regression tests for safety_gate.py (deterministic V3 safety overrides).

The gate turns CLAUDE.md §6 prose into a HARD gate the verdict layer must obey.
Inputs are tiny synthetic daily-slice dicts (only hrv_night.avg + heute_sleep.total_h
are read), so no real data is needed.

Locks:
  * HRV 🔴🔴 (avg<40 AND sleep<6h) -> CRITICAL, training_allowed False (non-negotiable).
  * Healthy -> OK, training allowed.
  * --opt-out -> roast_allowed False (persona off), training untouched.
  * --injury -> roast off + training_allowed None (assessment needed).
  * AFib markers are DELIBERATELY ignored -> never gate.
"""

import safety_gate as sg

HEALTHY = {"hrv_night": {"avg": 68}, "heute_sleep": {"total_h": 7.0}}


def test_critical_when_low_hrv_and_short_sleep():
    g = sg.evaluate_gate({"hrv_night": {"avg": 35}, "heute_sleep": {"total_h": 5.0}})
    assert g["level"] == "CRITICAL"
    assert g["training_allowed"] is False


def test_healthy_is_ok():
    g = sg.evaluate_gate(HEALTHY)
    assert g["level"] == "OK"
    assert g["training_allowed"] is True
    assert g["roast_allowed"] is True


def test_opt_out_disables_roast_only():
    g = sg.evaluate_gate(HEALTHY, opt_out=True)
    assert g["roast_allowed"] is False
    assert g["training_allowed"] is True   # opt-out never gates training
    assert g["level"] == "OK"


def test_injury_is_medical_override():
    g = sg.evaluate_gate(HEALTHY, injury=True)
    assert g["roast_allowed"] is False
    assert g["training_allowed"] is None    # assessment required, not a hard yes


def test_injury_does_not_unblock_a_critical_streichen():
    # A CRITICAL training-stop must stay False even when injury also fires.
    g = sg.evaluate_gate({"hrv_night": {"avg": 35}, "heute_sleep": {"total_h": 5.0}},
                         injury=True)
    assert g["level"] == "CRITICAL"
    assert g["training_allowed"] is False
    assert g["roast_allowed"] is False


def test_afib_input_never_gates():
    # AFib / rhythm fields are user-specific ignore -> the gate must not read them.
    g = sg.evaluate_gate({**HEALTHY, "afib_burden_pct": 99, "atrial_fibrillation": True})
    assert g["level"] == "OK"
    assert g["training_allowed"] is True
    assert g["roast_allowed"] is True


def test_low_hrv_alone_is_only_a_watch():
    # Single-day 🔴 without the 2-day confirmation is a WATCH, not an escalation.
    g = sg.evaluate_gate({"hrv_night": {"avg": 45}, "heute_sleep": {"total_h": 7.0}})
    assert g["level"] == "WATCH"
    assert g["training_allowed"] is True


def test_low_hrv_two_days_confirmed_is_warn():
    g = sg.evaluate_gate({"hrv_night": {"avg": 45}, "heute_sleep": {"total_h": 7.0}},
                         prev_hrv=44)
    assert g["level"] == "WARN"
