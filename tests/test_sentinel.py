"""Regression tests for sentinel.py (deterministic V3 proactive trip-wires).

The Sentinel turns CLAUDE.md §5/§6 prose into a HARD, testable list of the only
ACTIONABLE signals Senpai should surface proactively. Inputs are tiny synthetic
already-reduced aggregates (a daily-slice dict, daily HRV/RHR rows, daily weigh-ins)
— no real data, no raw series, mirroring the safety_gate / slice_hae_day tests.

Locks:
  * HRV🔴 sustained (2 days <50) -> WARN + actionable; healthy HRV -> no alert.
  * HRV🔴🔴 (<40) -> CRITICAL pointer that DEFERS to safety_gate (no training_allowed).
  * RHR sustained >= baseline+5 for 2 days -> WARN.
  * Weight creeping toward the metabolic threshold (passed in, not hardcoded) -> WARN;
    over threshold -> WARN; trending up without a threshold -> WATCH (not actionable).
  * Bedtime well past 00:30 -> WARN.
  * walking-asymmetry flag True -> WARN; breathing >10 -> WARN.
  * all-clear -> actionable False.
  * CSV parser: German 'Tägliche Kennzahlen' headers (HFV / Ruheherzfrequenz / VO₂ max)
    + comma decimals resolve to {date,hrv,rhr}.
"""

import sentinel as sen

# ----------------------------------------------------------------- shared fixtures
HEALTHY_DAILY = {
    "as_of": "2026-06-28",
    "hrv_night": {"avg": 66},
    "heute_sleep": {"bedtime": "23:45", "total_h": 7.2},
    "load_extra": {"gait": {"asymmetry_pct": {"avg": 3.0, "flag": False}}},
    "recovery": {"breathing_disturbances": {"value": 4, "date": "2026-06-28"}},
    "body_comp": {"weight_body_mass": None},
}
HEALTHY_HEALTH = [
    {"date": "2026-06-26", "hrv": 64, "rhr": 50},
    {"date": "2026-06-27", "hrv": 66, "rhr": 51},
    {"date": "2026-06-28", "hrv": 67, "rhr": 50},
]


def _signals(out):
    return {a["signal"]: a for a in out["alerts"]}


# ----------------------------------------------------------------- 1. HRV sustained
def test_hrv_sustained_red_fires_on_two_days_below_50():
    out = sen.evaluate(health_rows=[
        {"date": "2026-06-26", "hrv": 48},
        {"date": "2026-06-27", "hrv": 47},
    ])
    a = _signals(out)["hrv_sustained_red"]
    assert a["level"] == "WARN"
    assert out["actionable"] is True
    assert "hrv_sustained_red" in out["checked"]


def test_healthy_hrv_does_not_fire():
    out = sen.evaluate(health_rows=[
        {"date": "2026-06-26", "hrv": 64},
        {"date": "2026-06-27", "hrv": 66},
    ])
    assert "hrv_sustained_red" not in _signals(out)
    assert out["actionable"] is False
    # ...but it WAS evaluated (data present) -> shows in checked.
    assert "hrv_sustained_red" in out["checked"]


def test_single_red_day_is_only_a_watch():
    # Only today red, prior day green -> WATCH (no 2-day pattern), not actionable.
    out = sen.evaluate(health_rows=[
        {"date": "2026-06-26", "hrv": 62},
        {"date": "2026-06-27", "hrv": 47},
    ])
    assert _signals(out)["hrv_sustained_red"]["level"] == "WATCH"
    assert out["actionable"] is False


def test_today_hrv_from_daily_is_merged_into_trend():
    # Yesterday <50 in the CSV + today <50 from the slice -> 2-day WARN.
    out = sen.evaluate(
        daily={"as_of": "2026-06-28", "hrv_night": {"avg": 46}},
        health_rows=[{"date": "2026-06-27", "hrv": 48}],
    )
    assert _signals(out)["hrv_sustained_red"]["level"] == "WARN"


# ----------------------------------------------------------------- 2. HRV double-red defer
def test_hrv_double_red_defers_to_safety_gate():
    out = sen.evaluate(daily={"as_of": "2026-06-28", "hrv_night": {"avg": 35}})
    a = _signals(out)["hrv_double_red"]
    assert a["level"] == "CRITICAL"
    assert out["actionable"] is True
    assert "safety_gate" in a["detail"].lower()
    # The Sentinel must NOT duplicate the gate -> no training decision in the output.
    assert "training_allowed" not in out


# ----------------------------------------------------------------- 3. RHR elevation
def test_rhr_elevation_fires_when_two_days_above_baseline_plus_5():
    out = sen.evaluate(health_rows=[
        {"date": "2026-06-24", "rhr": 50},
        {"date": "2026-06-25", "rhr": 51},
        {"date": "2026-06-26", "rhr": 49},
        {"date": "2026-06-27", "rhr": 57},   # baseline median 50 -> +7
        {"date": "2026-06-28", "rhr": 58},   # +8
    ])
    a = _signals(out)["rhr_elevation"]
    assert a["level"] == "WARN"
    assert out["actionable"] is True


def test_rhr_needs_enough_history_to_be_checked():
    # 3 days only -> baseline not establishable -> wire not even checked.
    out = sen.evaluate(health_rows=[
        {"date": "2026-06-26", "rhr": 50},
        {"date": "2026-06-27", "rhr": 60},
        {"date": "2026-06-28", "rhr": 61},
    ])
    assert "rhr_elevation" not in out["checked"]
    assert "rhr_elevation" not in _signals(out)


