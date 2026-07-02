"""Tests für lib/preflight.py — Credential-Parsing ohne Netz.

DATA-FREE: synthetische (ungültige/valide-strukturierte) Credentials via Env.
Der echte Key-Load wird nicht getestet (bräuchte einen echten Private Key) —
wohl aber jede Fehlklassifikation, die der Preflight benennen soll.
"""

import base64
import json
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import preflight as pf  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("GOOGLE_SERVICE_ACCOUNT_B64", "GOOGLE_SERVICE_ACCOUNT_JSON",
                "GOOGLE_SERVICE_ACCOUNT_FILE"):
        monkeypatch.delenv(var, raising=False)


def test_no_credential_is_a_clear_error():
    with pytest.raises(ValueError, match="No service-account credential"):
        pf._load_sa_info()


def test_b64_not_base64(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_B64", "%%%not-base64%%%")
    with pytest.raises(ValueError, match="not valid base64"):
        pf._load_sa_info()


def test_b64_decodes_but_not_json(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_B64",
                       base64.b64encode(b"hello world").decode())
    with pytest.raises(ValueError, match="NOT JSON"):
        pf._load_sa_info()


def test_b64_valid_json_roundtrip(monkeypatch):
    info = {"type": "service_account", "client_email": "x@y", "private_key": "k",
            "token_uri": "https://t"}
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_B64",
                       base64.b64encode(json.dumps(info).encode()).decode())
    data, source = pf._load_sa_info()
    assert data["type"] == "service_account"
    assert source == "GOOGLE_SERVICE_ACCOUNT_B64"


def test_json_env_wrong_type(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps([1, 2, 3]))
    with pytest.raises(ValueError, match="not an object"):
        pf._load_sa_info()


def test_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(tmp_path / "nope.json"))
    with pytest.raises(ValueError, match="missing file"):
        pf._load_sa_info()


def test_main_never_blocks_session(monkeypatch, capsys):
    # Kein Credential → lauter Banner, aber IMMER Exit 0 (warnt, blockt nie).
    assert pf.main() == 0
    out = capsys.readouterr().out
    assert "PREFLIGHT FAILED" in out
