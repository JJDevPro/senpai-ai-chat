"""daily_signals.py — Tag-Signale, deterministisch (PR-3).

Kernstück: die **Tag-Shift-Regression** (Audit-CONFIRMED). Vor dem Fix fiel
`daylight`/`audio` bei gesetztem `as_of` still auf den LETZTEN Datentag zurück —
ein Morgen-Check ohne heutige Tageslicht-Punkte zeigte damit GESTERN als "heute".
Jetzt gilt: `as_of` pinnt today/yesterday auf EXAKTE Kalendertage; fehlt der Tag,
ist der Slot None (ehrlich), nie ein anderer Tag.

DATA-FREE: alle Inputs sind hand-gebaute synthetische Dicts mit bekannten Werten.
"""

import json

import pytest

import daily_signals as DS


# ---------------------------------------------------------------- helpers
def _metric(name, units, points, **extra_fields):
    """points = [(date_str, qty), ...] → HAE-Metrik-Block."""
    return {
        "name": name,
        "units": units,
        "data": [dict({"date": d, "qty": q}, **extra_fields) for d, q in points],
    }


def _hae(*metrics):
    return {"data": {"metrics": list(metrics)}}


def _merged(*metrics):
    return DS._load(_hae(*metrics))


# ---------------------------------------------------------------- daylight: Tag-Shift
def test_daylight_as_of_missing_today_is_none_not_yesterday():
    """DIE Regression: Daten nur bis gestern + as_of=heute → today=None (kein Shift)."""
    m = _merged(_metric("time_in_daylight", "min", [
        ("2026-06-26 12:00:00 +0200", 40),
        ("2026-06-27 12:00:00 +0200", 70),
        ("2026-06-27 15:00:00 +0200", 20),
    ]))
    res = DS.daylight_minutes(m, as_of="2026-06-28")
    assert res["today"] is None                       # NICHT still der 27.
    assert res["yesterday"]["day"] == "2026-06-27"
    assert res["yesterday"]["minutes"] == 90          # Tagessumme 70+20
    assert res["yesterday"]["ampel"] == "🟡"          # 60–119 min


def test_daylight_as_of_yesterday_is_exact_calendar_day_not_next_earlier():
    """Lücke am Vortag: yesterday=None statt "nächst-früherer" Tag (25.)."""
    m = _merged(_metric("time_in_daylight", "min", [
        ("2026-06-25 12:00:00 +0200", 130),
        ("2026-06-28 09:00:00 +0200", 35),
    ]))
    res = DS.daylight_minutes(m, as_of="2026-06-28")
    assert res["today"]["day"] == "2026-06-28"
    assert res["today"]["ampel"] == "🟠"              # 30–59 min
    assert res["yesterday"] is None                   # 27. fehlt → None, NICHT der 25.


def test_daylight_without_as_of_keeps_legacy_last_day_semantics():
    """Ohne as_of bleibt das alte Verhalten (letzter Datentag + nächst-früherer)."""
    m = _merged(_metric("time_in_daylight", "min", [
        ("2026-06-25 12:00:00 +0200", 130),
        ("2026-06-27 12:00:00 +0200", 70),
    ]))
    res = DS.daylight_minutes(m)
    assert res["today"]["day"] == "2026-06-27"
    assert res["yesterday"]["day"] == "2026-06-25"    # next-earlier erlaubt ohne as_of


# ---------------------------------------------------------------- audio: Tag-Shift
def test_audio_as_of_pins_exact_days():
    m = _merged(_metric("environmental_audio_exposure", "dBASPL", [
        ("2026-06-27 10:00:00 +0200", 70.0),
        ("2026-06-27 20:00:00 +0200", 90.0),
    ]))
    res = DS.audio_context(m, as_of="2026-06-28")
    assert res["today"] is None                       # 28. ohne Punkte → None
    assert res["yesterday"]["day"] == "2026-06-27"
    assert res["yesterday"]["peak"] == 90.0
    assert res["yesterday"]["hint"] == "laut"         # ≥88 dB


# ---------------------------------------------------------------- sleep_efficiency: as_of
def test_sleep_efficiency_as_of_excludes_future_records():
    sleep = {
        "name": "sleep_analysis", "units": "hr",
        "data": [
            {"date": "2026-06-28 06:30:00 +0200", "totalSleep": 7.0, "awake": 0.5},
            {"date": "2026-06-29 07:00:00 +0200", "totalSleep": 4.0, "awake": 4.0},
        ],
    }
    m = DS._load({"data": {"metrics": [sleep]}})
    res = DS.sleep_efficiency(m, as_of="2026-06-28")
    assert res["efficiency"] == pytest.approx(93.3, abs=0.1)   # 7.0/7.5, NICHT die 50% von morgen
    assert res["ampel"] == "🟢"
    res_no = DS.sleep_efficiency(m)                             # ohne as_of: jüngster Record
    assert res_no["efficiency"] == pytest.approx(50.0, abs=0.1)


def test_sleep_efficiency_prefers_real_asleep_inbed_fields():
    sleep = {
        "name": "sleep_analysis", "units": "hr",
        "data": [{"date": "2026-06-28 06:30:00 +0200",
                  "totalSleep": 7.0, "awake": 2.0, "asleep": 6.8, "inBed": 8.0}],
    }
    m = DS._load({"data": {"metrics": [sleep]}})
    res = DS.sleep_efficiency(m, as_of="2026-06-28")
    assert res["asleep_h"] == 6.8 and res["inbed_h"] == 8.0     # echte Felder gewinnen
    assert res["efficiency"] == pytest.approx(85.0, abs=0.1)


