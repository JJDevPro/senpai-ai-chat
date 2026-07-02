"""Tests für lib/weather.py — die pure reduce()-Logik (kein Netz, kein Bright-Sky-Call).

DATA-FREE & DETERMINISTISCH: synthetisches Roh-JSON, feste Timestamps. Lockt die
PR-2-Fixes: Slot-Start-Floor (20:30-Start braucht die 20:00-Stunde), korrektes
Einheiten-Label wind_max_kmh, Warnungen, Asphalt-Regen-Dämpfung, Taupunkt-Band.
"""

import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import weather  # noqa: E402


def _hour(ts_hour, temp, precip=0.0, wind=10.0, dew=8.0, solar=None, sunshine=None,
          cloud=50):
    return {
        "timestamp": f"2026-07-01T{ts_hour:02d}:00:00+02:00",
        "temperature": temp,
        "precipitation": precip,
        "precipitation_probability": 20,
        "wind_speed": wind,
        "wind_gust_speed": wind + 8,
        "relative_humidity": 60,
        "dew_point": dew,
        "cloud_cover": cloud,
        "condition": "dry",
        "solar": solar,
        "sunshine": sunshine,
    }


def _raw(hours):
    return {"weather": hours, "sources": [{"station_name": "Teststation"}]}


def test_slot_start_gets_floored_to_full_hour():
    # Lauf 20:30–21:30 → die 20:00-Stunde IST die Slot-Starttemp und muss drin sein.
    raw = _raw([_hour(19, 24.0), _hour(20, 23.0), _hour(21, 22.0), _hour(22, 21.0)])
    out = weather.reduce(raw, "20:30", "21:30")
    times = [h["time"] for h in out["slot_window"]]
    assert times == ["20:00", "21:00"]
    assert out["warnings"] == []


def test_full_hour_slot_unchanged():
    raw = _raw([_hour(19, 24.0), _hour(20, 23.0), _hour(21, 22.0)])
    out = weather.reduce(raw, "20:00", "21:00")
    assert [h["time"] for h in out["slot_window"]] == ["20:00", "21:00"]


def test_wind_key_is_labelled_kmh():
    raw = _raw([_hour(20, 23.0, wind=18.0), _hour(21, 22.0, wind=25.0)])
    out = weather.reduce(raw, "20:00", "21:00")
    assert out["day_summary"]["wind_max_kmh"] == 25.0
    assert "wind_max_ms" not in out["day_summary"]  # alte Einheiten-Falle ist weg


def test_empty_hours_produces_warning():
    out = weather.reduce(_raw([]), "20:00", "21:00")
    assert any("KEINE Stundenwerte" in w for w in out["warnings"])


def test_slot_without_matching_hours_warns():
    raw = _raw([_hour(9, 18.0)])
    out = weather.reduce(raw, "20:00", "21:00")
    assert any("Keine Stunden im Slot" in w for w in out["warnings"])


def test_rain_damps_asphalt_estimate():
    # Aktiver Regen kühlt den Belag → Aufschlag fällt auf <=1.0 °C.
    dry = _hour(20, 25.0, solar=0.8, sunshine=50)
    wet = _hour(21, 25.0, precip=2.0, solar=0.8, sunshine=50)
    out = weather.reduce(_raw([dry, wet]), "20:00", "21:00")
    w20, w21 = out["slot_window"]
    assert w20["asphalt_excess_c_est"] > 1.0
    assert w21["asphalt_excess_c_est"] <= 1.0


def test_dew_point_band_labels():
    assert weather._dew_band(-2) == "sehr trocken, angenehm"
    assert weather._dew_band(17) == "schwül, unangenehm"
    assert weather._dew_band(22) == "sehr schwül, drückend"
    assert weather._dew_band(None) is None


def test_reduce_never_dumps_raw_array():
    # Kernregel §0: kein 24-h-Dump — reduce() gibt nur Slot-Fenster + Aggregat.
    raw = _raw([_hour(h, 20.0) for h in range(24)])
    out = weather.reduce(raw, "20:00", "21:00")
    assert len(out["slot_window"]) == 2
    assert "weather" not in out
