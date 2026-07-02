"""Golden-/Snapshot-Tests (PR-7) — der Kern der Reproduzierbarkeits-Garantie.

Jede Engine wird EINMAL end-to-end auf einem synthetischen, handgerechneten
Input gefahren und der komplette Aggregat-Report strukturell + numerisch
gepinnt: gleiche Daten → gleiche Zahlen, gleiche Ampeln, gleiches Gate.
Bewegt sich ein Pin, ist das eine BEWUSSTE Engine-Änderung (Re-Pin mit
Begründung), nie ein Unfall.

Abgedeckt:
  1. FIT-Engine  — analyze_run_fit.assemble() auf einem Fake-Fit (voller Report).
  2. Daily-Kette — slice_hae_day → safety_gate → readiness auf hae_synthetic.json.
  3. Gym-Engine  — analyze_gym.analyze() Voll-Modus.
  4. Banister    — Multi-Step-Inkrementalpfad drift-frei über eine ganze Woche.
"""

import json
from datetime import datetime, timedelta


import analyze_gym as ag
import analyze_run_fit as arf
import banister as bb
import readiness as rd
import safety_gate as sg
import slice_hae_day as sl


# ════════════════════════════════════════════════════════════════════════
#  1) FIT-Engine-Golden (Fake-Fit → kompletter Report)
# ════════════════════════════════════════════════════════════════════════
class _Field:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class _Msg:
    def __init__(self, d):
        self.fields = [_Field(k, v) for k, v in d.items()]


class _FakeFit:
    def __init__(self, records, laps=None, session=None, workouts=None):
        self._m = {"record": [_Msg(d) for d in records],
                   "lap": [_Msg(d) for d in (laps or [])],
                   "session": [_Msg(session)] if session else [],
                   "workout": [_Msg(d) for d in (workouts or [])]}

    def get_messages(self, kind):
        return self._m.get(kind, [])


def _golden_fit():
    """20 min Z2-Lauf @3,0 m/s, 1-Hz-Records, Kadenz 85 (=170 spm), HR 140,
    GCT 250, VO 80, Stride 800, Temp 20 °C, Höhe flach — alles handrechenbar."""
    t0 = datetime(2026, 6, 28, 7, 0, 0)
    recs = []
    for i in range(1200):
        recs.append({
            "timestamp": t0 + timedelta(seconds=i),
            "heart_rate": 140,
            "cadence": 85,
            "enhanced_speed": 3.0,
            "enhanced_altitude": 300.0,
            "distance": 3.0 * i,
            "stance_time": 250.0,
            "vertical_oscillation": 80.0,
            "step_length": 800.0,
            "temperature": 20,
        })
    session = {"sport": "running", "sub_sport": "generic",
               "total_distance": 3600.0, "total_timer_time": 1200.0,
               "avg_temperature": 21, "total_calories": 400,
               "total_ascent": 0, "total_descent": 0}
    return _FakeFit(recs, session=session)


