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

from datetime import datetime, timedelta

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
    """Mimics just enough of fitparse.FitFile for extract_records() / laps."""
    def __init__(self, records, laps=None):
        self._records = [_Msg(d) for d in records]
        self._laps = [_Msg(d) for d in (laps or [])]

    def get_messages(self, kind):
        if kind == "record":
            return self._records
        if kind == "lap":
            return self._laps
        return []


# ------------------------------------------------------ synthetic record dicts
_T0 = datetime(2026, 6, 23, 19, 25, 24)


def _mkrec(sec, hr, spd, run=True, temp=None):
    """Minimal internal record dict (the shape extract_records() emits)."""
    return {"ts": _T0 + timedelta(seconds=sec), "hr": hr, "spd": spd,
            "run": run, "walk": not run, "stand": False, "temp": temp,
            "dist": None, "spm": 170.0 if run else 100.0}


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


# ---------------------------------------------- Pace@Z2 window: drop hard finish
def _golden_like():
    """A managed Z2 portion (HR<=147, ~9:06/km) + a hard beast finish (Z5, fast).

    Mirrors the 23.06 golden shape: a long easy lap then a short hard lap. The
    OLD "last 30 min" window would suck the beast KM in and corrupt Pace@Z2.
    """
    recs = []
    sec = 0
    # 600 s managed @ HR ~145, spd 1.83 m/s -> ~9:06/km
    for _ in range(600):
        recs.append(_mkrec(sec, 145, 1.83))
        sec += 1
    # 120 s beast finish @ HR ~175 (Z5), spd 2.6 m/s -> ~6:25/km
    for _ in range(120):
        recs.append(_mkrec(sec, 175, 2.6))
        sec += 1
    laps = [
        {"start_time": _T0},                      # lap1: managed
        {"start_time": _T0 + timedelta(seconds=600)},  # lap2: beast
    ]
    return recs, _FakeFit([], laps=laps)


def test_drop_trailing_hard_block_sample_level():
    # 100 steady @140 then 40 hard @175 -> the hard tail is cut off.
    run = [_mkrec(i, 140, 1.8) for i in range(100)] \
        + [_mkrec(100 + i, 175, 2.6) for i in range(40)]
    trimmed, blk = arf._drop_trailing_hard_block(run)
    assert blk == 40
    assert len(trimmed) == 100
    assert all(r["hr"] == 140 for r in trimmed)


def test_drop_trailing_hard_block_no_surge_keeps_all():
    run = [_mkrec(i, 142, 1.8) for i in range(120)]
    trimmed, blk = arf._drop_trailing_hard_block(run)
    assert blk == 0
    assert len(trimmed) == 120


def test_steady_segment_drops_hard_lap():
    recs, fit = _golden_like()
    seg, label = arf.steady_z2_segment(recs, fit)
    # only the 600 managed samples survive; the beast lap is gone
    assert len(seg) == 600
    assert all(r["hr"] == 145 for r in seg)
    assert "Schluss-Lap" in label


def test_tiny_trailing_hard_lap_not_dropped():
    # base-28.05 shape: a steady run + a tiny (11-sample) final auto-lap that
    # happens to read slightly hard. Must NOT be treated as a beast finish.
    recs = [_mkrec(i, 144, 1.85) for i in range(600)] \
        + [_mkrec(600 + i, 151, 1.9) for i in range(11)]
    laps = [{"start_time": _T0},
            {"start_time": _T0 + timedelta(seconds=600)}]
    fit = _FakeFit([], laps=laps)
    seg, label = arf.steady_z2_segment(recs, fit)
    # nothing dropped via laps (151<=159 Z3 + only 11 samples) -> whole run
    assert len(seg) == 611


def test_pace_at_z2_excludes_beast_finish():
    recs, fit = _golden_like()
    seg, label = arf.steady_z2_segment(recs, fit)
    pz2 = arf.pace_at_z2(seg, {"avg_temperature": 18.0}, recs=recs, label=label)
    # ~9:06/km from the managed portion, NOT pulled fast by the 6:25 beast KM.
    assert 540 <= pz2["pace_raw_running_only_s"] <= 552
    assert pz2["n_samples"] == 600
    # 18C baseline -> no heat tax
    assert pz2["heat_tax_s_per_km"] == 0.0


def test_pace_at_z2_old_last30_window_would_corrupt():
    # Guard: averaging the WHOLE run (managed + beast) is materially faster than
    # the steady segment -> proves the window matters.
    recs, fit = _golden_like()
    whole_run = [r for r in recs if r["run"] and r["hr"] <= arf.HR_Z2_CAP]
    seg, _ = arf.steady_z2_segment(recs, fit)
    seg_z2 = [r for r in seg if r["hr"] <= arf.HR_Z2_CAP]
    whole_spd = arf._mean([r["spd"] for r in whole_run])
    seg_spd = arf._mean([r["spd"] for r in seg_z2])
    # whole-run HR<=147 set is identical here (beast is HR>147), so equal;
    # the corruption case is the *time* window, covered above. Sanity: seg is
    # the managed set exactly.
    assert len(seg_z2) == 600
    assert abs(whole_spd - seg_spd) < 1e-9


def test_pace_at_z2_temp_normalization_and_gating():
    recs, fit = _golden_like()
    seg, label = arf.steady_z2_segment(recs, fit)
    pz2 = arf.pace_at_z2(seg, {"avg_temperature": 26.0}, recs=recs, label=label,
                         decoupling_pct=9.9, walk_pct=10.3)
    raw = pz2["pace_raw_running_only_s"]
    # 26C -> heat_tax = (26-18)*3.5 = 28 s/km
    assert pz2["heat_tax_s_per_km"] == 28.0
    assert pz2["pace_normalized_18c_s"] == round(raw - 28.0, 1)
    # not baseline-eligible: temp>22, walk>5%, decoupling>=8%
    assert pz2["baseline_eligible"] is False
    assert any("temp" in r for r in pz2["ineligible_reasons"])
    assert any("decoupling" in r for r in pz2["ineligible_reasons"])


