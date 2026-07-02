"""Regression tests for slice_hae_day.py (daily-check §3f / §3f-bis + Wave-1 fixes).

These lock in the four things that were the #1 daily-check bugs / the Wave-1
upgrades:

  1. TARGET-DAY SLICING — kumulative Tages-Summen MUST be filtered to `gestern`
     and never summed across the whole file. The fixture deliberately seeds a huge
     2026-06-26 sample for every cumulative metric; a correct slice ignores it.
  2. RAW HRV VOLATILITY — avg/min/max/range/std come from the RAW in-window HRV
     points, NOT the hourly means (hourly means smooth sigma artificially down).
     The fixture clusters extreme points (19, 120) into the same hour so raw sigma
     is an order of magnitude bigger than the hourly-bucketed sigma.
  3. BODY-COMP off_protocol — weiches Morgen-Fenster (Entscheidung 2026-07-02):
     Withings/Koerperwaage VORMITTAGS (<12:00) = gültige SoT; erst Nachmittag
     (>=12:00) oder eine Nicht-Waagen-Quelle flaggt off_protocol.
  4. LOAD-EXTRA — true_tdee = basal + active, exercise min, flights, and the
     walking-asymmetry trip-wire that fires only when sustained >5 %.

All inputs are the tiny synthetic fixture tests/fixtures/hae_synthetic.json.
"""

import statistics

import pytest

import slice_hae_day as s

AS_OF = "2026-06-28"   # gestern (load day) = 2026-06-27


@pytest.fixture(scope="module")
def sliced(hae_path):
    metrics = s._merge(s._load_metrics(str(hae_path)))
    return s.slice_day(metrics, AS_OF)


# ---------------------------------------------------------------- 1. target-day slicing
def test_gestern_is_as_of_minus_one(sliced):
    assert sliced["gestern"] == "2026-06-27"


def test_cumulative_sums_are_sliced_to_gestern_not_file_total(sliced):
    load = sliced["gestern_load"]
    # gestern-only: 300 + 200 = 500 (NOT 500 + 9999 = 10499 across the file).
    assert load["active_energy_kcal"] == 500.0
    # gestern-only: 4000 + 4000 = 8000 (NOT + 99999).
    assert load["steps"] == 8000
    # gestern-only: 3.0 + 2.0 = 5.0 km (NOT + 50.0).
    assert load["distance"] == {"value": 5.0, "units": "km"}
    # physical_effort uses avg/peak AT gestern (NOT pulled up by the 2026-06-26 50).
    assert load["physical_effort"] == {"avg": 6.0, "peak": 8.0}


def test_heart_is_gestern_only_and_waking(sliced):
    heart = sliced["gestern_load"]["heart"]
    assert heart["n_samples"] == 3            # only the 3 gestern HR samples
    assert heart["day_avg"] == 70.0           # (60 + 70 + 80) / 3
    assert heart["peak"] == 150.0             # max of the Max fields
    assert heart["peak_time"] == "18:00"
    # gestern HR predates the 2026-06-28 sleep window -> all waking, none excluded.
    assert heart["waking_avg"] == 70.0


# ---------------------------------------------------------------- 2. raw vs hourly HRV
def test_hrv_stats_come_from_raw_points(sliced):
    hrv = sliced["hrv_night"]
    # 6 RAW in-window points; the daytime 2026-06-27 point (200) is OUTSIDE the
    # sleep window and must be excluded -> max stays 120, n stays 6.
    assert hrv["n"] == 6
    assert hrv["min"] == 19
    assert hrv["max"] == 120
    assert hrv["range"] == 101
    assert hrv["std"] == 29.2


def test_raw_sigma_dwarfs_hourly_bucketed_sigma(sliced):
    """The whole point of the Wave-1 raw-volatility fix: hourly means hide sigma."""
    hrv = sliced["hrv_night"]
    hourly_vals = [h["hrv"] for h in hrv["hourly"]]
    hourly_std = statistics.pstdev(hourly_vals)     # ~1.9
    hourly_range = max(hourly_vals) - min(hourly_vals)  # 4
    # Raw sigma/range are an order of magnitude larger than the hourly-bucketed ones.
    assert hrv["std"] > 5 * hourly_std
    assert hrv["range"] > 10 * hourly_range
    assert hrv["std"] > 10            # absolute sanity: real volatility survived
    assert hourly_std < 5             # absolute sanity: hourly really did flatten it


