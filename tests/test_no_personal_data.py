"""Repo-weiter Data-free-Lint — kein echter Personenwert in getracktem Code/Doku.

Der Personal-Data-frei-Gate (CLAUDE.md §0) ist HART: Identität lebt ausschließlich
in Google Drive, NIE im git-Repo. `test_drive_seed.py` prüft nur `drive-seed/` —
dieser Test zieht das Gate über den GESAMTEN getrackten Baum (lib/, Skill-Scripts,
SKILL.md, commands, modules, drive-seed), damit ein Leak wie der Athleten-Name in
einem Kommentar oder Docstring in CI auffällt, statt still durchzurutschen.

Gescannt werden nur eindeutige Identitäts-Tokens (Name/E-Mail/enge Bezugspersonen +
Heimatstadt) — sie haben null legitime Verwendung im personal-data-freien Repo.
Ausgenommen: `tests/` (hier leben die Denylist-Definitionen) und nicht-Text-Assets.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Eindeutige Identitäts-Tokens — KEINE legitime Verwendung im Repo.
FORBIDDEN = ["Javier", "Garcell", "garcelljavier", "Janna", "Nürnberg", "Nuernberg"]

# Diese Pfad-Präfixe sind ausgenommen (Denylist-Defs leben in tests/; data/ ist
# gitignored; .git/ ist kein Quellcode).
EXCLUDE_PREFIXES = ("tests/", "data/", ".git/")
# Binär-/Asset-Endungen ohne durchsuchbaren Text.
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
                   ".gpx", ".fit", ".zip", ".woff", ".woff2"}


def _tracked_text_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    )
    for rel in out.stdout.splitlines():
        if rel.startswith(EXCLUDE_PREFIXES):
            continue
        p = REPO / rel
        if p.suffix.lower() in BINARY_SUFFIXES:
            continue
        yield rel, p


def test_no_personal_identity_in_tracked_repo():
    pat = re.compile("|".join(re.escape(t) for t in FORBIDDEN), re.IGNORECASE)
    hits = []
    for rel, p in _tracked_text_files():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:90]}")
    assert not hits, (
        "PERSONAL-DATA-FREI verletzt — echter Personenwert im getrackten Repo "
        "(Identität gehört in Drive, nie ins git):\n" + "\n".join(hits)
    )
