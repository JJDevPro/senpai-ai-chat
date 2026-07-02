"""Tests für lib/make_ics.py — Parsing + ICS-Emission (kein Drive, injizierte Zeit).

DATA-FREE & DETERMINISTISCH: synthetische Markdown-/Override-Strings; build_ics
bekommt start+now injiziert. Lockt den PR-2-Crash-Fix (Zielzeit "sub 40:00"
erzeugte hour=40) und die Zeit-Injektion.
"""

import datetime as dt
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import make_ics as mi  # noqa: E402

START = dt.date(2026, 6, 29)          # ein Montag
NOW = dt.datetime(2026, 6, 29, 12, 0)


def test_race_line_with_goal_time_does_not_crash():
    # Audit-CONFIRMED: "sub 40:00" wurde als Startzeit 40:00 geparst → ValueError.
    md = "## Race-Countdown\n- 🏃 Stadtlauf 6 km — 21.07.2026 → Ziel sub 40:00\n"
    races = mi.parse_races_md(md)
    assert len(races) == 1
    assert (races[0]["hh"], races[0]["mm"]) == (9, 0)  # Default, NICHT 40:00
    ics = mi.build_ics([], races, weeks=4, start=START, now=NOW)
    assert "BEGIN:VEVENT" in ics and "DTSTART:20260721T090000" in ics


def test_race_line_with_explicit_start_time():
    md = "## Race-Countdown\n- Stadtlauf 6 km — 21.07.2026 @10:15 → Ziel sub 40:00\n"
    races = mi.parse_races_md(md)
    assert (races[0]["hh"], races[0]["mm"]) == (10, 15)


def test_race_line_uhr_notation():
    md = "## Race-Countdown\n- Herbstlauf 10 km — 2026-10-03 Start 8:30 Uhr\n"
    races = mi.parse_races_md(md)
    assert (races[0]["hh"], races[0]["mm"]) == (8, 30)


def test_race_line_tbc_skipped():
    md = "## Race-Countdown\n- Frühjahrslauf (Datum TBC)\n"
    assert mi.parse_races_md(md) == []


def test_parse_race_time_goal_context_skipped():
    assert mi._parse_race_time("Ziel 1:10 — Start offen") == (9, 0)
    assert mi._parse_race_time("cutoff 3:00:00") == (9, 0)
    assert mi._parse_race_time("Start 18:05") == (18, 5)


def test_races_override_invalid_hour_falls_back():
    races = mi.parse_races_override("Testlauf|2026-08-01@40:00")
    assert (races[0]["hh"], races[0]["mm"]) == (9, 0)


def test_rhythm_override_and_ics_shape():
    events = mi.parse_rhythm_override("Mo=Run+Core@20:00;Di=Rest;Sa=Parkrun@09:00")
    assert [e["day"] for e in events] == ["mo", "sa"]  # Rest-Tag erzeugt kein Event
    ics = mi.build_ics(events, [], weeks=2, start=START, now=NOW)
    assert ics.count("BEGIN:VEVENT") == 2
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=2" in ics
    assert "DTSTAMP:20260629T120000" in ics  # injizierte Zeit, kein Clock-Read


def test_build_ics_is_deterministic_with_injected_time():
    events = mi.parse_rhythm_override("Mi=Long Run@18:00")
    a = mi.build_ics(events, [], weeks=3, start=START, now=NOW)
    b = mi.build_ics(events, [], weeks=3, start=START, now=NOW)
    assert a == b