def test_golden_fit_engine_full_report():
    res = arf.assemble(_golden_fit(), "2026-06-28", fit_path="golden.fit")
    # Struktur-Pin: der volle Aggregat-Kontrakt
    assert sorted(res.keys()) == sorted([
        "ok", "schema_version", "meta", "summary", "splits_km", "splits_lap",
        "hr_zones", "hr_source_warn", "run_form", "best_values",
        "sprint_last_60s", "decoupling", "pace_at_z2", "v3_ampeln", "topography"])
    assert res["ok"] is True and res["schema_version"] == "3.14"

    s = res["summary"]
    assert s["distance_km"] == 3.6
    assert s["duration_s"] == 1200
    assert s["pace_avg_running_only"] == "5:33/km"      # 3,0 m/s
    assert s["hr_avg"] == 140 and s["hr_max"] == 140
    assert s["cadence_avg_running_spm"] == 170.0
    assert s["walk_pct"] == 0.0 and s["stand_pct"] == 0.0

    z = res["hr_zones"]
    assert z["pct"]["Z2"] == 100.0 and z["z4_z5_pct"] == 0.0

    f = res["run_form"]
    assert f["gct_median_ms"] == 250 and f["stride_median_mm"] == 800
    assert f["vr_pct_record_weighted"] == 10.0          # 80/800×100

    pz = res["pace_at_z2"]
    assert pz["pace_raw_running_only"] == "5:33/km"
    assert pz["start_temp_c"] == 20.0                   # Records-START, nicht avg 21
    assert pz["temp_source"] == "records_start"
    assert pz["heat_tax_s_per_km"] == 7.0               # (20−18)×3,5
    assert pz["pace_normalized_18c"] == "5:26/km"       # 333,3−7,0 s

    amp = res["v3_ampeln"]
    assert amp["cadence"]["ampel"] == "🟡"              # 170 in 166–174
    assert amp["gct"]["ampel"] == "🟢"                  # 250 < 260
    assert amp["vertical_ratio"]["ampel"] == "🟡"       # 10,0 = obere 🟡-Kante (8–10)
    assert amp["easy_hr_compliance"]["ampel"] == "🟢"   # Ø140 ≤ 147
    # EF = 3,0·60/140 = 1,286 → 🔴 (<1,40)
    assert amp["ef"]["value"] == 1.286 and amp["ef"]["ampel"] == "🔴"
    # 20 min < 45 min → Decoupling methodisch nicht aussagekräftig
    assert amp["decoupling"]["valid_steady_state"] is False

    best = res["best_values"]
    assert best["fastest_km"]["pace"] == "5:33/km"
    assert best["top_speed"]["pace"] == "5:33/km"
    assert res["decoupling"]["decoupling_pct"] == 0.0   # perfekt konstant

    # Determinismus: zweiter Lauf, identisches Ergebnis
    res2 = arf.assemble(_golden_fit(), "2026-06-28", fit_path="golden.fit")
    assert json.dumps(res, sort_keys=True, default=str) == \
        json.dumps(res2, sort_keys=True, default=str)


# ════════════════════════════════════════════════════════════════════════
#  2) Daily-Check-Ketten-Golden (slice → gate → readiness)
# ════════════════════════════════════════════════════════════════════════
def test_golden_daily_chain(hae_path):
    metrics = sl._merge(sl._load_metrics(str(hae_path)))
    sliced = sl.slice_day(metrics, "2026-06-28")

    # Slice-Pin (Fixture-README: raw-Punkte 19/120/65/66/70/71 → Ø 68,5 → 68)
    assert sliced["hrv_night"]["avg"] == 68
    gate = sg.evaluate_gate(sliced)
    assert gate["gate"] == "v3_safety" and gate["training_allowed"] is True
    assert gate["roast_allowed"] is True

    readiness = rd.compute_readiness({
        "hrv_baseline": {"status": "balanced", "median": 55.0, "n_days": 60},
        "daily": sliced,
        "banister": {"tsb": 3.0, "ctl": 45.0, "atl": 42.0},
        "safety_gate": gate,
        "sentinel": {"alerts": [], "warn_count": 0, "rhr_deviation": 0.0},
        "rhr_deviation": None,
    })
    assert readiness["band"] in ("high", "moderate")
    assert readiness["meta"]["safety_gate_level"] == gate["level"]
    assert readiness["meta"]["training_allowed"] is True

    # Determinismus über die ganze Kette
    sliced2 = sl.slice_day(sl._merge(sl._load_metrics(str(hae_path))), "2026-06-28")
    r2 = rd.compute_readiness({
        "hrv_baseline": {"status": "balanced", "median": 55.0, "n_days": 60},
        "daily": sliced2,
        "banister": {"tsb": 3.0, "ctl": 45.0, "atl": 42.0},
        "safety_gate": sg.evaluate_gate(sliced2),
        "sentinel": {"alerts": [], "warn_count": 0, "rhr_deviation": 0.0},
        "rhr_deviation": None,
    })
    assert r2["score"] == readiness["score"]


def test_golden_daily_chain_hrv_pin(hae_path):
    """Der Nacht-HRV-Pin separat (Fixture: raw-Punkte 19/120/65/66/70/71)."""
    metrics = sl._merge(sl._load_metrics(str(hae_path)))
    night = sl.slice_day(metrics, "2026-06-28")["hrv_night"]
    assert night["n"] == 6
    assert night["avg"] == round((19 + 120 + 65 + 66 + 70 + 71) / 6)   # 69
    assert night["max"] == 120                     # Tages-200er liegt AUSSERHALB
    assert night["ampel"] == "🟢"


