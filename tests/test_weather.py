"""Tests für lib/weather.py — die pure reduce()-Logik (kein Netz, kein Bright-Sky-Call).

DATA-FREE & DETERMINISTISCH: synthetisches Roh-JSON, feste Timestamps. Lockt die
PR-2-Fixes: Slot-Start-Floor (20:30-Start braucht die 20:00-Stunde), korrektes
Einheiten-Label wind_max_kmh, Warnungen, Asphalt-Regen-Dämpfung, Taupunkt-Band.
Dazu die Offline-Flags: --from-json (Datei-Replay durch reduce(), kein Netz),
--print-url (nur URL drucken) und build_url() als geteilte URL-Quelle.
"""

import json
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


# --- Offline-Flags: --from-json / --print-url / build_url (KEIN Netz) -------------


def test_build_url_matches_fetch_construction():
    # build_url = BASE + urlencode in Arg-Reihenfolge lat/lon/date/tz (wie fetch()).
    url = weather.build_url(52.52, 13.41, "2026-07-01", "Europe/Berlin")
    assert url == ("https://api.brightsky.dev/weather"
                   "?lat=52.52&lon=13.41&date=2026-07-01&tz=Europe%2FBerlin")
    assert url.startswith(weather.BASE + "?")


def test_print_url_prints_url_and_exits_zero(capsys):
    rc = weather.main(["--lat", "52.52", "--lon", "13.41", "--date", "2026-07-01",
                       "--print-url"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == weather.build_url(52.52, 13.41, "2026-07-01", weather.DEFAULT_TZ)


def test_from_json_replays_file_through_reduce(tmp_path, capsys):
    # Offline-Replay: synthetische Roh-Response aus Datei → identischer reduce()-Pfad
    # wie der Fetch-Modus (Slot-Fenster + day_summary + Sonnenzeiten aus lat/lon/date).
    raw = _raw([_hour(19, 24.0), _hour(20, 23.0, wind=18.0),
                _hour(21, 22.0, wind=25.0), _hour(22, 21.0)])
    fixture = tmp_path / "brightsky_raw.json"
    fixture.write_text(json.dumps(raw), encoding="utf-8")

    rc = weather.main(["--lat", "52.52", "--lon", "13.41", "--date", "2026-07-01",
                       "--slot-start", "20:30", "--slot-end", "21:30",
                       "--from-json", str(fixture)])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    # Slot-Fenster inkl. Start-Floor (20:30 → 20:00-Stunde).
    assert [h["time"] for h in out["slot_window"]] == ["20:00", "21:00"]
    assert out["slot"] == {"start": "20:30", "end": "21:30"}
    # Tages-Aggregat aus der Fixture, kein Roh-Dump.
    assert out["day_summary"]["min_c"] == 21.0
    assert out["day_summary"]["max_c"] == 24.0
    assert out["day_summary"]["wind_max_kmh"] == 25.0
    assert out["warnings"] == []
    assert "weather" not in out
    # Sonnenzeiten kommen aus lat/lon/date — deshalb bleiben die Args Pflicht.
    assert out["sun"] is not None
    assert set(out["sun"]) == {"sunrise", "sunset"}


def test_from_json_output_identical_to_direct_reduce(tmp_path, capsys):
    # --from-json muss die IDENTISCHE Ausgabe liefern wie reduce() auf demselben Raw.
    raw = _raw([_hour(9, 18.0), _hour(10, 19.5)])
    fixture = tmp_path / "brightsky_raw.json"
    fixture.write_text(json.dumps(raw), encoding="utf-8")

    rc = weather.main(["--lat", "52.52", "--lon", "13.41", "--date", "2026-07-01",
                       "--slot-start", "09:00", "--slot-end", "10:00",
                       "--from-json", str(fixture)])
    cli_out = json.loads(capsys.readouterr().out)
    expected = weather.reduce(raw, "09:00", "10:00",
                              lat=52.52, lon=13.41, date="2026-07-01",
                              tz=weather.DEFAULT_TZ)
    assert rc == 0
    assert cli_out == expected
