"""Regression tests for dedup_trainings.py (Trainings_v5 sheet-hygiene).

Locks the three behaviours that keep CTL/ATL/TSB trustworthy:

  1. A TRUE double-write (same session written twice at different TRIMP precision,
     e.g. 78.141 vs 78.097) MUST collapse to ONE session after numeric-key
     normalisation (TRIMP -> 0 decimals, Strecke -> 2). Without this the ATL
     explodes (122 instead of 42).
  2. A structural-noise row (a separator/summary line with no valid Datum+TRIMP)
     MUST be reported in noise_rows and NEVER counted as a duplicate.
  3. A wrong-schema input (no Datum / TRIMP columns) MUST set schema_warning.

Fixture: tests/fixtures/trainings_synthetic.csv (5 data lines: 1 clean, a
2026-06-22 double-write pair, 1 clean, 1 noise row "Zwischensumme,,,...").
"""

import dedup_trainings as dd


def test_double_write_collapses_to_one_session(trainings_csv_text):
    clean, report = dd.dedup(trainings_csv_text)
    # 5 raw rows -> 1 noise dropped -> 4 nutzdaten -> 1 dup removed -> 3 unique.
    assert report["zeilen_gesamt"] == 5
    assert report["zeilen_nutzdaten"] == 4
    assert report["zeilen_eindeutig"] == 3
    assert report["duplikate_entfernt"] == 1
    assert len(clean) == 3

    # The collapsed pair is the 2026-06-22 session, booked 2x.
    top = report["top_duplikate"]
    assert len(top) == 1
    assert top[0]["kopien"] == 2
    assert "2026-06-22" in top[0]["session"]
    assert "trimp=78" in top[0]["session"]      # 78.141 and 78.097 normalise to 78

    # Exactly one row survives for 2026-06-22 (the first occurrence, full precision).
    days = [r[0] for r in clean]
    assert days.count("2026-06-22") == 1
    kept_2206 = next(r for r in clean if r[0] == "2026-06-22")
    assert kept_2206[4] == "78.141"             # raw TRIMP preserved on the kept row


def test_noise_row_reported_and_not_a_duplicate(trainings_csv_text):
    clean, report = dd.dedup(trainings_csv_text)
    assert report["noise_rows"] == 1
    # The noise row must NOT inflate the duplicate count.
    assert report["duplikate_entfernt"] == 1
    # ...and must not leak into the clean session set.
    assert all(r[0] != "Zwischensumme" for r in clean)


def test_clean_input_has_no_schema_warning(trainings_csv_text):
    _, report = dd.dedup(trainings_csv_text)
    assert report["schema_warning"] is None
    assert "session-key" in report["dedup_modus"]


def test_wrong_schema_sets_schema_warning():
    # No Datum / TRIMP columns -> the dedup must shout, not silently guess.
    bad = "Foo,Bar,Baz\n1,2,3\n4,5,6\n"
    _, report = dd.dedup(bad)
    assert report["schema_warning"] is not None
    assert "Datum" in report["schema_warning"]
    assert "TRIMP" in report["schema_warning"]
