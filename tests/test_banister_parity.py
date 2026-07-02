"""Parity-Tripwire: banister.py + dedup_trainings.py existieren in ZWEI Skills.

run-bundle und daily-check bündeln beide die Banister-Engine (Skills sind
self-contained, kein Cross-Skill-Import). Damit die beiden Kopien nie wieder
still auseinanderlaufen (Audit-CONFIRMED: sie WAREN divergiert — dem run-bundle
fehlten step/compute_incremental/day_trimp), pinnt dieser Test Byte-Identität.

Konvention: die **daily-check-Version ist die Quelle** — dort editieren, dann
    cp .claude/skills/daily-check-skill/scripts/banister.py \
       .claude/skills/run-bundle-skill/scripts/banister.py
(analog dedup_trainings.py). Schlägt dieser Test fehl, wurde eine Kopie
einseitig geändert → syncen, nicht den Test lockern.
"""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DAILY = REPO / ".claude" / "skills" / "daily-check-skill" / "scripts"
RUN = REPO / ".claude" / "skills" / "run-bundle-skill" / "scripts"

SHARED = ["banister.py", "dedup_trainings.py"]


@pytest.mark.parametrize("name", SHARED)
def test_shared_engine_copies_are_byte_identical(name):
    a = (DAILY / name).read_bytes()
    b = (RUN / name).read_bytes()
    assert a == b, (
        f"{name} ist zwischen daily-check und run-bundle divergiert — "
        f"daily-check ist die Quelle: dort editieren und nach run-bundle syncen."
    )


def test_both_copies_expose_incremental_api():
    """Beide Kopien müssen die volle v2/v3-API tragen (der historische Drift war
    ein run-bundle OHNE step/compute_incremental/day_trimp)."""
    import importlib.util

    for base in (DAILY, RUN):
        spec = importlib.util.spec_from_file_location(f"banister_{base.parent.parent.name}",
                                                      base / "banister.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for fn in ("banister", "compute_from_sheet", "step", "compute_incremental", "day_trimp"):
            assert hasattr(mod, fn), f"{base / 'banister.py'} fehlt {fn}()"