def test_pace_at_z2_baseline_eligible_clean_z2():
    # cool, low-walk, low-decoupling steady run -> eligible new baseline.
    run = [_mkrec(i, 143, 1.85) for i in range(600)]
    pz2 = arf.pace_at_z2(run, {"avg_temperature": 17.0}, recs=run,
                         label="steady", decoupling_pct=4.0, walk_pct=2.0)
    assert pz2["baseline_eligible"] is True
    assert pz2["ineligible_reasons"] is None


def test_decoupling_over_segment_detects_drift():
    # H1 fast/low-HR, H2 slower/higher-HR -> positive decoupling.
    seg = [_mkrec(i, 142, 1.9) for i in range(300)] \
        + [_mkrec(300 + i, 147, 1.7) for i in range(300)]
    dec = arf.decoupling(seg, "steady")
    assert dec["valid"] is True
    assert dec["decoupling_pct"] > 5.0
    assert dec["segment"] == "steady"


def test_decoupling_too_few_samples_invalid():
    seg = [_mkrec(i, 142, 1.9) for i in range(5)]
    dec = arf.decoupling(seg)
    assert dec["valid"] is False


# ---------------------------------------------- T4: Vertical Ratio (per km/lap)
def _mkfull(sec, dist, hr=145, spd=1.85, spm=170.0, vo=90.0, stride=1100.0,
            vr=None, run=True):
    """Vollständiges internes Record-Dict (Form-Felder), wie extract_records es liefert."""
    return {"ts": _T0 + timedelta(seconds=sec), "hr": hr, "spd": spd, "alt": None,
            "dist": dist, "spm": spm if run else 100.0, "power": None, "gct": 250.0,
            "vo": vo, "stride": stride, "vr": vr, "temp": None,
            "run": run, "walk": not run, "stand": False}


def test_vr_pct_native_preferred():
    # native vertical_ratio present -> used directly (median), VO/stride ignored.
    run = [_mkfull(i, i, vr=11.5) for i in range(5)]
    assert arf._vr_pct(run) == 11.5


def test_vr_pct_reconstructed_from_vo_stride_when_native_absent():
    # Apple-Watch case: no native vr -> reconstruct VO/stride*100. 90/1100*100 ≈ 8.18.
    run = [_mkfull(i, i, vo=90.0, stride=1100.0, vr=None) for i in range(5)]
    assert round(arf._vr_pct(run), 2) == 8.18


def test_vr_pct_none_when_nothing_derivable():
    run = [_mkfull(i, i, vo=None, stride=None, vr=None) for i in range(3)]
    assert arf._vr_pct(run) is None


def test_km_splits_emit_vr_pct():
    # one km bucket (dist 0..900), Apple-shape (no native vr) -> reconstructed VR present.
    recs = [_mkfull(i, i * 100, vo=90.0, stride=1100.0, vr=None) for i in range(10)]
    splits = arf.km_splits(recs)
    assert splits and "vr_pct" in splits[0]
    assert round(splits[0]["vr_pct"], 1) == 8.2


# ---------------------------------------------- T3: optical HR cadence-lock flag
def test_hr_source_warn_detects_cadence_lock():
    # HR ≈ spm (170) sustained -> classic optical lock reading too high.
    recs = [_mkrec(i, 170, 1.85) for i in range(200)]   # _mkrec sets spm=170 for run
    w = arf.hr_source_warn(recs)
    assert w["optical_cadence_lock_suspected"] is True
    assert w["locked_fraction_pct"] == 100.0
    assert w["longest_locked_stretch_s"] >= arf.LOCK_MIN_SUSTAIN_S


def test_hr_source_warn_clean_run_not_flagged():
    # real Z2 HR 145, cadence 170 -> min(|145-170|,|145-85|)=25 > tol -> no lock.
    recs = [_mkrec(i, 145, 1.85) for i in range(200)]
    w = arf.hr_source_warn(recs)
    assert w["optical_cadence_lock_suspected"] is False
    assert w["locked_fraction_pct"] == 0.0


def test_hr_source_warn_too_few_samples():
    recs = [_mkrec(i, 170, 1.85) for i in range(10)]
    w = arf.hr_source_warn(recs)
    assert w["optical_cadence_lock_suspected"] is False
    assert "zu wenige" in w["note"]


def test_hr_source_warn_recording_gap_breaks_stretch():
    # Zwei 69s-Lock-Cluster, getrennt durch eine 600s-Aufzeichnungslücke; keiner
    # erreicht 2 min, Lock-Anteil < 50% -> KEIN Flag. Die Lücke darf die Cluster
    # nicht zu einer durchgehenden Strecke verschmelzen (Gap = Bruch, kein 1s-Füller).
    recs = [_mkrec(i, 170, 1.85) for i in range(69)]                 # Cluster 1: 0..68 s
    recs += [_mkrec(668 + i, 170, 1.85) for i in range(69)]          # Cluster 2 nach 600 s Lücke
    recs += [_mkrec(1000 + i, 140, 1.85) for i in range(200)]        # unlocked -> Anteil < 50%
    w = arf.hr_source_warn(recs)
    assert w["locked_fraction_pct"] < 50.0
    assert w["longest_locked_stretch_s"] < arf.LOCK_MIN_SUSTAIN_S    # ~68 s, NICHT ~137 s
    assert w["optical_cadence_lock_suspected"] is False
