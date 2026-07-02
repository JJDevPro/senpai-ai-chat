"""Repo-weiter Data-free-Lint — kein echter Personenwert in getracktem Code/Doku.

Der Personal-Data-frei-Gate (CLAUDE.md §0) ist HART: Identität lebt ausschließlich
in Google Drive, NIE im git-Repo. Dieser Test zieht das Gate über den GESAMTEN
getrackten Baum — seit PR-7 **inklusive `tests/` und Datei-NAMEN**, möglich weil
die Identitäts-Tokens nur noch als gesaltete SHA-256-Hashes existieren
(`tests/denylist.py`) und nicht mehr im Klartext.

Zusätzlich (Entscheidung #9): Koordinaten-Paare der Heim-Gegend gelten als Leak
(Heim-Strecken-Anker gehören nach athlete.md/Drive, nicht ins Repo).
"""

import subprocess
from pathlib import Path

from denylist import COORD_PAIR, denied_words

REPO = Path(__file__).resolve().parents[1]

# data/ ist gitignored, .git/ kein Quellcode. tests/ wird MIT gescannt (PR-7).
# claude-ai-chat-files/ = bewusste PII-ENKLAVE (Entscheidung 2026-07, v10.1.0):
# der generierte claude.ai-Twin darf personalisierte Assets (Race-Strategie,
# GPX, Bright-Sky-URL) enthalten — privater Repo, dokumentiert in
# docs/CLAUDE_AI_EXPORT.md. tests/test_claude_ai_export.py pinnt dieses Set
# exakt (die Ausnahme kann nicht stillschweigend wachsen) und hält den
# Exporter-Quellcode selbst PII-frei.
EXCLUDE_PREFIXES = ("data/", ".git/", "claude-ai-chat-files/")
# Binär-/Asset-Endungen ohne durchsuchbaren Text.
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
                   ".gpx", ".fit", ".zip", ".woff", ".woff2"}


def _tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    )
    for rel in out.stdout.splitlines():
        if rel.startswith(EXCLUDE_PREFIXES):
            continue
        yield rel, REPO / rel


def test_no_personal_identity_in_tracked_repo():
    hits = []
    for rel, p in _tracked_files():
        # Datei-NAMEN mitprüfen (ein Export "Lauf-<Name>.fit" wäre sonst unsichtbar).
        for w in denied_words(rel):
            hits.append(f"{rel} (Dateiname): {w}")
        if p.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for w in denied_words(line):
                hits.append(f"{rel}:{n}: Token {w!r}")
    assert not hits, (
        "PERSONAL-DATA-FREI verletzt — Identitäts-Token im getrackten Repo "
        "(Identität gehört in Drive, nie ins git):\n" + "\n".join(hits)
    )


def test_no_home_coordinates_in_tracked_repo():
    hits = []
    for rel, p in _tracked_files():
        if p.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if COORD_PAIR.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:90]}")
    assert not hits, (
        "Koordinaten-Leak der Heim-Gegend — Strecken-Anker gehören nach "
        "athlete.md (Drive), nicht ins Repo:\n" + "\n".join(hits)
    )
