"""SSoT-Divergenz-Tripwire: Prosa-Docs muessen mit den Code-Konstanten uebereinstimmen.

Hintergrund
-----------
Der v9.0.0-SSoT-Refactor hat die Schwellen-Redundanz (derselbe Wert lebt in Prosa
UND in Code) als Drift-Quelle erkannt, aber keinen Tripwire eingebaut. Dieser Test
schliesst die Luecke: der CODE ist die Single Source of Truth; die Doku-Dateien
(CLAUDE.md, die SKILL.md, modules/) MUESSEN die Code-Konstanten widerspiegeln.
Aendert jemand eine Konstante, ohne die Doku nachzuziehen (oder umgekehrt), schlaegt
genau dieser Test fehl — die Drift, die PR1 manuell aufgeraeumt hat, kann so nicht
unbemerkt zurueckkehren.

DATA-FREE: liest nur getrackte, personendaten-freie Repo-Dateien (keine Health-Daten).
Konvention wie der Rest der Suite: conftest.py legt die Skript-Dirs auf sys.path.
"""

import importlib.util
from pathlib import Path

import analyze_run_fit as arf
import banister
import running_tolerance as rt
import safety_gate as sg
import sentinel as sen

REPO_ROOT = Path(__file__).resolve().parents[1]

# lib/constants.py = kanonische Registry (SSoT seit v10-PR-1). Direkt per Pfad
# laden — lib/ liegt nicht auf dem conftest-sys.path (nur die Skill-Script-Dirs).
_spec = importlib.util.spec_from_file_location(
    "senpai_constants", REPO_ROOT / "lib" / "constants.py"
)
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def _doc(rel):
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


CLAUDE_MD = _doc("CLAUDE.md")
RUN_SKILL = _doc(".claude/skills/run-bundle-skill/SKILL.md")
DAILY_SKILL = _doc(".claude/skills/daily-check-skill/SKILL.md")
NUTRITION_SKILL = _doc(".claude/skills/nutrition-skill/SKILL.md")
WEATHER_SKILL = _doc(".claude/skills/weather-runprep-skill/SKILL.md")
V3_PROTO = _doc("modules/V3_Protocol.md")


# ── HRV-Schwellen: safety_gate / sentinel <-> CLAUDE.md §5 ───────────────────
def test_hrv_constants_agree_between_gate_and_sentinel():
    assert sg.HRV_RED == sen.HRV_RED == 50
    assert sg.HRV_CRITICAL == sen.HRV_CRITICAL == 40


def test_hrv_thresholds_match_claude_md():
    assert f"<{sg.HRV_RED}" in CLAUDE_MD                     # "🔴 <50"
    assert f"<{sg.HRV_CRITICAL}" in CLAUDE_MD                # "🔴🔴 <40"
    assert f"Schlaf <{sg.SLEEP_CRITICAL_H}h" in CLAUDE_MD    # "<40 + Schlaf <6h"


# ── Atemstoerungen: sentinel <-> CLAUDE.md §5 ───────────────────────────────
def test_breathing_bands_match_claude_md():
    assert f"≤{sen.BREATHING_GREEN}" in CLAUDE_MD     # "🟢 ≤10"
    assert f">{sen.BREATHING_YELLOW}" in CLAUDE_MD    # ">12–15"
    assert f">{sen.BREATHING_ORANGE}" in CLAUDE_MD    # "🔴 >15"


# ── Hitze-Tax: analyze_run_fit <-> run SKILL.md ─────────────────────────────
def test_heat_tax_matches_docs():
    assert arf.HEAT_TAX_S_PER_C == 3.5
    assert arf.HEAT_BASELINE_C == 18.0
    assert "3,5 sek/km" in RUN_SKILL     # HEAT_TAX_S_PER_C (deutsche Dezimalschreibweise)
    assert "18°C" in RUN_SKILL           # HEAT_BASELINE_C


# ── Walking-Filter v3.5: analyze_run_fit <-> run SKILL.md §4 ────────────────
def test_walking_filter_matches_docs():
    assert arf.WALK_CAD == 140
    assert arf.WALK_SPD == 2.0
    assert f"<{arf.WALK_CAD}" in RUN_SKILL    # "Kadenz <140" (int, sicher ableitbar)
    assert "<2,0 m/s" in RUN_SKILL            # WALK_SPD (deutsche Dezimalschreibweise)


