"""Regression tests for lib/archive.py — the rolling Drive-journal append logic.

DATA-FREE & DRIVE-FREE: these tests never touch Google Drive. They exercise the
pure append/format helpers (`format_section`, `append_section`) plus the
`run_archive` orchestrator with `pull_drive` fully monkeypatched to a local
in-memory fake. The point is to lock:

  1. a fresh (empty/whitespace) journal yields exactly one section, no leading blank.
  2. appending to a non-empty journal inserts exactly one blank-line delimiter and
     preserves the prior content (rolling history).
  3. the section header format is "## [kind] YYYY-MM-DD" and the body is framed.
  4. an unknown kind is rejected.
  5. a MISSING journal -> SystemExit(non-zero) with a pre-seed instruction; the
     fake Drive's create-path is NEVER called (we never create the file).
  6. a PRESENT journal -> download, append, files.update (upload) round-trip.
"""

import sys
from pathlib import Path

import pytest

# lib/ is not a package on sys.path by default — add it for `import archive`.
LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import archive  # noqa: E402


# --------------------------------------------------------------------------- #
# Pure format / append logic
# --------------------------------------------------------------------------- #
def test_format_section_shape():
    sec = archive.format_section("daily", "2026-06-28", "TSB +4. Go run.\n\n")
    assert sec == "## [daily] 2026-06-28\nTSB +4. Go run.\n"


def test_append_to_empty_journal_no_leading_blank():
    out = archive.append_section("", "run", "2026-06-28", "10k @ Z2. Clean.")
    assert out == "## [run] 2026-06-28\n10k @ Z2. Clean.\n"
    assert not out.startswith("\n")


def test_append_to_whitespace_only_journal():
    out = archive.append_section("   \n\n  ", "weekly", "2026-06-28", "CTL up.")
    assert out == "## [weekly] 2026-06-28\nCTL up.\n"


def test_append_preserves_history_with_single_blank_delimiter():
    j0 = archive.append_section("", "daily", "2026-06-27", "Day 1.")
    j1 = archive.append_section(j0, "daily", "2026-06-28", "Day 2.")
    assert j1 == (
        "## [daily] 2026-06-27\nDay 1.\n"
        "\n"
        "## [daily] 2026-06-28\nDay 2.\n"
    )
    # Exactly one blank line between sections; both headers survive.
    assert j1.count("## [daily]") == 2
    assert "\n\n\n" not in j1


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        archive.format_section("bogus", "2026-06-28", "x")


# --------------------------------------------------------------------------- #
# run_archive orchestrator against a fake pull_drive (no real Drive)
# --------------------------------------------------------------------------- #
class _FakeDrive:
    """Minimal stand-in: a folder is a dict {name: text}. Tracks if create ran."""

    def __init__(self, files):
        self.files = dict(files)  # name -> text
        self.created = False
        self.updated = False


def _install_fake(monkeypatch, fake: _FakeDrive):
    import pull_drive as pd

    monkeypatch.setattr(pd, "_load_credentials", lambda sa, scopes: object())
    monkeypatch.setattr(pd, "_drive", lambda creds: fake)

    def _list(svc, folder_id, match, ext):
        out = []
        for name in svc.files:
            if match and match not in name:
                continue
            out.append({"id": f"id::{name}", "name": name})
        return out

    def _download(svc, file_id, dest: Path):
        name = file_id.split("::", 1)[1]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(svc.files[name], encoding="utf-8")

    def _upload(svc, local_path, folder_id, name=None):
        name = name or Path(local_path).name
        text = Path(local_path).read_text(encoding="utf-8")
        if name in svc.files:
            svc.updated = True
        else:
            svc.created = True  # would happen on real Drive only with quota
        svc.files[name] = text
        return f"id::{name}"

    monkeypatch.setattr(pd, "_list_matches", _list)
    monkeypatch.setattr(pd, "_download_media", _download)
    monkeypatch.setattr(pd, "_upload", _upload)
    return pd


def test_missing_journal_errors_and_never_creates(monkeypatch, tmp_path, capsys):
    fake = _FakeDrive({})  # empty folder -> journal absent
    _install_fake(monkeypatch, fake)

    with pytest.raises(SystemExit) as exc:
        archive.run_archive(
            report_text="anything",
            kind="daily",
            day="2026-06-28",
            journal_name="senpai-journal.md",
            folder_id="FOLDER",
            out_dir=str(tmp_path),
        )
    assert exc.value.code != 0
    assert fake.created is False  # we NEVER create the file
    err = capsys.readouterr().err
    assert "PRE-SEED" in err
    assert "senpai-journal.md" in err


def test_present_journal_appends_via_update(monkeypatch, tmp_path):
    fake = _FakeDrive({"senpai-journal.md": "## [daily] 2026-06-27\nOld.\n"})
    _install_fake(monkeypatch, fake)

    fid = archive.run_archive(
        report_text="New verdict.",
        kind="run",
        day="2026-06-28",
        journal_name="senpai-journal.md",
        folder_id="FOLDER",
        out_dir=str(tmp_path),
    )
    assert fid == "id::senpai-journal.md"
    assert fake.updated is True
    assert fake.created is False
    final = fake.files["senpai-journal.md"]
    assert final == (
        "## [daily] 2026-06-27\nOld.\n"
        "\n"
        "## [run] 2026-06-28\nNew verdict.\n"
    )


def test_main_stdin_report_round_trip(monkeypatch, tmp_path, capsys):
    fake = _FakeDrive({"senpai-journal.md": ""})  # pre-seeded empty
    _install_fake(monkeypatch, fake)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("From stdin."))

    rc = archive.main(
        [
            "--report", "-",
            "--kind", "weekly",
            "--date", "2026-06-28",
            "--folder", "FOLDER",
            "--out", str(tmp_path),
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "id::senpai-journal.md"
    assert fake.files["senpai-journal.md"] == "## [weekly] 2026-06-28\nFrom stdin.\n"
