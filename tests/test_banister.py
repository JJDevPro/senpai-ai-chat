"""Regression tests for banister.py (deterministic CTL/ATL/TSB).

The bug this script fixes: ad-hoc TSB swung between runs for the SAME day
(+10.3 vs -0.5) on identical data, because rest days were not zero-filled and
seeds/rounding drifted. These tests lock determinism and the gapless zerofill.

The expected CTL/ATL/TSB values below are pinned from the current
implementation (CTL tc=42, ATL tc=7, seed 0, gapless daily zerofill); they are
the regression anchor. If the engine changes and these move, that is a
deliberate decision to re-pin, not an accident.

Fixture: tests/fixtures/trainings_synthetic.csv -> after dedup the daily TRIMP
series is {2026-06-20: 50.0, 2026-06-22: 78.141, 2026-06-24: 65.0}.
"""

import banister as bb


def test_deterministic_same_input_same_output(trainings_csv_text):
    a = bb.compute_from_sheet(trainings_csv_text, as_of="2026-06-25")
    b = bb.compute_from_sheet(trainings_csv_text, as_of="2026-06-25")
    # Drop nested report objects that are irrelevant to the determinism check.
    for r in (a, b):
        r.pop("dedup_report", None)
        r.pop("extract_report", None)
    assert a == b


def test_pinned_ctl_atl_tsb(trainings_csv_text):
    res = bb.compute_from_sheet(trainings_csv_text, as_of="2026-06-25")
    assert res["ctl"] == 4.4
    assert res["atl"] == 20.2
    # tsb is rounded from the RAW ctl-atl (-15.877), not from the rounded
    # components (which would give -15.8) — the script rounds last, on purpose.
    assert res["tsb"] == -15.9


def test_gapless_zerofill(trainings_csv_text):
    res = bb.compute_from_sheet(trainings_csv_text, as_of="2026-06-25")
    # Series runs 2026-06-20 .. 2026-06-24 inclusive = 5 calendar days,
    # even though only 3 of them had a session (rest days zero-filled).
    assert res["series_start"] == "2026-06-20"
    assert res["series_end"] == "2026-06-24"
    assert res["n_calendar_days"] == 5
    assert res["n_session_days"] == 3
    # The two rest days (06-21, 06-23) carry TRIMP 0 in the tail.
    tail = {row[0]: row[1] for row in res["tail7"]}
    assert tail["2026-06-21"] == 0.0
    assert tail["2026-06-23"] == 0.0
    assert tail["2026-06-22"] == 78.1   # tail TRIMP is rounded to 1 dp for display


def test_as_of_before_any_session_degrades_gracefully(trainings_csv_text):
    # as_of precedes every session -> end clamps to series_start, no crash,
    # a valid one-day result is returned.
    res = bb.compute_from_sheet(trainings_csv_text, as_of="2026-06-01")
    assert res is not None
    assert res["series_start"] == "2026-06-20"
    assert res["series_end"] == "2026-06-20"
    assert res["n_calendar_days"] == 1
    assert res["warmup_ok"] is False


def test_empty_sheet_returns_none():
    # No parsable sessions at all -> banister returns None (caller shows "no data").
    assert bb.compute_from_sheet("Datum,TRIMP\n", as_of="2026-06-25") is None
