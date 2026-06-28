"""Regression tests for season.py (batch/season analysis over Trainings_v5).

DATA-FREE: a tiny synthetic CSV (tests/fixtures/season_synthetic.csv) with
hand-computed monthly aggregates is the only input. The fixture has:
  - 2026-05: two outdoor runs (one booked twice -> dedup must drop it) + one
    strength session (must NOT count as a run).
  - 2026-06: one outdoor + one indoor run.

Hand-computed run aggregates (post-dedup, runs only):
  2026-05: 2 runs, 15.0 km, 120.0 TRIMP, avg HR 145.0, longest 10.0 km,
           paces 30/5=6.0 & 50/10=5.0 -> avg 5.5 min/km -> "5:30".
  2026-06: 2 runs, 16.0 km, 135.0 TRIMP, avg HR 150.0, longest 12.0 km,
           paces 60/12=5.0 & 25/4=6.25 -> avg 5.625 min/km -> "5:38".
"""

from pathlib import Path

import pytest

import season as sn

FIX = Path(__file__).resolve().parent / "fixtures" / "season_synthetic.csv"


@pytest.fixture(scope="module")
def raw():
    return FIX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def res(raw):
    return sn.analyze_season(raw, as_of="2026-06-04", months=0)


def test_dedup_drops_double_booked_run(res):
    # 6 data rows, one is an exact dup -> 5 unique sessions, 4 of them runs.
    assert res["span"]["n_sessions"] == 5
    assert res["span"]["n_runs"] == 4


def test_monthly_aggregates_pinned(res):
    months = {m["month"]: m for m in res["monthly"]}
    assert set(months) == {"2026-05", "2026-06"}

    may = months["2026-05"]
    assert may["runs"] == 2
    assert may["km"] == 15.0
    assert may["trimp"] == 120.0
    assert may["avg_hr"] == 145.0
    assert may["longest_km"] == 10.0
    assert may["avg_pace"] == "5:30"

    jun = months["2026-06"]
    assert jun["runs"] == 2
    assert jun["km"] == 16.0
    assert jun["trimp"] == 135.0
    assert jun["avg_hr"] == 150.0
    assert jun["longest_km"] == 12.0
    assert jun["avg_pace"] == "5:38"


def test_strength_session_excluded_from_runs_but_in_type_dist(res):
    # The Krafttraining row must not inflate run counts...
    assert sum(m["runs"] for m in res["monthly"]) == 4
    # ...but it must still appear in the activity-type distribution.
    td = res["type_distribution"]
    assert td["Funktionelles Krafttraining"] == 1
    # Three outdoor runs survive dedup: 05-02, 05-10 (the double-book dropped), 06-01.
    assert td["Laufen outdoor"] == 3
    assert td["Laufen indoor"] == 1


def test_pace_is_flagged_derived(res):
    # The sheet has no native pace column -> trend must be marked derived.
    assert res["pace_trend"]["derived"] is True
    assert res["pace_trend"]["from"] == "2026-05"
    assert res["pace_trend"]["to"] == "2026-06"
    # May 5.5 -> Jun 5.625 min/km = +0.125 min = +7.5 s/km, slower.
    assert res["pace_trend"]["delta_sec_per_km"] == 7.5
    assert res["pace_trend"]["direction"] == "langsamer"


def test_pace_z2_progression_is_honest(res):
    pz = res["pace_z2_progression"]
    assert pz["available"] is False
    assert "forward-tracked" in pz["proposal"].lower()
    assert "pace-z2.csv" in pz["proposal"]


def test_ctl_trajectory_endpoint_matches_banister(res):
    # The trajectory endpoint must equal the deterministic banister final point.
    traj = res["ctl_trajectory"]
    assert traj is not None
    assert traj["ctl_end"] == res["ctl_final"]["ctl"]
    assert traj["tsb_end"] == res["ctl_final"]["tsb"]


def test_empty_sheet_degrades_gracefully():
    res = sn.analyze_season("Datum,Art,TRIMP\n", as_of="2026-06-04")
    assert res.get("insufficient_data") is True
