"""Regression tests for lib/bootstrap.py — SessionStart identity-bootstrap.

DATA-FREE & DRIVE-FREE: these tests never touch Google Drive and contain NO real
personal value. They exercise the pure extraction/banner logic (`build_banner`
and helpers) against SYNTHETIC athlete/live markdown, plus the `run_bootstrap`
orchestrator with `pull_drive` fully monkeypatched to a local in-memory fake.

Locks:
  1. build_banner pulls Name (athlete.md), KW + Gewicht/HRV/VO2 (live.md tables)
     and counts bullets under "## Aktive Overrides".
  2. missing fields degrade to "n/a" (never crash, never fabricate).
  3. run_bootstrap on a SUCCESSFUL pull writes the seed files and prints the OK
     banner, returning 0.
  4. run_bootstrap on ANY pull failure prints the WARN banner and STILL returns 0
     (non-blocking) — and never fabricates state.
"""

import sys
from pathlib import Path

import pytest

# lib/ is not a package on sys.path by default — add it for `import bootstrap`.
LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import bootstrap  # noqa: E402


# --------------------------------------------------------------------------- #
# Synthetic seed text (fake athlete — no real personal value anywhere)
# --------------------------------------------------------------------------- #
SYN_ATHLETE = """# Athlet-Profil

**Name:** Testathlet
**Beruf:** Cloud-Engineer
"""

SYN_LIVE = """# Live-State

Stand: KW01 2026

## Werte
| Metrik | Wert |
|---|---|
| Gewicht | 80.0 kg |
| HRV | 62 ms |
| VO2 | 35.5 |

## Aktive Overrides
- Bedtime-Attacke aktiv
- Mg-Protokoll
"""


# --------------------------------------------------------------------------- #
# Pure extraction / banner logic
# --------------------------------------------------------------------------- #
def test_build_banner_full_seed():
    banner = bootstrap.build_banner(SYN_ATHLETE, SYN_LIVE)
    assert banner == (
        "Senpai bootstrap OK — Athlet: Testathlet · KW01 · "
        "Gewicht 80.0 kg · HRV 62 ms · VO2 35.5 · Overrides: 2"
    )


def test_extract_name():
    assert bootstrap._extract_name(SYN_ATHLETE) == "Testathlet"
    assert bootstrap._extract_name("no name here") == "n/a"


def test_extract_kw():
    assert bootstrap._extract_kw(SYN_LIVE) == "KW01"
    assert bootstrap._extract_kw("no stand line") == "n/a"


def test_missing_metrics_degrade_to_na():
    banner = bootstrap.build_banner("", "Stand: KW02\n")
    assert "Athlet: n/a" in banner
    assert "KW02" in banner
    assert "Gewicht n/a" in banner
    assert "HRV n/a" in banner
    assert "VO2 n/a" in banner
    assert "Overrides: 0" in banner


def test_override_placeholder_counts_zero():
    live = "Stand: KW03\n\n## Aktive Overrides\n- keine\n"
    assert bootstrap._count_overrides(live) == 0
    # next-heading boundary: bullets after the section don't leak in
    live2 = "## Aktive Overrides\n- A\n- B\n\n## Andere\n- C\n- D\n"
    assert bootstrap._count_overrides(live2) == 2


def test_simple_colon_metric_form():
    live = "Stand: KW04\nGewicht: 79.2\nHRV: 55\nVO2: 34.1\n"
    banner = bootstrap.build_banner("", live)
    assert "Gewicht 79.2" in banner
    assert "HRV 55" in banner
    assert "VO2 34.1" in banner


# --------------------------------------------------------------------------- #
# run_bootstrap orchestrator against a fake pull_drive (no real Drive)
# --------------------------------------------------------------------------- #
class _FakeDrive:
    """Minimal stand-in: a folder is a dict {name: text}."""

    def __init__(self, files):
        self.files = dict(files)


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

    monkeypatch.setattr(pd, "_list_matches", _list)
    monkeypatch.setattr(pd, "_download_media", _download)
    return pd


def test_run_bootstrap_success_prints_ok_banner(monkeypatch, tmp_path, capsys):
    fake = _FakeDrive({"athlete.md": SYN_ATHLETE, "live.md": SYN_LIVE})
    _install_fake(monkeypatch, fake)

    rc = bootstrap.run_bootstrap(folder="FOLDER", out_dir=str(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Senpai bootstrap OK" in out
    assert "Testathlet" in out
    assert "Overrides: 2" in out
    # seed files were actually written to the scratch dir
    assert (tmp_path / "athlete.md").read_text(encoding="utf-8") == SYN_ATHLETE
    assert (tmp_path / "live.md").read_text(encoding="utf-8") == SYN_LIVE


def test_run_bootstrap_network_failure_warns_and_exits_zero(monkeypatch, tmp_path, capsys):
    import pull_drive as pd

    monkeypatch.setattr(pd, "_load_credentials", lambda sa, scopes: object())
    monkeypatch.setattr(pd, "_drive", lambda creds: object())

    def _boom(svc, folder_id, match, ext):
        raise ConnectionError("drive unreachable")

    monkeypatch.setattr(pd, "_list_matches", _boom)

    rc = bootstrap.run_bootstrap(folder="FOLDER", out_dir=str(tmp_path))
    assert rc == 0  # NON-BLOCKING
    out = capsys.readouterr().out
    assert "Senpai bootstrap WARN" in out
    assert "do not fabricate athlete state" in out


def test_run_bootstrap_credential_systemexit_warns_and_exits_zero(monkeypatch, tmp_path, capsys):
    import pull_drive as pd

    def _no_creds(sa, scopes):
        raise SystemExit(2)

    monkeypatch.setattr(pd, "_load_credentials", _no_creds)

    rc = bootstrap.run_bootstrap(folder="FOLDER", out_dir=str(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Senpai bootstrap WARN" in out


def test_main_smoke(monkeypatch, tmp_path, capsys):
    fake = _FakeDrive({"athlete.md": SYN_ATHLETE, "live.md": SYN_LIVE})
    _install_fake(monkeypatch, fake)

    rc = bootstrap.main(["--folder", "FOLDER", "--out", str(tmp_path)])
    assert rc == 0
    assert "Senpai bootstrap OK" in capsys.readouterr().out


def test_run_bootstrap_missing_seed_warns_instead_of_ok(monkeypatch, tmp_path, capsys):
    # PR-2 (Audit-CONFIRMED): technisch erfolgreicher Pull OHNE Seed-Dateien darf
    # kein "bootstrap OK" mit lauter n/a drucken — WARN + nicht fabrizieren.
    fake = _FakeDrive({})  # Ordner leer: weder athlete.md noch live.md
    _install_fake(monkeypatch, fake)

    rc = bootstrap.run_bootstrap(folder="FOLDER", out_dir=str(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Senpai bootstrap WARN" in out
    assert "seed fehlt" in out
    assert "bootstrap OK" not in out


def test_run_bootstrap_partial_seed_flags_missing_file(monkeypatch, tmp_path, capsys):
    fake = _FakeDrive({"athlete.md": SYN_ATHLETE})  # live.md fehlt
    _install_fake(monkeypatch, fake)

    rc = bootstrap.run_bootstrap(folder="FOLDER", out_dir=str(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Senpai bootstrap OK" in out
    assert "Seed unvollständig" in out and "live.md" in out
