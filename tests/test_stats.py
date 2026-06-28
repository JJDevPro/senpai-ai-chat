"""Synthetic, DATA-FREE regression tests for stats.py.

The four analyses are advisory and must be HONEST about data sufficiency.
These tests lock:
  * bedtime_hrv recovers a known OLS slope from a crafted dataset (+ guards),
  * the robust z-score flags an injected outlier (HFV-down / RHR-up),
  * the insufficient-data paths return the guard instead of a bogus fit,
  * race projection produces a monotone best<real<conservative band,
  * banister_fit stays ADVISORY and falls back to the 42/7 default when thin.

No real health data is touched — every input is hand-built here.
"""

import numpy as np

import stats


# ───────────────────────── 1) bedtime_hrv ─────────────────────────
def test_bedtime_hrv_recovers_known_slope():
    # Truth: HRV = 60 - 2.0 * bedtime_lateness, tiny deterministic noise.
    rng = np.random.default_rng(42)
    xs = np.linspace(-1.0, 3.0, 120)          # 23:00 .. 03:00
    true_slope, true_int = -2.0, 60.0
    ys = true_int + true_slope * xs + rng.normal(0, 0.3, xs.size)
    res = stats.fit_bedtime_hrv(list(zip(xs, ys)), ref_bedtime=0.5)

    assert "insufficient_data" not in res
    assert res["n"] == 120
    assert abs(res["slope_ms_per_hour_later"] - true_slope) < 0.15
    lo, hi = res["ci95"]
    assert lo <= true_slope <= hi               # CI brackets the truth
    assert res["r_squared"] > 0.95
    assert res["significant_5pct"] is True


def test_bedtime_hrv_confound_model_runs():
    rng = np.random.default_rng(1)
    xs = np.linspace(-1.0, 3.0, 80)
    durs = list(7.0 - 0.2 * xs)                  # later -> slightly shorter
    ys = 58.0 - 1.5 * xs + rng.normal(0, 0.4, xs.size)
    res = stats.fit_bedtime_hrv(list(zip(xs, ys)), durations=durs)
    assert "controlled_for_sleep_duration" in res
    assert res["controlled_for_sleep_duration"]["n"] == 80


def test_bedtime_hrv_insufficient_n():
    res = stats.fit_bedtime_hrv([(0.0, 55.0), (1.0, 54.0), (2.0, 53.0)])
    assert res["insufficient_data"] is True
    assert res["n"] == 3


def test_bedtime_hrv_no_bedtime_variance():
    # All same bedtime -> slope not identifiable -> guard.
    pairs = [(0.5, 55.0 + (i % 3)) for i in range(40)]
    res = stats.fit_bedtime_hrv(pairs)
    assert res["insufficient_data"] is True
    assert "Streuung" in res["reason"]


# ───────────────────────── 2) anomaly ─────────────────────────
def _stable_series(n=30, level=55.0):
    # Small, non-zero spread so MAD > 0.
    return [level + (1 if i % 2 else -1) * (1 + (i % 3)) for i in range(n)]


def test_anomaly_flags_injected_hrv_drop():
    series = _stable_series() + [28.0]           # latest = big HRV collapse
    res = stats.robust_anomaly(series, higher_is_bad=False, z_thresh=3.5)
    assert res["is_outlier"] is True
    assert res["is_adverse_outlier"] is True      # low HRV is adverse
    assert res["robust_z"] < -3.5
    assert res["direction"] == "niedrig"


def test_anomaly_flags_injected_rhr_spike():
    series = _stable_series(level=60.0) + [95.0]  # latest = RHR spike
    res = stats.robust_anomaly(series, higher_is_bad=True, z_thresh=3.5)
    assert res["is_adverse_outlier"] is True       # high RHR is adverse
    assert res["robust_z"] > 3.5


def test_anomaly_normal_latest_not_flagged():
    series = _stable_series() + [55.0]
    res = stats.robust_anomaly(series, higher_is_bad=False)
    assert res["is_outlier"] is False
    assert res["is_adverse_outlier"] is False


def test_anomaly_insufficient_n():
    res = stats.robust_anomaly([55, 54, 56], higher_is_bad=False)
    assert res["insufficient_data"] is True


# ───────────────────────── 3) race projection ─────────────────────────
def test_project_race_band_is_monotone():
    band = stats.project_race(8.0, race_km=6.0, tsb=None)
    assert set(band) == {"best", "real", "conservative"}
    bp = band["best"]["pace_min_per_km"]
    rp = band["real"]["pace_min_per_km"]
    cp = band["conservative"]["pace_min_per_km"]
    assert bp < rp < cp                            # best is fastest
    assert all(":" in band[k]["finish"] for k in band)


def test_project_race_fresh_tsb_speeds_up():
    base = stats.project_race(8.0, tsb=None)["real"]["pace_min_per_km"]
    fresh = stats.project_race(8.0, tsb=20.0)["real"]["pace_min_per_km"]
    assert fresh < base                            # high TSB -> a touch faster


# ───────────────────────── 4) banister_fit (advisory) ─────────────────────────
def test_banister_fit_thin_history_returns_default():
    import datetime as dt
    trimp = {dt.date(2026, 6, 1): 50.0, dt.date(2026, 6, 3): 80.0}
    resp = {dt.date(2026, 6, 1): 55.0, dt.date(2026, 6, 3): 52.0}
    res = stats.fit_banister_tc(trimp, resp)
    assert res["insufficient_data"] is True
    assert res["recommended_tc"] == [42, 7]        # NEVER silently replaces 42/7


def test_banister_fit_is_advisory_and_well_formed():
    # Long synthetic history; response loosely tracks a CTL-like decay.
    import datetime as dt
    start = dt.date(2025, 1, 1)
    trimp, resp = {}, {}
    acc = 0.0
    lam = 1 - np.exp(-1 / 30)                       # "true" tc ~ 30
    for i in range(200):
        d = start + dt.timedelta(days=i)
        load = 60.0 if i % 3 == 0 else 0.0
        trimp[d] = load
        acc += (load - acc) * lam
        resp[d] = 40.0 + 0.3 * acc                  # HRV rises with fitness
    res = stats.fit_banister_tc(trimp, resp)
    assert res["advisory_only"] is True
    assert isinstance(res["recommended_tc"], list) and len(res["recommended_tc"]) == 2
    # The deterministic default must always remain reported for comparison.
    assert res["default_tc"] == [42, 7]
