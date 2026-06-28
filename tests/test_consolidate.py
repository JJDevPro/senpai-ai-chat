"""Regression tests for lib/consolidate.py — claude.ai-style memory consolidation.

DATA-FREE & DRIVE-FREE: these tests never touch Google Drive and use only
SYNTHETIC journal/state text authored here. They exercise the pure
extract/dedup/render helpers plus the `run_consolidate` orchestrator with
`pull_drive` fully monkeypatched to a local in-memory fake (the `_FakeDrive`
pattern copied from test_archive.py). Locked behavior:

  1. extraction finds >= 1 durable learning (recurring pattern + new PR/baseline).
  2. dedup drops a candidate already present in the existing state (no re-promote).
  3. render appends the new block with EXACTLY ONE blank-line delimiter.
  4. idempotency: a second run over the same journal promotes NOTHING new and
     leaves the state byte-identical.
  5. a MISSING target state file -> SystemExit(non-zero) with a pre-seed
     instruction; the fake Drive's create-path is NEVER called.
  6. a PRESENT journal+state -> download, patch, files.update (upload) round-trip.
  7. bad --as-of -> non-zero exit with a JSON error object on stderr.
"""

import sys
from pathlib import Path

import pytest

# lib/ is not a package on sys.path by default — add it for `import consolidate`.
LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import consolidate  # noqa: E402


# --------------------------------------------------------------------------- #
# Synthetic journal fixtures (authored here — no real personal/health values)
# --------------------------------------------------------------------------- #
JOURNAL_RECURRING = (
    "## [daily] 2026-06-26\n"
    "- Handy im Bett, Bedtime nach 00:30 verschoben.\n"
    "- TSB +4.\n"
    "\n"
    "## [daily] 2026-06-27\n"
    "- Handy im Bett, Bedtime nach 00:30 verschoben.\n"
    "- TSB +2.\n"
)

JOURNAL_WITH_PR = (
    "## [run] 2026-06-28\n"
    "- Pace@Z2 PR: 8:42/km bei HR 145.\n"
    "- GCT sauber.\n"
    "\n"
    "## [weekly] 2026-06-28\n"
    "- Neue VO2-Baseline: 35.4.\n"
)


# --------------------------------------------------------------------------- #
# Pure extract / dedup / render logic
# --------------------------------------------------------------------------- #
def test_extract_finds_recurring_pattern():
    cands = consolidate.extract_candidates(JOURNAL_RECURRING)
    texts = [c["text"] for c in cands]
    assert any("Bedtime nach 00:30" in t for t in texts)
    pat = next(c for c in cands if "Bedtime" in c["text"])
    assert pat["source"] == "pattern"
    assert pat["count"] >= consolidate.RECURRENCE_MIN
    # A one-off, non-recurring bullet must NOT be promoted.
    assert not any("TSB +4" in t for t in texts)


def test_extract_finds_new_pr_and_baseline():
    cands = consolidate.extract_candidates(JOURNAL_WITH_PR)
    by_source = {c["source"]: c["text"] for c in cands}
    assert "run" in by_source and "PR" in by_source["run"]
    assert "weekly" in by_source and "Baseline" in by_source["weekly"]
    assert len(cands) >= 1


def test_dedup_drops_already_present():
    cands = consolidate.extract_candidates(JOURNAL_WITH_PR)
    # Pre-load the baselines state with the PR line already promoted.
    existing = (
        "- [2026-06-20] (run) Pace@Z2 PR: 8:42/km bei HR 145.   "
        + consolidate._MARK
        + "\n"
    )
    fresh = consolidate.dedup(cands, existing)
    fresh_texts = [c["text"] for c in fresh]
    assert not any("8:42/km" in t for t in fresh_texts)  # not re-promoted
    assert any("VO2-Baseline" in t for t in fresh_texts)  # the new one survives


def test_render_appends_single_delimiter():
    existing = "- [2026-06-01] (run) Old fact.   " + consolidate._MARK + "\n"
    new = [{"source": "weekly", "text": "Neue VO2-Baseline: 35.4."}]
    out = consolidate.render_patch(existing, new, "2026-06-28")
    assert "Old fact." in out
    assert "## " not in out  # state lines, not journal headers
    assert out.count(consolidate._MARK) == 2
    assert "\n\n\n" not in out  # exactly one blank-line delimiter
    assert out.split("\n\n")[1].startswith("- [2026-06-28] (weekly)")


def test_render_into_empty_state_no_leading_blank():
    new = [{"source": "pattern", "text": "X."}]
    out = consolidate.render_patch("   \n\n ", new, "2026-06-28")
    assert out == "- [2026-06-28] (pattern) X.   " + consolidate._MARK + "\n"
    assert not out.startswith("\n")


