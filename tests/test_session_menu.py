"""Tests für lib/session_menu.py — das Action-HUD.

DATA-FREE & DETERMINISTISCH: `now` wird injiziert (kein Clock-Read), Texte sind
synthetisch. Lockt das Wochentag×Zeitfenster-Routing + Data-Freiheit.
"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LIB = Path(__file__).resolve().parents[1] / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import session_menu as sm  # noqa: E402

BERLIN = ZoneInfo("Europe/Berlin")


def _b(date_str, h, m=0):
    y, mo, d = map(int, date_str.split("-"))
    return datetime(y, mo, d, h, m, tzinfo=BERLIN)


# Bekannte Wochentage 2026: Mo 29.06 · Sa 04.07 · So 28.06
def test_day_plan_weekdays():
    assert sm.day_plan(0)["name"] == "Mo"
    assert sm.day_plan(2)["type"] == "Long Run"
    assert sm.day_plan(3)["slot"].startswith("Full Body")
    assert sm.day_plan(6)["kw_action"].startswith("/payload")
    assert sm.day_plan(1)["slot"] is None  # Di Ruhetag


def test_hud_monday_morning_has_briefing_sot_sync():
    h = sm.build_hud(_b("2026-06-29", 7), "", "", full=False)
    assert "Mo" in h and "Heute: Lauf + Core" in h
    assert "/briefing" in h
    assert "SoT-Wiegen" in h
    assert "/sync" in h
    assert "Automation: inaktiv" in h


def test_hud_saturday_preslot_weather():
    # Sa 08:00, Parkrun 09:00 -> Pre-Slot-Wetter feuert (slot_hour-h == 1).
    h = sm.build_hud(_b("2026-07-04", 8), "", "", full=False)
    assert "Sa" in h
    assert "Pre-Lauf" in h


def test_hud_sunday_evening_payload_bedtime_and_tomorrow_monday():
    h = sm.build_hud(_b("2026-06-28", 23), "", "", full=False)
    assert "/payload" in h
    assert "Bedtime" in h          # >= 22:00
    assert "Morgen:" in h and "Mo" in h  # forward-looking


def test_hud_full_lists_skill_index():
    h = sm.build_hud(_b("2026-06-29", 9), "", "", full=True)
    assert "Skills & Commands" in h
    assert "/menu" in h
    assert "Race-Projektion" in h


def test_race_line_from_live_full_only():
    live = "## Race-Countdown\n- 🏃 **B2Run 6 km** — 21.07.2026 → erstes V3-Rennen.\n"
    h_full = sm.build_hud(_b("2026-06-29", 9), "", live, full=True)
    assert "Race:" in h_full and "B2Run" in h_full
    # kompakt liest live nicht -> keine Race-Zeile
    assert "Race:" not in sm.build_hud(_b("2026-06-29", 9), "", live, full=False)


def test_hud_is_data_free():
    h = sm.build_hud(_b("2026-06-29", 9), "", "", full=True)
    for tok in ("Javier", "Garcell", "Nürnberg", "Janna"):
        assert tok not in h


def test_main_smoke_exit0(capsys):
    assert sm.main(["--now", "2026-06-29T07:00"]) == 0
    assert "Senpai HUD" in capsys.readouterr().out
