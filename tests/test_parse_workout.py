"""parse_workout.py — Runna-Soll-Ist-Parser: pure Helfer + Mismatch-Kontrakt (PR-4).

Kein binäres FIT nötig: reconstruct_prescription()/_compliance()/format_table()
laufen gegen einen fitparse-Fake bzw. gebaute Ergebnis-Dicts.
"""

import parse_workout as pw


class _Field:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class _Msg:
    def __init__(self, d):
        self._d = d

    def __iter__(self):
        return iter(_Field(k, v) for k, v in self._d.items())


class _FakeFit:
    def __init__(self, workouts=None, steps=None, laps=None):
        self._m = {"workout": [_Msg(d) for d in (workouts or [])],
                   "workout_step": [_Msg(d) for d in (steps or [])],
                   "lap": [_Msg(d) for d in (laps or [])]}

    def get_messages(self, kind):
        return self._m.get(kind, [])


def test_reconstruct_prescription_expands_repeats():
    steps = [
        {"message_index": 0, "intensity": 2, "duration_type": "time",
         "duration_time": 600, "target_type": None, "wkt_step_name": "Warmup"},
        {"message_index": 1, "intensity": 0, "duration_type": "distance",
         "duration_distance": 1000, "target_type": "speed",
         "custom_target_speed_low": 2.2, "custom_target_speed_high": 2.6,
         "wkt_step_name": "Rep"},
        {"message_index": 2, "intensity": 1, "duration_type": "time",
         "duration_time": 120, "target_type": None, "wkt_step_name": "Rest"},
        {"message_index": 3, "duration_type": "repeat_until_steps_cmplt",
         "duration_step": 1, "repeat_steps": 3},
    ]
    name, flat = pw.reconstruct_prescription(
        _FakeFit(workouts=[{"wkt_name": "K1000er"}], steps=steps))
    assert name == "K1000er"
    # Warmup + (Rep+Rest) einmal im Vorwärtslauf + 2 weitere Wiederholungen = 7
    assert len(flat) == 7
    assert [s["name"] for s in flat].count("Rep") == 3


def test_compliance_band_logic():
    band = ("pace_band", 380.0, 420.0)      # 6:20–7:00
    assert pw._compliance(400.0, band) == "✅ im Band"
    assert pw._compliance(425.0, band).startswith("🟡")     # knapp (±5 %)
    assert pw._compliance(500.0, band) == "❌ langsamer"
    assert pw._compliance(300.0, band) == "❌ schneller"
    assert pw._compliance(None, band) == "—"


def _res(mismatch):
    rows = [{"lap": 0, "phase": "Rep", "intensity": "active",
             "soll": "6:20/km–7:00/km", "ist": "6:30/km", "hr": 150,
             "dist": 1000, "comp": "✅ im Band"}]
    return {"name": "K1000er", "structured": True, "prescription": [], "laps": [],
            "rows": rows, "lap_count": 5 if mismatch else 1,
            "step_count": 1, "lap_step_mismatch": mismatch,
            "mismatch_note": ("⚠️ 1 Vorschrift-Steps vs 5 Ist-Laps — Index-Zuordnung "
                              "ab der Abweichung potenziell verschoben, "
                              "Compliance-Tabelle mit Vorsicht lesen." if mismatch else None),
            "manual": False}


def test_format_table_surfaces_mismatch_warning():
    md = pw.format_table(_res(mismatch=True))
    assert "⚠️" in md and "potenziell verschoben" in md


def test_format_table_clean_run_has_no_warning():
    md = pw.format_table(_res(mismatch=False))
    assert "potenziell verschoben" not in md