# ── HR-Zonen-Cap: analyze_run_fit <-> CLAUDE.md + run SKILL.md ──────────────
def test_hr_zone_cap_consistent_across_docs():
    assert arf.HR_Z2_CAP == 147
    for doc in (CLAUDE_MD, RUN_SKILL):
        assert "136" in doc and str(arf.HR_Z2_CAP) in doc   # Z2 136–147 in beiden Docs


# ── TSB-Ampel: banister.tsb_ampel <-> run SKILL.md ──────────────────────────
def test_tsb_bands_code_matches_run_skill():
    # Code-Grenzen (banister.tsb_ampel): >5 🟢 / >=-10 🟡 / >=-30 🟠 / <-30 🔴
    assert banister.tsb_ampel(6) == "🟢"
    assert banister.tsb_ampel(0) == "🟡"
    assert banister.tsb_ampel(-20) == "🟠"
    assert banister.tsb_ampel(-31) == "🔴"
    # Doku muss dieselbe 🟠->🔴-Grenze tragen (PR1 hat das alte -25 auf -30 korrigiert):
    assert "<-30" in RUN_SKILL
    assert "-25 bis -10" not in RUN_SKILL    # alte, divergente Grenze ist weg


# ── ACWR: running_tolerance interne Konsistenz ──────────────────────────────
def test_acwr_constants_self_consistent():
    assert rt.RAMP_MAX == 1.3
    assert rt.ACWR_LOW == 0.8
    assert rt.CEILING_FACTOR == rt.RAMP_MAX


# ═════════════════════════════════════════════════════════════════════════════
# lib/constants.py = kanonische Registry: Skript-Konstanten UND Doku-Prosa
# muessen mit ihr uebereinstimmen (v10-PR-1). Aendert jemand nur eine Seite,
# schlaegt genau EIN Test hier fehl und benennt die Drift.
# ═════════════════════════════════════════════════════════════════════════════

def test_registry_matches_script_constants():
    assert C.HRV_RED == sg.HRV_RED == sen.HRV_RED
    assert C.HRV_CRITICAL == sg.HRV_CRITICAL == sen.HRV_CRITICAL
    assert C.SLEEP_CRITICAL_H == sg.SLEEP_CRITICAL_H
    assert C.BREATHING_GREEN == sen.BREATHING_GREEN
    assert C.BREATHING_YELLOW == sen.BREATHING_YELLOW
    assert C.BREATHING_ORANGE == sen.BREATHING_ORANGE
    assert C.HEAT_TAX_S_PER_C == arf.HEAT_TAX_S_PER_C
    assert C.HEAT_BASELINE_C == arf.HEAT_BASELINE_C
    assert C.WALK_CAD == arf.WALK_CAD
    assert C.WALK_SPD == arf.WALK_SPD
    assert C.HR_Z2_CAP == arf.HR_Z2_CAP
    assert C.ACWR_LOW == rt.ACWR_LOW
    assert C.RAMP_MAX == rt.RAMP_MAX


def test_registry_tsb_bands_match_banister():
    assert banister.tsb_ampel(C.TSB_GREEN_MIN + 1) == "🟢"
    assert banister.tsb_ampel(C.TSB_GREEN_MIN) == "🟡"
    assert banister.tsb_ampel(C.TSB_YELLOW_MIN) == "🟡"
    assert banister.tsb_ampel(C.TSB_YELLOW_MIN - 1) == "🟠"
    assert banister.tsb_ampel(C.TSB_ORANGE_MIN) == "🟠"
    assert banister.tsb_ampel(C.TSB_ORANGE_MIN - 1) == "🔴"


def test_hrv_display_band_in_claude_md():
    # 🟡-Anzeigeband 50–59 (by design, CLAUDE.md §5)
    assert f"{C.HRV_RED}–59" in CLAUDE_MD
    assert f"≥{C.HRV_GREEN}" in CLAUDE_MD


