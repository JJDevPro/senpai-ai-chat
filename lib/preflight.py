#!/usr/bin/env python3
"""SessionStart preflight for senpai-ai-chat (Claude Code on the web).

Why this exists: every skill pulls identity + state from Drive via lib/pull_drive.py.
If the Python crypto stack is incomplete, or the GOOGLE_SERVICE_ACCOUNT_B64 secret is
in the wrong format, the pull dies DEEP inside google-auth with an opaque traceback —
and it dies once per skill, silently, burning a whole session before anyone notices.
(Seen in the wild: `No module named '_cffi_backend'`, then a JSONDecodeError because
the secret base64-decodes to something that is not the service-account JSON.)

This script runs ONCE at SessionStart and turns those late, cryptic failures into a
single loud, actionable banner. It is READ-ONLY and makes NO network call: it only
checks locally that (a) the deps import and (b) the credential decodes to a valid
service-account object. It ALWAYS exits 0 — it warns, it never blocks the session.

Run standalone any time:  python3 lib/preflight.py
"""
from __future__ import annotations

import base64
import json
import os

REQUIRED_SA_KEYS = ("type", "client_email", "private_key", "token_uri")
SCOPES_RO = ["https://www.googleapis.com/auth/drive.readonly"]
BANNER = "=" * 66


def _as_dict(obj, label):
    if not isinstance(obj, dict):
        raise ValueError(f"{label} parses as JSON but is a {type(obj).__name__}, not an object.")
    return obj


def _load_sa_info():
    """Return (info_dict, source_label) or raise ValueError with a human reason.

    Mirrors the credential precedence in lib/pull_drive.py: B64 -> JSON -> FILE.
    """
    b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT_B64")
    if b64:
        try:
            raw = base64.b64decode(b64)
        except Exception as e:
            raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_B64 is not valid base64 ({e}).")
        try:
            data = json.loads(raw)
        except Exception:
            raise ValueError(
                f"GOOGLE_SERVICE_ACCOUNT_B64 base64-decodes ({len(raw)} bytes) but is NOT JSON. "
                "It must be the raw service-account JSON, base64-encoded exactly once: "
                "`base64 -i service-account.json | tr -d '\\n'` — no extra wrapping/encryption."
            )
        return _as_dict(data, "GOOGLE_SERVICE_ACCOUNT_B64"), "GOOGLE_SERVICE_ACCOUNT_B64"

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        try:
            data = json.loads(raw)
        except Exception:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is set but is not valid JSON.")
        return _as_dict(data, "GOOGLE_SERVICE_ACCOUNT_JSON"), "GOOGLE_SERVICE_ACCOUNT_JSON"

    path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if path:
        if not os.path.isfile(path):
            raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_FILE points at a missing file: {path}")
        try:
            with open(path) as fh:
                data = json.load(fh)
        except Exception as e:
            raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_FILE is not valid JSON ({e}).")
        return _as_dict(data, f"GOOGLE_SERVICE_ACCOUNT_FILE ({path})"), f"file {path}"

    raise ValueError(
        "No service-account credential set. Provide GOOGLE_SERVICE_ACCOUNT_B64 "
        "(base64 of the service-account JSON) in the environment config."
    )


def main():
    problems = []

    # 1) Are the Drive deps importable? (catches the missing-_cffi_backend class of break.)
    deps_ok = True
    try:
        import google.oauth2.service_account  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
    except Exception as e:
        deps_ok = False
        problems.append(
            f"Python Drive deps not importable: {e}. "
            "Fix: pip install --use-pep517 -r requirements.txt"
        )

    # 2) Does a credential exist and parse to a service-account object?
    info = source = None
    try:
        info, source = _load_sa_info()
    except ValueError as e:
        problems.append(str(e))

    # 3) Required keys + a real (local, no-network) credentials build to validate the key.
    if info is not None:
        missing = [k for k in REQUIRED_SA_KEYS if k not in info]
        if missing:
            problems.append(f"Credential JSON is missing required keys: {', '.join(missing)}.")
        elif info.get("type") != "service_account":
            problems.append(
                f"Credential 'type' is {info.get('type')!r}, expected 'service_account'."
            )
        elif deps_ok:
            try:
                from google.oauth2 import service_account

                service_account.Credentials.from_service_account_info(info, scopes=SCOPES_RO)
            except Exception as e:
                problems.append(f"Credential present but the private key will not load: {e}")

    if problems:
        print(BANNER)
        print("⛔ SENPAI PREFLIGHT FAILED — Drive pulls will NOT work this session.")
        for p in problems:
            print("   • " + p)
        print("   → Fix the environment config, then start a FRESH session.")
        print("   → Until then: do NOT fabricate athlete state — say the pull is down.")
        print(BANNER)
        return 0  # warn loudly, never block the session

    print(f"✅ Senpai preflight OK — Drive deps import, credential parses ({source}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
