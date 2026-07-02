"""analyze_gym.py — deterministische Gym-Engine (v2.0, PR-5).

Pinnt den Engine-Kontrakt: Übungs-Text-Parser (SKILL §3-Notationen),
Segment-Mapping (§5), PR-Detection + baseline_updates (§6), Tonnage/Bänder (§7),
Bedtime-Ampel (§12), Re-Entry (§11). DATA-FREE: synthetische Inputs.
"""

import json
import subprocess
import sys
from pathlib import Path

import analyze_gym as ag

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / ".claude" / "skills" / "gym-bundle-skill" / "scripts" / "analyze_gym.py"

EXERCISES = """\
3030 - Beinpresse - 80, 85, 90, 95 kg (max)
3018 - Waden - 4× 105 kg
3008 - Klappsitz - 60, 65, 70 kg (6x)
3020 - Latzug - 2× 50, 2× 55 kg
"""

BASELINES = """\
# Baselines

## Gym PRs (Stand KW26)
- Beinpresse: 90 kg
- Waden: 110 kg
- Klappsitz: 70 kg
- Latzug: 60 kg

## Andere Sektion
- Irgendwas: 999 kg
"""


# ---------------------------------------------------------------- Text-Parser (§3)
def test_parse_exercise_line_notations():
    ex = ag.parse_exercise_line("3030 - Beinpresse - 80, 85, 90, 95 kg (max)")
    assert ex["device"] == "3030" and ex["name"] == "Beinpresse"
    assert [s["weight"] for s in ex["sets"]] == [80, 85, 90, 95]
    assert all(s["reps"] == 10 for s in ex["sets"])
    assert ex["pr_claimed"] is True                     # "(max)"


def test_parse_multiplier_and_reps_override():
    ex = ag.parse_exercise_line("3018 - Waden - 2× 80, 2× 85 kg (6x)")
    assert [s["weight"] for s in ex["sets"]] == [80, 80, 85, 85]
    assert [s["reps"] for s in ex["sets"]] == [10, 10, 10, 6]   # (6x) = letzter Satz


def test_parse_line_without_device():
    ex = ag.parse_exercise_line("Beinbeuger - 45, 50 kg")
    assert ex["device"] is None and ex["name"] == "Beinbeuger"
    assert len(ex["sets"]) == 2


def test_parse_ignores_comment_notes_and_junk():
    assert ag.parse_exercise_line("") is None
    assert ag.parse_exercise_line("# Kommentar") is None
    ex = ag.parse_exercise_line("3225 - Rotation - 30, 35 kg (dual ist bequemer)")
    assert len(ex["sets"]) == 2 and ex["pr_claimed"] is False


# ---------------------------------------------------------------- Klassifikation (§4)
def test_classification_device_then_name_fallback():
    assert ag.classify_group("3030", "Beinpresse", ag.DEVICE_MAP) == "Beine"
    assert ag.classify_group(None, "Beinbeuger", ag.DEVICE_MAP) == "Beine"
    assert ag.classify_group(None, "Rotation", ag.DEVICE_MAP) == "Core"
    assert ag.classify_group("9999", "Mystery-Maschine", ag.DEVICE_MAP) == "Unklassifiziert"


# ---------------------------------------------------------------- Mapping (§5)
def _segs(n, hr0=98):
    return [{"idx": i + 1, "dur_s": 300, "hr_avg": hr0 + i * 5,
             "hr_max": hr0 + i * 5 + 20, "start": None,
             "end": f"2026-07-02T21:{10 + i:02d}:00"} for i in range(n)]


def test_mapping_warmup_plus_one_to_one():
    mapped, meta = ag.map_segments(_segs(5), 4)
    assert meta["mode"] == "warmup+1:1"
    assert meta["warmup"]["idx"] == 1
    assert [s["idx"] for s in mapped] == [2, 3, 4, 5]


def test_mapping_unmatched_does_not_guess():
    mapped, meta = ag.map_segments(_segs(9), 4)
    assert mapped is None and meta["mode"] == "unmatched"
    assert "kein sicheres" in meta["note"]


# ---------------------------------------------------------------- PR-Detection (§6)
def test_pr_detection_and_baseline_updates():
    res = ag.analyze(EXERCISES, baselines_text=BASELINES, as_of="2026-07-02")
    by_name = {e["name"]: e for e in res["exercises"]}
    assert by_name["Beinpresse"]["pr_status"] == "🏆 PR"        # 95 > 90
    assert by_name["Waden"]["pr_status"] == "🟡 normal"         # 105 < 110
    assert by_name["Klappsitz"]["pr_status"] == "🟢 PB matched"  # 70 == 70
    ups = res["pr"]["baseline_updates"]
    assert len(ups) == 1 and ups[0]["exercise"] == "Beinpresse"
    assert ups[0]["old_kg"] == 90 and ups[0]["new_kg"] == 95
    assert ups[0]["delta_pct"] == 5.6


def test_pr_section_scoping_ignores_other_sections():
    prs = ag.parse_baselines(BASELINES)
    assert "irgendwas" not in prs                        # nur der Gym-PR-Abschnitt
    assert prs["beinpresse"] == 90.0