# ---------------------------------------------------------------- wrist_temp: as_of
def test_wrist_temp_as_of_excludes_future_and_builds_prior_baseline():
    pts = [(f"2026-06-{d:02d} 04:00:00 +0200", 35.0) for d in range(22, 28)]
    pts += [("2026-06-28 04:00:00 +0200", 35.2), ("2026-06-29 04:00:00 +0200", 36.5)]
    m = _merged(_metric("apple_sleeping_wrist_temperature", "degC", pts))
    res = DS.wrist_temp(m, as_of="2026-06-28")
    assert res["latest"] == 35.2                       # 29. (Zukunft) ausgefiltert
    assert res["baseline"] == 35.0
    assert res["deviation"] == pytest.approx(0.2)
    assert res["flag"] is False and res["baseline_ok"] is True
    res_no = DS.wrist_temp(m)                          # ohne as_of: 36.5 → Flag feuert
    assert res_no["latest"] == 36.5 and res_no["flag"] is True


# ---------------------------------------------------------------- latest_reading: as_of
def test_latest_reading_as_of_caps_at_reference_day():
    m = _merged(_metric("vo2_max", "mL/min·kg", [
        ("2026-06-20 10:00:00 +0200", 36.0),
        ("2026-06-29 10:00:00 +0200", 37.5),
    ]))
    assert DS.latest_reading(m, "vo2_max", as_of="2026-06-28") == {
        "value": 36.0, "date": "2026-06-20"}
    assert DS.latest_reading(m, "vo2_max")["value"] == 37.5


# ---------------------------------------------------------------- water: Tagessumme
def test_dietary_water_is_day_sum_not_last_reading():
    m = _merged(_metric("dietary_water", "mL", [
        ("2026-06-27 09:00:00 +0200", 500),
        ("2026-06-28 08:00:00 +0200", 250),
        ("2026-06-28 12:00:00 +0200", 300),
        ("2026-06-28 18:00:00 +0200", 450),
    ]))
    assert DS.dietary_water(m, as_of="2026-06-28") == 1000.0   # Summe, nicht 450
    assert DS.dietary_water(m, as_of="2026-06-27") == 500.0
    assert DS.dietary_water(m) == 1000.0                        # Default = letzter Tag


# ---------------------------------------------------------------- energy: kJ/kcal-Autodetect
def test_energy_factor_autodetects_units():
    kj = _merged(_metric("dietary_energy", "kJ", [("2026-06-27 12:00:00 +0200", 4184)]))
    kcal = _merged(_metric("dietary_energy", "kcal", [("2026-06-27 12:00:00 +0200", 1000)]))
    none = _merged(_metric("dietary_energy", None, [("2026-06-27 12:00:00 +0200", 4184)]))
    assert DS._energy_factor(kj) == pytest.approx(1 / 4.184)
    assert DS._energy_factor(kcal) == 1.0
    assert DS._energy_factor(none) == pytest.approx(1 / 4.184)  # HAE-Default kJ


def test_dietary_macros_exact_day_and_kcal_conversion():
    m = _merged(
        _metric("protein", "g", [
            ("2026-06-27 12:00:00 +0200", 100),
            ("2026-06-27 19:00:00 +0200", 50),
        ]),
        _metric("dietary_energy", "kJ", [("2026-06-27 12:00:00 +0200", 8368)]),
    )
    res = DS.dietary_macros(m, as_of="2026-06-28")
    assert res["today"] is None                        # 28. nicht geloggt → None, NIE 0
    assert res["yesterday"]["protein_g"] == 150.0      # Meal-Summen je Tag
    assert res["yesterday"]["kcal"] == pytest.approx(2000.0, abs=0.1)  # 8368 kJ → kcal
    assert res["logged_days"] == ["2026-06-27"]


def test_dietary_macros_kcal_units_not_double_converted():
    m = _merged(_metric("dietary_energy", "kcal", [("2026-06-27 12:00:00 +0200", 2000)]))
    res = DS.dietary_macros(m, as_of="2026-06-28")
    assert res["yesterday"]["kcal"] == 2000.0          # kein 4,184×-Fehler


# ---------------------------------------------------------------- all_signals: Vortag-Nachzug
def test_all_signals_autoloads_missing_yesterday_file(tmp_path):
    """Nur die Heute-Datei übergeben → Vortag wird aus <data_dir> nachgeladen."""
    today_f = tmp_path / "HealthAutoExport-2026-06-28.json"
    y_f = tmp_path / "HealthAutoExport-2026-06-27.json"
    today_f.write_text(json.dumps(_hae(
        _metric("time_in_daylight", "min", [("2026-06-28 12:00:00 +0200", 45)]))),
        encoding="utf-8")
    y_f.write_text(json.dumps(_hae(
        _metric("time_in_daylight", "min", [("2026-06-27 12:00:00 +0200", 125)]))),
        encoding="utf-8")
    sig = DS.all_signals(str(today_f), as_of="2026-06-28")
    assert sig["daylight"]["today"]["minutes"] == 45
    assert sig["daylight"]["yesterday"] == {
        "day": "2026-06-27", "minutes": 125, "ampel": "🟢"}   # nachgeladen, nicht None


def test_all_signals_missing_yesterday_file_is_nonfatal(tmp_path):
    today_f = tmp_path / "HealthAutoExport-2026-06-28.json"
    today_f.write_text(json.dumps(_hae(
        _metric("time_in_daylight", "min", [("2026-06-28 12:00:00 +0200", 45)]))),
        encoding="utf-8")
    sig = DS.all_signals(str(today_f), as_of="2026-06-28")    # kein 27er-File → kein Crash
    assert sig["daylight"]["today"]["minutes"] == 45
    assert sig["daylight"]["yesterday"] is None