# ----------------------------------------------------------------- 4. weight creep
def test_weight_creep_toward_threshold_fires():
    out = sen.evaluate(
        weight_rows=[
            {"date": "2026-06-07", "weight_kg": 110.0},
            {"date": "2026-06-14", "weight_kg": 111.5},
            {"date": "2026-06-21", "weight_kg": 112.5},
            {"date": "2026-06-28", "weight_kg": 113.2},   # 0.8 kg under 114, trending up
        ],
        weight_threshold_kg=114.0,
    )
    a = _signals(out)["weight_creep"]
    assert a["level"] == "WARN"
    assert out["actionable"] is True
    assert "114" in a["detail"]


def test_weight_over_threshold_fires():
    out = sen.evaluate(
        weight_rows=[{"date": "2026-06-21", "weight_kg": 113.0},
                     {"date": "2026-06-28", "weight_kg": 115.0}],
        weight_threshold_kg=114.0,
    )
    assert _signals(out)["weight_creep"]["level"] == "WARN"


def test_weight_trend_without_threshold_is_only_watch():
    out = sen.evaluate(
        weight_rows=[{"date": "2026-06-21", "weight_kg": 100.0},
                     {"date": "2026-06-28", "weight_kg": 101.0}],
    )
    assert _signals(out)["weight_creep"]["level"] == "WATCH"
    assert out["actionable"] is False


def test_weight_far_below_threshold_does_not_alarm():
    out = sen.evaluate(
        weight_rows=[{"date": "2026-06-21", "weight_kg": 100.0},
                     {"date": "2026-06-28", "weight_kg": 100.5}],
        weight_threshold_kg=114.0,
    )
    # trending up but ~13 kg headroom -> WATCH at most, never actionable.
    a = _signals(out).get("weight_creep")
    assert a is None or a["level"] == "WATCH"
    assert out["actionable"] is False


# ----------------------------------------------------------------- 5. bedtime drift
def test_bedtime_drift_fires_past_0030():
    out = sen.evaluate(daily={"as_of": "2026-06-28", "heute_sleep": {"bedtime": "01:30"}})
    assert _signals(out)["bedtime_drift"]["level"] == "WARN"
    assert out["actionable"] is True


def test_bedtime_before_midnight_is_clean():
    out = sen.evaluate(daily={"as_of": "2026-06-28", "heute_sleep": {"bedtime": "23:50"}})
    assert "bedtime_drift" not in _signals(out)
    assert "bedtime_drift" in out["checked"]


# ----------------------------------------------------------------- 6. asymmetry + breathing
def test_walking_asymmetry_flag_true_alerts():
    out = sen.evaluate(daily={
        "as_of": "2026-06-28",
        "load_extra": {"gait": {"asymmetry_pct": {"avg": 7.0, "flag": True}}},
    })
    assert _signals(out)["walking_asymmetry"]["level"] == "WARN"
    assert out["actionable"] is True


def test_breathing_above_10_alerts():
    out = sen.evaluate(daily={
        "as_of": "2026-06-28",
        "recovery": {"breathing_disturbances": {"value": 14, "date": "2026-06-28"}},
    })
    assert _signals(out)["breathing_disturbances"]["level"] == "WARN"
    assert out["actionable"] is True


def test_breathing_at_or_below_10_is_clean():
    out = sen.evaluate(daily={
        "as_of": "2026-06-28",
        "recovery": {"breathing_disturbances": {"value": 10, "date": "2026-06-28"}},
    })
    assert "breathing_disturbances" not in _signals(out)


# ----------------------------------------------------------------- 7. all-clear
def test_all_clear_is_not_actionable():
    out = sen.evaluate(daily=HEALTHY_DAILY, health_rows=HEALTHY_HEALTH)
    assert out["alerts"] == []
    assert out["actionable"] is False
    # several wires were evaluated and stayed silent.
    assert {"hrv_sustained_red", "bedtime_drift", "walking_asymmetry",
            "breathing_disturbances"} <= set(out["checked"])


def test_no_inputs_is_robust():
    out = sen.evaluate()
    assert out["alerts"] == []
    assert out["actionable"] is False
    assert out["checked"] == []


# ----------------------------------------------------------------- 8. CSV parsing
def test_health_csv_parses_german_headers_and_commas(tmp_path):
    csv_text = (
        "Datum,Ruheherzfrequenz,HFV,VO₂ max\n"
        "2026-06-26,52,48,34.1\n"
        "27.06.2026,53,47,34.0\n"          # dt. DD.MM.YYYY + same columns
        "Zwischensumme,,,\n"               # non-date row must be skipped
    )
    p = tmp_path / "kennzahlen.csv"
    p.write_text(csv_text, encoding="utf-8")
    rows = sen.read_health_csv(str(p))
    assert [r["date"] for r in rows] == ["2026-06-26", "2026-06-27"]
    assert [r["hrv"] for r in rows] == [48.0, 47.0]
    assert [r["rhr"] for r in rows] == [52.0, 53.0]
    # ...and they drive the sustained-red wire end-to-end.
    out = sen.evaluate(health_rows=rows)
    assert _signals(out)["hrv_sustained_red"]["level"] == "WARN"


def test_weight_csv_parses_dot_decimal(tmp_path):
    # pull_drive.py writes UNFORMATTED_VALUE numbers -> dot decimals, comma-delimited.
    p = tmp_path / "gewicht.csv"
    p.write_text("Datum,Gewicht\n2026-06-21,112.5\n2026-06-28,113.4\n", encoding="utf-8")
    rows = sen.read_weight_csv(str(p))
    assert rows == [{"date": "2026-06-21", "weight_kg": 112.5},
                    {"date": "2026-06-28", "weight_kg": 113.4}]


def test_num_handles_thousands_and_comma():
    assert sen._num("1.234,5") == 1234.5
    assert sen._num("55,3") == 55.3
    assert sen._num("48") == 48.0
    assert sen._num("") is None
    assert sen._num(None) is None