def test_no_baseline_is_flagged_not_guessed():
    res = ag.analyze("3036 - Dip - 40, 45 kg", baselines_text=BASELINES,
                     as_of="2026-07-02")
    assert res["exercises"][0]["pr_status"] == "no_baseline"


# ---------------------------------------------------------------- Tonnage (§7)
def test_tonnage_and_band_ampeln():
    res = ag.analyze(EXERCISES, baselines_text=BASELINES, as_of="2026-07-02")
    by_name = {e["name"]: e for e in res["exercises"]}
    assert by_name["Beinpresse"]["tonnage_kg"] == 3500.0        # (80+85+90+95)*10
    assert by_name["Waden"]["tonnage_kg"] == 4200.0             # 4*105*10
    assert by_name["Klappsitz"]["tonnage_kg"] == 1670.0         # 600+650+70*6
    assert by_name["Latzug"]["tonnage_kg"] == 2100.0            # (50+50+55+55)*10
    t = res["tonnage"]
    assert t["total_kg"] == 11470.0
    # Beine (3500+4200)/11470 = 67.1 % -> knapp ÜBER dem 50–65-Band -> 🟡
    assert t["by_group"]["Beine"]["pct"] == 67.1
    assert t["by_group"]["Beine"]["ampel"] == "🟡"
    assert t["by_group"]["Core"]["band_pct"] == (8, 15)


# ---------------------------------------------------------------- Bedtime (§12)
def test_bedtime_ampel_bands():
    assert ag.bedtime_ampel("2026-07-02T21:25:00")["ampel"] == "🟢"
    assert ag.bedtime_ampel("2026-07-02T21:45:00")["ampel"] == "🟡"
    assert ag.bedtime_ampel("2026-07-02T22:15:00")["ampel"] == "🟠"
    assert ag.bedtime_ampel("2026-07-02T22:45:00")["ampel"] == "🔴"
    assert ag.bedtime_ampel(None)["ampel"] is None


# ---------------------------------------------------------------- Re-Entry (§11)
def test_reentry_rule_flags_over_target():
    res = ag.analyze("3030 - Beinpresse - 85, 92 kg", baselines_text=BASELINES,
                     as_of="2026-07-02", days_since_last=14)
    assert res["pr"]["reentry"]["active"] is True
    ex = res["exercises"][0]
    # 92 > 0.8*90=72 -> über dem Re-Entry-Ziel (Warnung, kein Lob)
    assert ex["reentry_over_target"] is True


def test_no_reentry_within_gap():
    res = ag.analyze("3030 - Beinpresse - 85 kg", baselines_text=BASELINES,
                     as_of="2026-07-02", days_since_last=3)
    assert res["pr"]["reentry"] is None


# ---------------------------------------------------------------- Segmente-CSV + CLI
def _sampling_csv(tmp_path):
    """Master-CSV-Form: 4-s-Sampling mit Lap-Spalte (2 Übungen + Warmup = 3 Laps)."""
    lines = ["ISO8601;Heart Rate (bpm);Lap"]
    for lap, (hr, minute) in enumerate([(95, 0), (120, 6), (135, 12)], start=1):
        for s in range(0, 120, 4):
            lines.append(f"2026-07-02T21:{minute + s // 60:02d}:{s % 60:02d}+02:00;{hr + (s % 8)};{lap}")
    p = tmp_path / "master.csv"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_sampling_csv_aggregated_per_lap_and_mapped(tmp_path):
    csv_path = _sampling_csv(tmp_path)
    segs = ag.read_segments(str(csv_path))
    assert len(segs) == 3
    assert segs[0]["hr_avg"] is not None and segs[0]["hr_avg"] < segs[2]["hr_avg"]
    res = ag.analyze("3030 - Beinpresse - 90 kg\n3018 - Waden - 100 kg",
                     segments_path=str(csv_path), as_of="2026-07-02")
    assert res["segment_mapping"]["mode"] == "warmup+1:1"
    ex = res["exercises"][0]
    assert ex["hr"]["avg"] is not None
    assert ex["strain_hr_over_baseline"] is not None      # Peak − Warmup-Ø
    assert res["bedtime"]["ampel"] in ("🟢", "🟡", "🟠", "🔴")


def test_cli_contract_and_failure(tmp_path):
    ex_f = tmp_path / "uebungen.txt"
    ex_f.write_text(EXERCISES, encoding="utf-8")
    out = subprocess.run([sys.executable, str(SCRIPT), "--exercises", str(ex_f),
                          "--as-of", "2026-07-02"],
                         capture_output=True, text=True, check=True)
    res = json.loads(out.stdout)
    assert res["ok"] is True and res["schema_version"] == "2.0"
    assert res["meta"]["mode"].startswith("text-only")
    # Fehlerpfad: leerer Übungs-Text -> Exit != 0 + JSON-Error
    empty = tmp_path / "leer.txt"
    empty.write_text("nur Prosa ohne Gewichte\n", encoding="utf-8")
    bad = subprocess.run([sys.executable, str(SCRIPT), "--exercises", str(empty),
                          "--as-of", "2026-07-02"], capture_output=True, text=True)
    assert bad.returncode != 0
    assert json.loads(bad.stdout)["ok"] is False
