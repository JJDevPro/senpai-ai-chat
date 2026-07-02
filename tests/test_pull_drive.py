"""Tests für lib/pull_drive.py — die netzfreien Pfade (Guards, Filter, Escaping).

DATA-FREE & OHNE NETZ: getestet werden nur Codepfade, die VOR jedem Credential-/
API-Call greifen — der Write-Back-Guard (Whitelist State-Dateien + Personal-
Ordner, Audit/PR-2), das --exact-Filterprinzip und das Query-Escaping.
"""

import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import pull_drive as pd  # noqa: E402

STATE = pd.STATE_FOLDER_ID


def test_q_escape():
    assert pd._q_escape("a'b") == "a\\'b"
    assert pd._q_escape("a\\b") == "a\\\\b"


def test_upload_guard_rejects_foreign_folder(tmp_path, capsys):
    f = tmp_path / "live.md"
    f.write_text("x", encoding="utf-8")
    rc = pd.main(["--upload", str(f), "--folder", "TRUTH_FOLDER_XYZ", "--name", "live.md"])
    assert rc == 3
    assert "READ-ONLY" in capsys.readouterr().err


def test_upload_guard_rejects_unregistered_state_file(tmp_path, capsys):
    f = tmp_path / "evil.md"
    f.write_text("x", encoding="utf-8")
    rc = pd.main(["--upload", str(f), "--folder", STATE, "--name", "evil.md"])
    assert rc == 3
    assert "not a registered state file" in capsys.readouterr().err


def test_upload_guard_uses_basename_when_no_name(tmp_path, capsys):
    f = tmp_path / "raw-export.json"
    f.write_text("{}", encoding="utf-8")
    rc = pd.main(["--upload", str(f), "--folder", STATE])
    assert rc == 3  # basename ist keine registrierte State-Datei


def test_state_whitelist_covers_claude_md_registry():
    # CLAUDE.md §11 State-Dateien müssen alle uploadbar sein.
    for name in ("live.md", "athlete.md", "baselines.md", "learnings.md",
                 "coaching_cues.md", "readiness-history.csv", "trend_snapshot.md",
                 "backlog.md", "gear.md", "senpai-journal.md"):
        assert name in pd.STATE_FILES


def test_exact_filter_principle():
    # Das --exact-Nachfilter-Prinzip: contains-Treffer werden auf Namensgleichheit reduziert.
    matches = [{"name": "Historie.md"}, {"name": "Archiv_Historie.md"}]
    exact = [f for f in matches if f["name"] == "Historie.md"]
    assert [f["name"] for f in exact] == ["Historie.md"]
