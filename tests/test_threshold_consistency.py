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

from pathlib import Path

import analyze_run_fit as arf
import banister
import running_tolerance as rt
import safety_gate as sg
import sentinel as sen

REPO_ROOT = Path(__file__).resolve().parents[1]


def _doc(rel):
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


CLAUDE_MD = _doc("CLAUDE.md")
RUN_SKILL = _doc(".claude/skills/run-bundle-skill/SKILL.md")
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
