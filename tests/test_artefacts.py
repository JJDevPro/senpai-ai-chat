"""Synthetic, DATA-FREE tests for the two E4 artefact generators.

  * make_ics  → a valid VCALENDAR with the right VEVENT / RRULE count from a
    synthetic weekly rhythm + race list (Drive never touched — overrides only).
  * pacing_card → a markdown card whose per-km split rows sum EXACTLY to the
    target finish time, for both the even and the negative-split strategy.

No real health data is read — every input is hand-built here.
"""
import datetime as dt

import make_ics
import pacing_card


# ───────────────────────── make_ics ─────────────────────────
SYN_RHYTHM = "Mo=Run+Core@20:00;Di=Rest;Mi=Long Run@18:00;Do=Gym@21:30;Sa=Parkrun@09:00"
SYN_RACES = "Firmenlauf 6km|2026-07-21@09:00;Stadtlauf 10km|2026-10-04"


def test_make_ics_override_parses_training_days():
    events = make_ics.parse_rhythm_override(SYN_RHYTHM)
    # 5 entries, but Di=Rest is dropped → 4 training days.
    assert len(events) == 4
    bydays = {e["byday"] for e in events}
    assert bydays == {"MO", "WE", "TH", "SA"}
    do = next(e for e in events if e["byday"] == "TH")
    assert (do["hh"], do["mm"]) == (21, 30)  # "≤21:30"-style clock parsed


def test_make_ics_builds_valid_vcalendar():
    events = make_ics.parse_rhythm_override(SYN_RHYTHM)
    races = make_ics.parse_races_override(SYN_RACES)
    assert len(races) == 2
    weeks = 8
    ics = make_ics.build_ics(events, races, weeks=weeks, start=dt.date(2026, 6, 29))

    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.rstrip().endswith("END:VCALENDAR")
    # 4 weekly + 2 race = 6 VEVENTs, balanced BEGIN/END.
    assert ics.count("BEGIN:VEVENT") == 6
    assert ics.count("END:VEVENT") == 6
    # One RRULE per training day, none for the one-off races.
    assert ics.count("RRULE:FREQ=WEEKLY") == 4
    assert ics.count(f"COUNT={weeks}") == 4
    # The Saturday parkrun event lands on a real Saturday at 09:00.
    assert "BYDAY=SA" in ics
    assert "DTSTART:20260704T090000" in ics  # first Sat on/after 2026-06-29
    # Race day is a one-off (no RRULE) at its given date/time.
    assert "DTSTART:20260721T090000" in ics


def test_make_ics_parses_markdown_seed():
    # Robust to the real athlete.md / live.md markdown shape.
    rhythm_md = (
        "## Wochen-Rhythmus\n\n"
        "| Tag | Plan |\n|-----|-----|\n"
        "| **Mo** | Runna + Core 20:00 (Partnerin Zumba) |\n"
        "| **Di** | Rest |\n"
        "| **Mi** | Long Run (flex, HR ≤ Z2) |\n"
        "| **Do** | Full Body Gym ≤ 21:30 |\n"
        "| **Sa** | Parkrun 09:00 mit Trainingspartner |\n"
        "| **So** | Rest |\n"
    )
    races_md = (
        "## Race-Countdown\n\n"
        "- 🏃 **Firmenlauf (6 km) — 21.07.2026** → erstes V3-Rennen.\n"
        "- 2. Rennen: Sportscheck RUN 10 km (Oktober 2026, Datum TBC).\n"
    )
    events = make_ics.parse_rhythm_md(rhythm_md)
    races = make_ics.parse_races_md(races_md)
    assert {e["byday"] for e in events} == {"MO", "WE", "TH", "SA"}  # 2 Rest dropped
    # Mi has no explicit clock → per-day default 18:00; Do "≤21:30" parsed.
    assert next(e for e in events if e["byday"] == "WE")["hh"] == 18
    assert next(e for e in events if e["byday"] == "TH")["mm"] == 30
    # Only the dated race survives; "Datum TBC" line is skipped.
    assert len(races) == 1
    assert races[0]["date"] == dt.date(2026, 7, 21)
    assert races[0]["km"] == 6.0


# ───────────────────────── pacing_card ─────────────────────────
def test_pacing_card_splits_sum_to_target_even_and_neg():
    target = "39:00"          # 6 km @ 6:30/km
    card = pacing_card.build_card("Firmenlauf", 6.0, target_time=target)
    total = pacing_card.parse_mmss(target)
    assert card["target_sec"] == total
    assert len(card["even"]) == 6
    assert len(card["neg"]) == 6
    # EXACT integer sum to the target for both strategies.
    assert sum(s["split_sec"] for s in card["even"]) == total
    assert sum(s["split_sec"] for s in card["neg"]) == total
    assert card["even"][-1]["cum_sec"] == total
    assert card["neg"][-1]["cum_sec"] == total
    # Negative split: first km slower than average, last km faster.
    avg = total / 6.0
    assert card["neg"][0]["pace_sec"] > avg
    assert card["neg"][-1]["pace_sec"] < avg
    assert "Pacing-Card" in card["markdown"]


def test_pacing_card_reuses_readiness_band():
    # A synthetic stats.py race_readiness JSON (band shape verbatim).
    rr = {
        "race": {"event": "Firmenlauf", "km": 6.0},
        "projection": {
            "best": {"pace_min_per_km": 5.4, "finish": "32:24", "finish_minutes": 32.4},
            "real": {"pace_min_per_km": 5.7, "finish": "34:12", "finish_minutes": 34.2},
            "conservative": {"pace_min_per_km": 6.1, "finish": "36:36", "finish_minutes": 36.6},
        },
    }
    card = pacing_card.build_card("Firmenlauf", 6.0, readiness=rr)
    # 'real' band drives the target: 34.2 min = 2052 s.
    assert card["target_sec"] == round(34.2 * 60)
    assert sum(s["split_sec"] for s in card["neg"]) == card["target_sec"]
    assert card["band"]["best"]["finish"] == "32:24"
    assert "Ziel-Band" in card["markdown"]


def test_pacing_card_partial_km_distance_sums_exact():
    # Non-integer distance (parkrun 5 km would be integer; use 6.4 to hit the remainder).
    card = pacing_card.build_card("TestRace", 6.4, target_time="40:00")
    total = pacing_card.parse_mmss("40:00")
    assert len(card["neg"]) == 7  # 6 full km + 0.4 km tail
    assert sum(s["split_sec"] for s in card["neg"]) == total
    assert abs(card["neg"][-1]["length_km"] - 0.4) < 1e-6