def test_vo2_bands_in_claude_md():
    assert C.VO2_GREEN == 35.0 and C.VO2_YELLOW_LOW == 33.0
    assert "≥35,0" in CLAUDE_MD and "<33,0" in CLAUDE_MD


def test_trimp_bands_docs_agree():
    # Kanonisch (Entscheidung 2026-07-02): 🟡 100–150 · 🟠 150–180 — in BEIDEN Skills.
    assert C.TRIMP_GREEN_MAX == 100 and C.TRIMP_YELLOW_MAX == 150 and C.TRIMP_ORANGE_MAX == 180
    assert "100−150" in DAILY_SKILL or "100-150" in DAILY_SKILL or "100–150" in DAILY_SKILL
    assert "100-150" in RUN_SKILL
    assert "100-140" not in RUN_SKILL  # alte, divergente run-bundle-Grenze ist weg


def test_heat_tax_is_single_compute_value_across_docs():
    assert C.HEAT_TAX_S_PER_C == 3.5
    for doc in (CLAUDE_MD, V3_PROTO, WEATHER_SKILL, RUN_SKILL, DAILY_SKILL):
        assert "3,5" in doc  # der EINE Rechenwert taucht ueberall auf
    # die alte Prosa-Range als RECHENREGEL ist raus (Kalibrier-Band nur als Doku-Notiz):
    assert "+15–25 s/km" not in WEATHER_SKILL
    assert "+15–25 sek/km" not in V3_PROTO


def test_fat_rule_daytype_cap_plus_hard_gate():
    assert C.FAT_HARD_CAP_G == 85
    assert "Tagestyp-Cap" in NUTRITION_SKILL and "85 g" in NUTRITION_SKILL
    assert "Tagestyp-Cap" in DAILY_SKILL
    # 85 g ist ZUSAETZLICHES Gate, nicht die Ampel-Referenz:
    assert "85 g Hard-Cap [Ampel]" not in DAILY_SKILL


def test_bedtime_two_stage_rule_in_docs():
    assert C.BEDTIME_HALF_CUTOFF_MIN == 30 and C.BEDTIME_HALF_WEIGHT == 0.5
    assert "00:00-00:30" in DAILY_SKILL or "00:00–00:30" in DAILY_SKILL
    payload = _doc(".claude/skills/payload-skill/SKILL.md")
    assert "halb" in payload and "voll" in payload  # zweistufiger Bedtime-Score


def test_z2_form_targets_docs_agree():
    assert C.VR_TARGET_PCT == 11.0 and C.VR_WARN_PCT == 12.0
    assert "<11" in CLAUDE_MD and "<11" in V3_PROTO
    assert f"≥{C.CADENCE_Z2_TARGET}" in CLAUDE_MD
    assert f"≤{C.GCT_Z2_MAX_MS} ms" in CLAUDE_MD
    daten_parsing = _doc("modules/Daten_Parsing.md")
    assert f"≤{C.GCT_Z2_MAX_MS} ms" in daten_parsing
    assert "<300 ms" not in daten_parsing  # alte GCT-Drift ist weg


def test_sot_weekday_is_monday_everywhere():
    assert C.SOT_WEEKDAY == "Mo"
    payload = _doc(".claude/skills/payload-skill/SKILL.md")
    daten_parsing = _doc("modules/Daten_Parsing.md")
    assert "MONTAGS" in payload or "Mo-SoT" in payload
    assert "Sonntag-SoT" not in daten_parsing
    assert "Montag, nüchtern nach dem Aufstehen" in CLAUDE_MD


def test_viszeralfett_removed_from_schemas():
    # KPI gestrichen (Entscheidung 2026-07-02): keine VFat-Felder mehr in
    # Seeds, Sync-Output oder Live-State-Beschreibungen.
    sync = _doc(".claude/skills/sync-skill/SKILL.md")
    seed_live = _doc("drive-seed/live.md")
    seed_athlete = _doc("drive-seed/athlete.md")
    assert "VFat [X]" not in sync
    assert "{{VISZERAL}}" not in seed_live
    assert "{{VISZERAL_ZIEL}}" not in seed_athlete
    assert "Gewicht/KFA/Viszeralfett" not in CLAUDE_MD