def test_fine_15min_series_present(sliced):
    fine = sliced["hrv_night"]["fine"]
    assert isinstance(fine, list) and len(fine) >= 1
    # fine keys are 15-min buckets "YYYY-MM-DD HH:Q"
    assert all(set(("t", "hrv", "ampel")) <= set(p) for p in fine)


# ---------------------------------------------------------------- 3. body-comp off_protocol
def test_morning_withings_weight_is_valid_sot(sliced):
    """Weiches Morgen-Fenster (SoT = nüchtern nach dem Aufstehen, Richtwert ≤09:00,
    deterministisches Gate erst ab 12:00): die 09:30-Withings-Lesung ist GÜLTIGE SoT,
    nicht mehr off_protocol (Homeoffice-Realität, Entscheidung 2026-07-02)."""
    wc = sliced["body_comp"]["weight_body_mass"]
    # Latest reading is the 09:30 Withings (supersedes the 08:00 Koerperwaage).
    assert wc["source"] == "Withings"
    assert wc["time"] == "09:30"
    assert wc["off_protocol"] is False
    assert sliced["body_comp"]["body_fat_percentage"]["off_protocol"] is False


def test_afternoon_or_non_scale_reading_is_off_protocol():
    """Das off_protocol-Gate bleibt scharf: Nachmittags-Messung (>=12:00) ODER
    Nicht-Waagen-Quelle (manueller iPhone-Eintrag) flaggt weiterhin."""
    afternoon = {"weight_body_mass": {"units": "kg", "data": [
        {"date": "2026-06-28 14:05:00 +0200", "qty": 75.1, "source": "Withings"}]}}
    manual = {"weight_body_mass": {"units": "kg", "data": [
        {"date": "2026-06-28 08:00:00 +0200", "qty": 75.1, "source": "iPhone"}]}}
    assert s._body_comp(afternoon, AS_OF)["weight_body_mass"]["off_protocol"] is True
    assert s._body_comp(manual, AS_OF)["weight_body_mass"]["off_protocol"] is True


# ---------------------------------------------------------------- 4. load-extra
def test_load_extra_true_tdee_and_micros(sliced):
    le = sliced["load_extra"]
    assert le["basal_energy_kcal"] == 1500.0          # 800 + 700
    assert le["true_tdee_kcal"] == 2000.0             # basal 1500 + active 500
    assert le["exercise_min"] == 45                    # 20 + 25
    assert le["flights_climbed"] == 8                  # 5 + 3


def test_asymmetry_flag_fires_only_when_elevated(sliced):
    # Fixture: sustained 7.0 % (>5) -> flag fires.
    asym = sliced["load_extra"]["gait"]["asymmetry_pct"]
    assert asym["avg"] == 7.0
    assert asym["flag"] is True
    # Double-support 29 % is in the normal 20-40 band -> no flag.
    assert sliced["load_extra"]["gait"]["double_support_pct"]["flag"] is False

    # ...and the flag must NOT fire for a normal (<=5 %) reading.
    low = {"walking_asymmetry_percentage": {"units": "%",
           "data": [{"date": "2026-06-27 10:00:00 +0200", "qty": 3.0}]}}
    le_low = s._load_extra(low, "2026-06-27")
    assert le_low["gait"]["asymmetry_pct"]["flag"] is False


# ---------------------------------------------------------------- sleep attribution
def test_sleep_attributed_by_sleepend_on_as_of(sliced):
    sleep = sliced["heute_sleep"]
    assert sleep["attributed_by"] == "sleepEnd==as_of"
    assert sleep["total_h"] == 6.0
    assert sleep["bedtime"] == "00:15"
