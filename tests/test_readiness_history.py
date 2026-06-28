"""Regression tests for daily-check-skill/scripts/readiness_history.py.

DATA-FREE & DRIVE-FREE: these tests never touch Google Drive. They exercise the
pure row/CSV helpers (`build_row`, `append_row`) plus the `run_history`
orchestrator with `pull_drive` fully monkeypatched to a local in-memory fake
(`_FakeDrive`, copied from tests/test_archive.py). The point is to lock:

  1. build_row maps the reduced upstream outputs onto the exact Drive-seed header.
  2. append_row on a header-only CSV grows by EXACTLY one data row.
  3. append_row with the SAME date is a NO-OP (idempotent on date).
  4. append_row preserves prior rows + the header order (rolling history).
  5. a MISSING CSV -> SystemExit(non-zero) with a pre-seed instruction; the fake
     Drive's create-path is NEVER called (we never create the file).
  6. a PRESENT CSV -> download, append, files.update (upload) round-trip.
  7. a bad --as-of -> non-zero exit + JSON error object (deterministic, no clock).

The aggregates here are SYNTHETIC (authored in-test) — no real personal/health data.
"""

import io
import json
import sys
from pathlib import Path

import pytest

# The daily-check scripts dir is already on sys.path via tests/conftest.py, but add
# it defensively so this module imports standalone too.
SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "daily-check-skill" / "scripts"
)
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import readiness_history as rh  # noqa: E402


# --------------------------------------------------------------------------- #
# Synthetic reduced upstream outputs (authored here — no real data)
# --------------------------------------------------------------------------- #
def _readiness(score=72, band="moderate", top_limiter="sleep"):
    return {"score": score, "band": band, "top_limiter": top_limiter,
            "top_driver": "hrv", "safety_override": False}


def _body_battery(bb_start=70, bb_end=42):
    return {"bb_start": bb_start, "bb_end": bb_end, "surrogate": True}


def _banister(tsb=-4.2):
    return {"tsb": tsb, "atl": 50.0, "ctl": 45.8}


def _hrv_baseline(status="balanced"):
    return {"status": status}


# --------------------------------------------------------------------------- #
# Pure build_row / append_row logic
# --------------------------------------------------------------------------- #
def test_build_row_maps_to_seed_header():
    row = rh.build_row(
        "2026-06-28",
        readiness=_readiness(score=72, band="moderate", top_limiter="sleep"),
        body_battery=_body_battery(bb_start=70, bb_end=42),
        banister=_banister(tsb=-4.2),
        hrv_baseline=_hrv_baseline("balanced"),
    )
    assert list(row.keys()) == rh.HEADER
    assert row == {
        "date": "2026-06-28",
        "readiness_score": 72,
        "band": "moderate",
        "hrv_status": "balanced",
        "bb_start": 70,
        "bb_end": 42,
        "tsb": -4.2,
        "top_limiter": "sleep",
    }


def test_build_row_missing_sources_leave_cells_none():
    row = rh.build_row("2026-06-28", readiness=_readiness())
    # body_battery / banister / hrv absent -> their cells are None (rendered empty).
    assert row["bb_start"] is None
    assert row["bb_end"] is None
    assert row["tsb"] is None
    assert row["hrv_status"] is None
    assert row["readiness_score"] == 72


def test_build_row_bad_date_raises():
    with pytest.raises(ValueError):
        rh.build_row("28.06.2026", readiness=_readiness())


def _header_only_csv():
    return ",".join(rh.HEADER) + "\n"


def test_append_to_header_only_grows_by_one_row():
    csv0 = _header_only_csv()
    row = rh.build_row("2026-06-28", readiness=_readiness(),
                       body_battery=_body_battery(), banister=_banister(),
                       hrv_baseline=_hrv_baseline())
    csv1 = rh.append_row(csv0, row)

    lines = [ln for ln in csv1.splitlines() if ln.strip()]
    assert lines[0] == ",".join(rh.HEADER)         # header preserved
    assert len(lines) == 2                          # header + exactly one data row
    parsed = list(__import__("csv").DictReader(io.StringIO(csv1)))
    assert len(parsed) == 1
    assert parsed[0]["date"] == "2026-06-28"
    assert parsed[0]["readiness_score"] == "72"
    assert parsed[0]["tsb"] == "-4.2"