def test_render_empty_learnings_is_byte_identical():
    existing = "- [2026-06-01] (run) Old.   " + consolidate._MARK + "\n"
    assert consolidate.render_patch(existing, [], "2026-06-28") == existing


# --------------------------------------------------------------------------- #
# run_consolidate orchestrator against a fake pull_drive (no real Drive)
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


def test_missing_target_errors_and_never_creates(monkeypatch, tmp_path, capsys):
    # journal present, but learnings.md absent -> pre-seed error, no create.
    fake = _FakeDrive({"senpai-journal.md": JOURNAL_RECURRING})
    _install_fake(monkeypatch, fake)

    with pytest.raises(SystemExit) as exc:
        consolidate.run_consolidate(
            target="learnings",
            day="2026-06-28",
            journal_name="senpai-journal.md",
            target_name="learnings.md",
            folder_id="FOLDER",
            out_dir=str(tmp_path),
        )
    assert exc.value.code != 0
    assert fake.created is False
    err = capsys.readouterr().err
    assert "PRE-SEED" in err
    assert "learnings.md" in err


def test_present_promotes_via_update(monkeypatch, tmp_path):
    fake = _FakeDrive(
        {
            "senpai-journal.md": JOURNAL_RECURRING,
            "learnings.md": "- [2026-06-01] (pattern) Some old learning.   "
            + consolidate._MARK
            + "\n",
        }
    )
    _install_fake(monkeypatch, fake)

    fid, promoted = consolidate.run_consolidate(
        target="learnings",
        day="2026-06-28",
        journal_name="senpai-journal.md",
        target_name="learnings.md",
        folder_id="FOLDER",
        out_dir=str(tmp_path),
    )
    assert fid == "id::learnings.md"
    assert fake.updated is True
    assert fake.created is False
    assert any("Bedtime" in t for t in promoted)
    final = fake.files["learnings.md"]
    assert "Some old learning." in final  # history preserved
    assert "[2026-06-28] (pattern)" in final


def test_idempotent_second_run_promotes_nothing(monkeypatch, tmp_path):
    fake = _FakeDrive(
        {
            "senpai-journal.md": JOURNAL_RECURRING,
            "learnings.md": "",  # pre-seeded empty
        }
    )
    _install_fake(monkeypatch, fake)

    kwargs = dict(
        target="learnings",
        day="2026-06-28",
        journal_name="senpai-journal.md",
        target_name="learnings.md",
        folder_id="FOLDER",
        out_dir=str(tmp_path),
    )

    _, promoted1 = consolidate.run_consolidate(**kwargs)
    assert len(promoted1) >= 1
    state_after_1 = fake.files["learnings.md"]

    _, promoted2 = consolidate.run_consolidate(**kwargs)
    assert promoted2 == []  # nothing new on the second pass
    assert fake.files["learnings.md"] == state_after_1  # byte-identical


def test_baselines_target_promotes_pr_not_pattern(monkeypatch, tmp_path):
    fake = _FakeDrive(
        {
            "senpai-journal.md": JOURNAL_WITH_PR,
            "baselines.md": "",
        }
    )
    _install_fake(monkeypatch, fake)

    _, promoted = consolidate.run_consolidate(
        target="baselines",
        day="2026-06-28",
        journal_name="senpai-journal.md",
        target_name="baselines.md",
        folder_id="FOLDER",
        out_dir=str(tmp_path),
    )
    assert any("PR" in t for t in promoted)
    assert any("Baseline" in t for t in promoted)


def test_main_prints_visible_diff(monkeypatch, tmp_path, capsys):
    fake = _FakeDrive(
        {"senpai-journal.md": JOURNAL_RECURRING, "learnings.md": ""}
    )
    _install_fake(monkeypatch, fake)

    rc = consolidate.main(
        [
            "--target", "learnings",
            "--as-of", "2026-06-28",
            "--folder", "FOLDER",
            "--out", str(tmp_path),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "consolidated -> learnings.md" in out
    assert "+ [2026-06-28]" in out


def test_main_bad_as_of_returns_nonzero_json_error(monkeypatch, tmp_path, capsys):
    fake = _FakeDrive({"senpai-journal.md": "", "learnings.md": ""})
    _install_fake(monkeypatch, fake)

    rc = consolidate.main(["--as-of", "28-06-2026", "--out", str(tmp_path)])
    assert rc != 0
    err = capsys.readouterr().err
    assert '"error"' in err
