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


# ── PR-2-Regression: PR-Erkennung mit Wortgrenze (Audit-CONFIRMED-Fix) ────────
def test_pr_detection_ignores_protein_and_problem_lines():
    journal = (
        "## [run] 2026-06-27\n"
        "- Protein 155g erreicht, kein Problem beim Sprint\n"
        "- Neuer PR: Bench 62,5 kg\n"
        "- PRs gefeiert: 5k in 27:30\n"
    )
    cands = consolidate.extract_candidates(journal)
    run_texts = [c["text"] for c in cands if c["source"] == "run"]
    assert "Neuer PR: Bench 62,5 kg" in run_texts
    assert "PRs gefeiert: 5k in 27:30" in run_texts
    assert all("Protein" not in t for t in run_texts)  # Substring-Falle ist zu


def test_pr_detection_is_case_sensitive():
    # "pr" klein (z. B. in Wörtern/Slang) ist KEIN PR-Fakt — nur der Fachbegriff.
    journal = "## [run] 2026-06-27\n- pr-team meeting war zäh\n"
    cands = consolidate.extract_candidates(journal)
    assert [c for c in cands if c["source"] == "run"] == []


# --------------------------------------------------------------------------- #
# Local-Mode (--local --data-dir): Roundtrip ohne jeden Drive-/pull_drive-Zugriff
# --------------------------------------------------------------------------- #
# Kombiniertes synthetisches Journal: ein wiederkehrendes Muster (-> learnings)
# UND ein PR + eine Baseline (-> baselines) — data-free, keine echten Werte.
JOURNAL_LOCAL = JOURNAL_RECURRING + "\n" + JOURNAL_WITH_PR


def _seed_local(tmp_path, journal=JOURNAL_LOCAL, learnings="", baselines=""):
    """Seed ein Local-Mode-Datenverzeichnis mit den drei erwarteten Dateien."""
    (tmp_path / "senpai-journal.md").write_text(journal, encoding="utf-8")
    (tmp_path / "learnings.md").write_text(learnings, encoding="utf-8")
    (tmp_path / "baselines.md").write_text(baselines, encoding="utf-8")


def _block_drive(monkeypatch):
    """Simuliere eine Umgebung OHNE google-Libs: jeder Import von pull_drive/google
    schlaegt fehl. Der Local-Mode MUSS trotzdem durchlaufen (lazy import)."""
    for mod in ("pull_drive", "google", "google.oauth2", "googleapiclient"):
        monkeypatch.setitem(sys.modules, mod, None)  # import -> ImportError


def test_local_mode_roundtrip_without_pull_drive(monkeypatch, tmp_path, capsys):
    _seed_local(tmp_path)
    _block_drive(monkeypatch)  # KEIN Drive-Zugriff im Local-Mode — hart erzwungen

    rc = consolidate.main(
        ["--local", "--data-dir", str(tmp_path), "--as-of", "2026-06-28"]
    )
    assert rc == 0

    # learnings.md erhaelt das wiederkehrende Muster, baselines.md die Fakten.
    learnings = (tmp_path / "learnings.md").read_text(encoding="utf-8")
    baselines = (tmp_path / "baselines.md").read_text(encoding="utf-8")
    assert "Bedtime nach 00:30" in learnings
    assert "[2026-06-28] (pattern)" in learnings
    assert "Bedtime" not in baselines
    assert "Pace@Z2 PR" in baselines and "VO2-Baseline" in baselines
    assert consolidate._MARK in learnings and consolidate._MARK in baselines

    # Kompakte Zusammenfassung auf stdout: beide Targets + appendete Zeilen.
    out = capsys.readouterr().out
    assert "consolidated (local) -> learnings.md" in out
    assert "consolidated (local) -> baselines.md" in out
    assert "+ [2026-06-28]" in out


def test_local_mode_idempotent_and_reports_dedup(tmp_path, capsys):
    _seed_local(tmp_path)
    args = ["--local", "--data-dir", str(tmp_path), "--as-of", "2026-06-28"]

    assert consolidate.main(args) == 0
    state_l = (tmp_path / "learnings.md").read_text(encoding="utf-8")
    state_b = (tmp_path / "baselines.md").read_text(encoding="utf-8")
    capsys.readouterr()  # ersten Report verwerfen

    # Zweiter Lauf: NICHTS Neues, States byte-identisch, alles als dedup gemeldet.
    assert consolidate.main(args) == 0
    assert (tmp_path / "learnings.md").read_text(encoding="utf-8") == state_l
    assert (tmp_path / "baselines.md").read_text(encoding="utf-8") == state_b
    out = capsys.readouterr().out
    assert "0 new" in out and "(idempotent)" in out
    assert "= dedup:" in out  # die schon bekannten Kandidaten werden benannt
    assert "+ [" not in out  # nichts appendet


def test_local_mode_dedups_against_preseeded_state(tmp_path):
    # Der PR steht schon im lokalen baselines-State -> kein Re-Promote.
    preseeded = (
        "- [2026-06-20] (run) Pace@Z2 PR: 8:42/km bei HR 145.   "
        + consolidate._MARK
        + "\n"
    )
    _seed_local(tmp_path, baselines=preseeded)

    results = consolidate.run_consolidate_local(
        day="2026-06-28",
        journal_name="senpai-journal.md",
        learnings_name="learnings.md",
        baselines_name="baselines.md",
        data_dir=str(tmp_path),
    )
    by_name = {name: (promoted, deduped) for name, promoted, deduped in results}
    promoted_b, deduped_b = by_name["baselines.md"]
    assert not any("8:42/km" in t for t in promoted_b)  # nicht re-promotet
    assert any("8:42/km" in t for t in deduped_b)  # aber sichtbar als dedup gemeldet
    assert any("VO2-Baseline" in t for t in promoted_b)  # das Neue kommt durch
    # Der State bleibt Append-only: Alt-Zeile erhalten, Neues dahinter.
    final = (tmp_path / "baselines.md").read_text(encoding="utf-8")
    assert final.startswith(preseeded.rstrip("\n"))
    assert "VO2-Baseline" in final


def test_local_mode_missing_state_errors_and_creates_nothing(tmp_path, capsys):
    # Journal da, aber learnings.md fehlt -> klare Anweisung, non-zero, kein Anlegen.
    (tmp_path / "senpai-journal.md").write_text(JOURNAL_LOCAL, encoding="utf-8")
    (tmp_path / "baselines.md").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        consolidate.main(["--local", "--data-dir", str(tmp_path), "--as-of", "2026-06-28"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "learnings.md" in err
    assert "Local-Mode" in err
    assert not (tmp_path / "learnings.md").exists()  # NIE eine Datei angelegt


def test_local_mode_missing_journal_errors(tmp_path, capsys):
    (tmp_path / "learnings.md").write_text("", encoding="utf-8")
    (tmp_path / "baselines.md").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        consolidate.main(["--local", "--data-dir", str(tmp_path)])
    assert exc.value.code != 0
    assert "senpai-journal.md" in capsys.readouterr().err