def test_append_same_date_is_noop():
    csv0 = _header_only_csv()
    row = rh.build_row("2026-06-28", readiness=_readiness(score=72))
    csv1 = rh.append_row(csv0, row)

    # Re-append the SAME date (even with different values) -> unchanged text.
    row_dup = rh.build_row("2026-06-28", readiness=_readiness(score=99, band="high"))
    csv2 = rh.append_row(csv1, row_dup)
    assert csv2 == csv1
    parsed = list(__import__("csv").DictReader(io.StringIO(csv2)))
    assert len(parsed) == 1
    assert parsed[0]["readiness_score"] == "72"     # original kept, not overwritten


def test_append_preserves_history_and_order():
    csv0 = _header_only_csv()
    csv1 = rh.append_row(csv0, rh.build_row("2026-06-27", readiness=_readiness(score=60)))
    csv2 = rh.append_row(csv1, rh.build_row("2026-06-28", readiness=_readiness(score=72)))
    parsed = list(__import__("csv").DictReader(io.StringIO(csv2)))
    assert [p["date"] for p in parsed] == ["2026-06-27", "2026-06-28"]
    assert [p["readiness_score"] for p in parsed] == ["60", "72"]


def test_append_row_requires_date():
    with pytest.raises(ValueError):
        rh.append_row(_header_only_csv(), {"readiness_score": 70})


# --------------------------------------------------------------------------- #
# run_history orchestrator against a fake pull_drive (no real Drive)
# Copied from tests/test_archive.py::_FakeDrive
# --------------------------------------------------------------------------- #
class _FakeDrive:
    """Minimal stand-in: a folder is a dict {name: text}. Tracks if create ran."""

    def __init__(self, files):
        self.files = dict(files)  # name -> text
        self.created = False
        self.updated = False


def _install_fake(monkeypatch, fake):
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

    def _download(svc, file_id, dest):
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


def test_missing_csv_errors_and_never_creates(monkeypatch, tmp_path, capsys):
    fake = _FakeDrive({})  # empty folder -> CSV absent
    _install_fake(monkeypatch, fake)

    row = rh.build_row("2026-06-28", readiness=_readiness())
    with pytest.raises(SystemExit) as exc:
        rh.run_history(
            row_dict=row,
            csv_name="readiness-history.csv",
            folder_id="FOLDER",
            out_dir=str(tmp_path),
        )
    assert exc.value.code != 0
    assert fake.created is False  # we NEVER create the file
    err = capsys.readouterr().err
    assert "PRE-SEED" in err
    assert "readiness-history.csv" in err


def test_present_csv_appends_via_update(monkeypatch, tmp_path):
    seed = ",".join(rh.HEADER) + "\n"
    fake = _FakeDrive({"readiness-history.csv": seed})
    _install_fake(monkeypatch, fake)

    row = rh.build_row("2026-06-28", readiness=_readiness(score=72),
                       body_battery=_body_battery(), banister=_banister(),
                       hrv_baseline=_hrv_baseline())
    fid = rh.run_history(
        row_dict=row,
        csv_name="readiness-history.csv",
        folder_id="FOLDER",
        out_dir=str(tmp_path),
    )
    assert fid == "id::readiness-history.csv"
    assert fake.updated is True
    assert fake.created is False
    final = fake.files["readiness-history.csv"]
    parsed = list(__import__("csv").DictReader(io.StringIO(final)))
    assert len(parsed) == 1
    assert parsed[0]["date"] == "2026-06-28"
    assert parsed[0]["readiness_score"] == "72"


def test_present_csv_same_date_upload_is_noop(monkeypatch, tmp_path):
    seed = ",".join(rh.HEADER) + "\n2026-06-28,72,moderate,balanced,70,42,-4.2,sleep\n"
    fake = _FakeDrive({"readiness-history.csv": seed})
    _install_fake(monkeypatch, fake)

    row = rh.build_row("2026-06-28", readiness=_readiness(score=99, band="high"))
    rh.run_history(
        row_dict=row,
        csv_name="readiness-history.csv",
        folder_id="FOLDER",
        out_dir=str(tmp_path),
    )
    # Idempotent: still one data row, original values intact.
    parsed = list(__import__("csv").DictReader(io.StringIO(fake.files["readiness-history.csv"])))
    assert len(parsed) == 1
    assert parsed[0]["readiness_score"] == "72"


# --------------------------------------------------------------------------- #
# CLI: bad --as-of -> non-zero + JSON error object
# --------------------------------------------------------------------------- #
def test_main_bad_as_of_json_error(capsys):
    rc = rh.main(["--as-of", "2026-13-40"])
    assert rc == 1
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert "error" in obj
