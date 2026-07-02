"""Shared pytest scaffolding for the Senpai (chat) regression suite.

The production logic lives in *skill scripts* under
``.claude/skills/*/scripts/`` (a path that is not a Python package), so we
put those script dirs on ``sys.path`` here. Then the test modules can simply
``import slice_hae_day`` / ``import banister`` / etc.

Notes
-----
* ``banister.py`` and ``dedup_trainings.py`` exist in BOTH the daily-check-skill
  and run-bundle-skill script dirs. Byte-identity is ENFORCED by
  ``test_banister_parity.py`` (daily-check is the source of truth; edit there,
  then sync). Import order is therefore harmless; ``slice_hae_day`` /
  ``safety_gate`` / ``daily_signals`` only live in daily-check.
* ``banister.compute_from_sheet`` does ``from dedup_trainings import dedup`` at
  call time, so ``dedup_trainings`` must be importable — the sys.path insert
  below satisfies that.
* DATA-FREE: nothing here loads real health data. The only inputs are the tiny
  synthetic fixtures in ``tests/fixtures/``.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / ".claude" / "skills"

# Script dirs that hold the modules under test.
_SCRIPT_DIRS = [
    SKILLS / "run-bundle-skill" / "scripts",   # analyze_run_fit, banister, dedup_trainings, pacing_card
    SKILLS / "daily-check-skill" / "scripts",  # slice_hae_day, safety_gate, daily_signals, banister, dedup
    SKILLS / "gym-bundle-skill" / "scripts",   # analyze_gym, unzip_gym
    REPO_ROOT / "lib",                          # make_ics, pull_drive
]
for _d in _SCRIPT_DIRS:
    p = str(_d)
    if _d.is_dir() and p not in sys.path:
        sys.path.insert(0, p)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to tests/fixtures/."""
    return FIXTURES


@pytest.fixture(scope="session")
def hae_path(fixtures_dir) -> Path:
    """Synthetic Health-Auto-Export JSON (2 days, hand-crafted known values)."""
    return fixtures_dir / "hae_synthetic.json"


@pytest.fixture(scope="session")
def trainings_csv_text(fixtures_dir) -> str:
    """Raw text of the synthetic Trainings_v5 CSV (read as the skill would)."""
    return (fixtures_dir / "trainings_synthetic.csv").read_text(encoding="utf-8")
