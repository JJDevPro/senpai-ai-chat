"""Tests für lib/clock.py — deterministische lokale Zeit + Zeitfenster.

DATA-FREE & API-FREE: kein echter Clock-Read (alles via injiziertem `now`),
keine Personendaten. Lockt die UTC→Berlin-Umrechnung + die Fenster-Grenzen.
"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LIB = Path(__file__).resolve().parents[1] / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import clock  # noqa: E402

BERLIN = ZoneInfo("Europe/Berlin")


def _b(h, m=0):
    return datetime(2026, 6, 28, h, m, tzinfo=BERLIN)


def test_local_now_naive_is_local_time():
    # naiv = bereits lokale Zeit in tz (KEIN UTC-Shift) — so wie --now gemeint ist.
    dt = clock.local_now("Europe/Berlin", datetime(2026, 6, 28, 19, 43))
    assert (dt.hour, dt.minute) == (19, 43)
    assert dt.tzinfo is not None


def test_local_now_aware_utc_is_converted():
    # tz-aware UTC wird in die Ziel-TZ umgerechnet (Sommer +2h).
    aware = datetime(2026, 6, 28, 12, 0, tzinfo=ZoneInfo("UTC"))
    assert clock.local_now("Europe/Berlin", aware).hour == 14  # +2 CEST


def test_time_window_boundaries():
    assert clock.time_window(_b(6)) == "morgen"
    assert clock.time_window(_b(9)) == "morgen"
    assert clock.time_window(_b(10)) == "tag"
    assert clock.time_window(_b(16)) == "tag"
    assert clock.time_window(_b(17)) == "abend"
    assert clock.time_window(_b(21)) == "abend"
    assert clock.time_window(_b(22)) == "nacht"
    assert clock.time_window(_b(3)) == "nacht"


def test_roast_morning_window():
    assert clock.is_roast_morning(_b(5, 30)) is True
    assert clock.is_roast_morning(_b(9, 59)) is True
    assert clock.is_roast_morning(_b(10)) is False
    assert clock.is_roast_morning(_b(4)) is False


def test_bedtime_window():
    assert clock.is_bedtime_window(_b(22)) is True
    assert clock.is_bedtime_window(_b(23, 30)) is True
    assert clock.is_bedtime_window(_b(21, 59)) is False


def test_parse_now_roundtrip():
    assert clock.parse_now(None) is None
    d = clock.parse_now("2026-06-29T07:00")
    assert (d.year, d.month, d.day, d.hour) == (2026, 6, 29, 7)


def test_cli_smoke(capsys):
    rc = clock.main(["--now", "2026-06-28T19:43", "--tz", "Europe/Berlin"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "19:43" in out          # naiv = lokale Zeit (kein Shift)
    assert "bedtime=False" in out  # 19:43 < 22:00
    assert "window=abend" in out
