"""Regression tests for analyze_run_fit.py PURE helpers (no real .fit needed).

We never synthesize a binary .fit. Instead we test the deterministic pure logic:
  * zone_of()   — the hard V3 HR-zone boundaries.
  * _pace_str() — 'M:SS/km' formatting, incl. the "8:60/km" rounding bug guard.
  * _pace_from_speed() — m/s -> sec/km.
  * extract_records() walking-filter v3.5 + cadence x2 + enhanced_* fallback,
    driven by a tiny in-memory fake that mimics the fitparse object API
    (fit.get_messages("record") -> msgs; msg.fields -> [field.name/.value]).
extract_records does NOT import fitparse, so this runs even without it installed.
"""

import analyze_run_fit as arf


# ---------------------------------------------------------------- fitparse fake
class _Field:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class _Msg:
    def __init__(self, d):
        self.fields = [_Field(k, v) for k, v in d.items()]


class _FakeFit:
    """Mimics just enough of fitparse.FitFile for extract_records()."""
    def __init__(self, records):
        self._records = [_Msg(d) for d in records]

    def get_messages(self, kind):
        return self._records if kind == "record" else []


# ---------------------------------------------------------------- zone_of (V3)
def test_zone_of_boundaries():
    assert arf.zone_of(None) is None
    assert arf.zone_of(135) == "Z1"   # <136
    assert arf.zone_of(136) == "Z2"   # 136-147
    assert arf.zone_of(147) == "Z2"
    assert arf.zone_of(148) == "Z3"   # 148-159
    assert arf.zone_of(159) == "Z3"
    assert arf.zone_of(160) == "Z4"   # 160-171
    assert arf.zone_of(171) == "Z4"
    assert arf.zone_of(172) == "Z5"   # >=172
    assert arf.zone_of(200) == "Z5"


# ---------------------------------------------------------------- pace formatting
def test_pace_str_no_8_60_bug():
    # 539.6 s/km rounds to 540 -> "9:00/km", NOT "8:60/km" (floor + sec-rounding bug).
    assert arf._pace_str(539.6) == "9:00/km"
    assert arf._pace_str(343) == "5:43/km"
    # zero-padding of the seconds field
    assert arf._pace_str(305) == "5:05/km"


def test_pace_str_invalid_inputs_are_none():
    assert arf._pace_str(0) is None
    assert arf._pace_str(None) is None
    assert arf._pace_str(-5) is None
    assert arf._pace_str(float("inf")) is None


def test_pace_from_speed():
    assert arf._pace_from_speed(2.5) == 400.0   # 1000 / 2.5
    assert arf._pace_from_speed(0) is None
    assert arf._pace_from_speed(None) is None


# ---------------------------------------------------------------- walking-filter v3.5
def test_walking_filter_classification_and_cadence_doubling():
    recs, apple = arf.extract_records(_FakeFit([
        # run: spm=(80+2)*2=164 >=140, enhanced_speed 3.5 preferred over speed 3.0.
        {"cadence": 80, "fractional_cadence": 2, "speed": 3.0,
         "enhanced_speed": 3.5, "heart_rate": 150, "distance": 100},
        # walk: spm=120 <140 AND spd 1.5 <2.0.
        {"cadence": 60, "fractional_cadence": 0, "speed": 1.5,
         "heart_rate": 120, "distance": 200},
        # stand: spm=0 AND spd 0.2 <0.5.
        {"cadence": 0, "speed": 0.2, "heart_rate": 90, "distance": 210},
        # cad 0 but moving 1.0 m/s -> NOT stand (spd>=0.5) -> walk.
        {"cadence": 0, "speed": 1.0, "heart_rate": 100, "distance": 250},
    ]))

    run, walk, stand, cad0move = recs

    # cadence x2 (FIT cadence is single-foot)
    assert run["spm"] == 164.0
    # enhanced_speed wins over speed
    assert run["spd"] == 3.5
    assert (run["run"], run["walk"], run["stand"]) == (True, False, False)

    assert walk["spm"] == 120.0
    assert (walk["run"], walk["walk"], walk["stand"]) == (False, True, False)

    assert (stand["run"], stand["walk"], stand["stand"]) == (False, False, True)

    # cad==0 but spd 1.0 >= 0.5 -> walk, not stand
    assert (cad0move["walk"], cad0move["stand"]) == (True, False)

    # at least one record carried enhanced_* -> not flagged as an Apple-Watch FIT
    assert apple is False


def test_apple_watch_fit_detected_when_no_enhanced_fields():
    _, apple = arf.extract_records(_FakeFit([
        {"cadence": 80, "fractional_cadence": 0, "speed": 3.0,
         "heart_rate": 150, "distance": 10},
    ]))
    assert apple is True


def test_speed_fallback_to_non_enhanced():
    recs, _ = arf.extract_records(_FakeFit([
        {"cadence": 80, "fractional_cadence": 0, "speed": 2.7,
         "heart_rate": 150, "distance": 10},
    ]))
    # no enhanced_speed present -> spd falls back to plain speed
    assert recs[0]["spd"] == 2.7
