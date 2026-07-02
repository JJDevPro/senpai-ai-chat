"""hrv_heatmap.py — Multi-Tag-HRV-Heatmap (Stunde × Wochentag).

Prüft die deterministische Matrix-Bildung aus gecachten HAE-Tagesdateien:
Nacht→Aufwach-Tag-Zuordnung (sleepEnd==Tag), Vor-Mitternacht-Punkte aus der
Vortags-Datei, Nacht-Sortierung der Stunden-Achse (Abend vor Morgen) und die
progressive "N/M Nächte"-Ehrlichkeit (fehlende Tage = "—", kein Nachziehen).

DATA-FREE: synthetische Tagesdateien mit bekannten Stunden-Werten.
"""

import json

import hrv_heatmap as HM


# ---------------------------------------------------------------- fixtures
def _write_day(tmp_path, day, metrics):
    p = tmp_path / f"HealthAutoExport-{day}.json"
    p.write_text(json.dumps({"data": {"metrics": metrics}}), encoding="utf-8")
    return p


def _hrv(points):
    return {"name": "heart_rate_variability", "units": "ms",
            "data": [{"date": d, "qty": q} for d, q in points]}


def _sleep(sleep_start, sleep_end):
    return {"name": "sleep_analysis", "units": "hr",
            "data": [{"date": sleep_end, "sleepStart": sleep_start,
                      "sleepEnd": sleep_end, "totalSleep": 6.0}]}


def _cells(res, day):
    for ds, _wd, c in res["columns"]:
        if ds == day:
            return c
    raise AssertionError(f"Spalte {day} fehlt")


# ---------------------------------------------------------------- build()
def test_build_assigns_nights_to_wake_day_with_known_ampeln(tmp_path):
    _write_day(tmp_path, "2026-06-28", [
        _sleep("2026-06-28 00:30:00 +0200", "2026-06-28 06:30:00 +0200"),
        _hrv([("2026-06-28 03:05:00 +0200", 55),
              ("2026-06-28 04:10:00 +0200", 65)]),
    ])
    _write_day(tmp_path, "2026-06-27", [
        _sleep("2026-06-27 00:00:00 +0200", "2026-06-27 06:00:00 +0200"),
        _hrv([("2026-06-27 02:00:00 +0200", 48)]),
    ])
    res = HM.build("2026-06-28", str(tmp_path), days=7)
    assert res["found"] == 2 and len(res["columns"]) == 7
    assert [ds for ds, _, _ in res["columns"]][-1] == "2026-06-28"   # alt → neu
    c28 = _cells(res, "2026-06-28")
    assert c28[3] == (55, "🟡") and c28[4] == (65, "🟢")             # Ampel-Bänder 50/60
    assert _cells(res, "2026-06-27")[2] == (48, "🔴")
    assert _cells(res, "2026-06-26") is None                          # nicht gecached → leer


def test_build_loads_pre_midnight_points_from_previous_days_file(tmp_path):
    """Die Vor-Mitternacht-HRV einer Nacht steht in der DATEI DES VORTAGS —
    build() lädt deshalb auch den Tag vor dem ältesten Fenster-Tag."""
    _write_day(tmp_path, "2026-06-26", [
        _hrv([("2026-06-26 23:30:00 +0200", 58)]),   # gehört zur Nacht → 27.
    ])
    _write_day(tmp_path, "2026-06-27", [
        _sleep("2026-06-26 23:00:00 +0200", "2026-06-27 06:00:00 +0200"),
        _hrv([("2026-06-27 03:00:00 +0200", 62)]),
    ])
    res = HM.build("2026-06-28", str(tmp_path), days=2)   # Fenster = 27.+28., lädt ab 26.
    c27 = _cells(res, "2026-06-27")
    assert c27[23] == (58, "🟡")                          # Vor-Mitternacht-Stunde da
    assert c27[3] == (62, "🟢")


def test_build_no_fallback_night_duplication(tmp_path):
    """Kein sleepEnd==Tag → Spalte leer; dieselbe Nacht darf NIE zwei Spalten füllen."""
    _write_day(tmp_path, "2026-06-28", [
        _sleep("2026-06-28 00:30:00 +0200", "2026-06-28 06:30:00 +0200"),
        _hrv([("2026-06-28 03:05:00 +0200", 55)]),
    ])
    # 27er-Datei existiert (present), hat aber KEINE Nacht mit sleepEnd==27.
    _write_day(tmp_path, "2026-06-27", [_hrv([("2026-06-27 14:00:00 +0200", 99)])])
    res = HM.build("2026-06-28", str(tmp_path), days=3)
    assert _cells(res, "2026-06-27") is None
    assert res["found"] == 1


def test_build_returns_none_without_any_cached_files(tmp_path):
    assert HM.build("2026-06-28", str(tmp_path), days=7) is None


# ---------------------------------------------------------------- Achsen-Ordnung
def test_night_order_sorts_evening_hours_before_morning():
    assert sorted([0, 23, 3, 12], key=HM._night_order) == [12, 23, 0, 3]


# ---------------------------------------------------------------- render_md()
def test_render_md_shows_coverage_gaps_and_values(tmp_path):
    _write_day(tmp_path, "2026-06-28", [
        _sleep("2026-06-28 00:30:00 +0200", "2026-06-28 06:30:00 +0200"),
        _hrv([("2026-06-28 03:05:00 +0200", 55)]),
    ])
    md = HM.render_md(HM.build("2026-06-28", str(tmp_path), days=7))
    assert "1/7 Nächte" in md
    assert "| 03:00 |" in md and "🟡55" in md
    assert "—" in md                                   # fehlende Nächte ehrlich als Strich
    assert "Backfill" in md                            # Hinweis statt stillem Loch


def test_render_md_handles_zero_hrv_nights(tmp_path):
    _write_day(tmp_path, "2026-06-28", [_hrv([("2026-06-28 14:00:00 +0200", 80)])])  # nur Tag-Punkt
    md = HM.render_md(HM.build("2026-06-28", str(tmp_path), days=7))
    assert "Keine gecachten Nächte" in md