# ════════════════════════════════════════════════════════════════════════
#  3) Gym-Engine-Golden (Voll-Modus)
# ════════════════════════════════════════════════════════════════════════
GYM_TEXT = """\
3030 - Beinpresse - 80, 85, 90, 95 kg (max)
3018 - Waden - 4× 105 kg
"""
GYM_BASELINES = "## Gym PRs\n- Beinpresse: 90 kg\n- Waden: 110 kg\n"


def _gym_csv(tmp_path):
    lines = ["ISO8601;Heart Rate (bpm);Lap"]
    for lap, (hr, minute) in enumerate([(95, 0), (120, 6), (135, 12)], start=1):
        for s2 in range(0, 120, 4):
            lines.append(f"2026-07-02T21:{minute + s2 // 60:02d}:{s2 % 60:02d}+02:00;{hr};{lap}")
    p = tmp_path / "gym.csv"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def test_golden_gym_engine(tmp_path):
    res = ag.analyze(GYM_TEXT, segments_path=_gym_csv(tmp_path),
                     baselines_text=GYM_BASELINES, as_of="2026-07-02")
    assert res["ok"] is True and res["schema_version"] == "2.0"
    assert res["segment_mapping"]["mode"] == "warmup+1:1"
    assert res["hr_baseline_for_strain"] == 95.0

    ex = {e["name"]: e for e in res["exercises"]}
    bp = ex["Beinpresse"]
    assert bp["tonnage_kg"] == 3500.0 and bp["max_kg"] == 95
    assert bp["pr_status"] == "🏆 PR"
    assert bp["hr"]["avg"] == 120.0 and bp["strain_hr_over_baseline"] == 25
    wd = ex["Waden"]
    assert wd["tonnage_kg"] == 4200.0 and wd["pr_status"] == "🟡 normal"
    assert wd["strain_hr_over_baseline"] == 40

    assert res["tonnage"]["total_kg"] == 7700.0
    assert res["tonnage"]["by_group"]["Beine"]["pct"] == 100.0
    assert res["pr"]["baseline_updates"] == [{
        "exercise": "Beinpresse", "old_kg": 90.0, "new_kg": 95.0,
        "delta_kg": 5.0, "delta_pct": 5.6}]
    assert res["bedtime"]["ampel"] == "🟢"        # Ende 21:13 ≤ 21:30

    res2 = ag.analyze(GYM_TEXT, segments_path=_gym_csv(tmp_path),
                      baselines_text=GYM_BASELINES, as_of="2026-07-02")
    assert json.dumps(res, sort_keys=True) == json.dumps(res2, sort_keys=True)


# ════════════════════════════════════════════════════════════════════════
#  4) Banister-Multi-Step-Drift (inkrementell == Vollrechnung über 1 Woche)
# ════════════════════════════════════════════════════════════════════════
def test_golden_banister_incremental_week_no_drift(trainings_csv_text):
    """Der inkrementelle Pfad (day_trimp + step) darf über einen ganzen
    Wochen-Horizont NICHT von der Vollrechnung wegdriften — sonst zeigt der
    Daily-Check je nach Pfad andere TSB-Werte (genau der Alt-Bug)."""
    from datetime import date

    start_anchor = "2026-06-21"
    anchor = bb.compute_from_sheet(trainings_csv_text, as_of=start_anchor)
    ctl, atl = anchor["ctl"], anchor["atl"]
    d = date.fromisoformat(start_anchor)
    for _ in range(7):                                  # 7 inkrementelle Schritte
        t = bb.day_trimp(trainings_csv_text, d.isoformat())
        stepped = bb.step(ctl, atl, t)
        ctl, atl = stepped["ctl"], stepped["atl"]
        d += timedelta(days=1)

    full = bb.compute_from_sheet(trainings_csv_text, as_of=d.isoformat())
    # Rundung je Schritt (1 Dezimal) darf sich über 7 Tage nicht aufschaukeln
    assert abs(ctl - full["ctl"]) <= 0.3
    assert abs(atl - full["atl"]) <= 0.3
    assert abs((ctl - atl) - full["tsb"]) <= 0.5
