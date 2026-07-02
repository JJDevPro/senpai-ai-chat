#!/usr/bin/env python3
"""Append a finished Senpai report to a rolling Drive journal (coaching history).

Why this exists: every Daily-Check / Run-Analyse / Weekly / Payload produces a
verdict that is worth keeping as a searchable, dated coaching log. Instead of
scattering files, we keep ONE markdown journal in the private `Senpai-AI-Chat`
Drive folder and *append* each report as a clearly-delimited dated section.

HARD CONSTRAINT (verified): the service-account has NO My-Drive quota, so it can
only UPDATE an already-existing, user-owned file — it can NOT create one. The
journal therefore must be PRE-SEEDED once by the user (drop an empty
`senpai-journal.md` into the folder). If it is missing, this script prints a
clear instruction and exits non-zero — it never tries to create it.

Flow:
  1. pull the current journal from the folder (lib/pull_drive.py read path)
  2. append "## [kind] YYYY-MM-DD\n<report>\n" (pure, testable: append_section)
  3. upload it back (lib/pull_drive.py --upload -> Drive files.update on the
     existing file). Because the file already exists, this is an UPDATE.

CLI:
  python3 lib/archive.py --report <file|-> --kind daily|run|weekly|payload \
      [--date YYYY-MM-DD] [--journal senpai-journal.md] [--folder <ID>]

The append/format logic (`append_section`) takes only strings and never touches
Drive, so the tests exercise it against local files only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# archive.py lives next to pull_drive.py in lib/ — make it importable either way.
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import clock  # noqa: E402 — Berlin date instead of the VM's UTC date (CLAUDE.md §3)

# The default private state folder (Senpai-AI-Chat). Overridable via --folder.
DEFAULT_FOLDER_ID = "1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde"
DEFAULT_JOURNAL = "senpai-journal.md"
KINDS = ("daily", "run", "weekly", "payload")


def _eprint(*a):
    print(*a, file=sys.stderr)


# --------------------------------------------------------------------------- #
# Pure append/format logic (no Drive, fully unit-testable)
# --------------------------------------------------------------------------- #
def format_section(kind: str, day: str, report: str) -> str:
    """Render one journal section: a delimited, dated header + the report body.

    The body is stripped of trailing whitespace and the section is newline-framed
    so successive appends stay readable and grep-able (one header per report).
    """
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    body = report.strip("\n")
    return f"## [{kind}] {day}\n{body}\n"


def append_section(journal: str, kind: str, day: str, report: str) -> str:
    """Append a new section to existing journal text, returning the new text.

    Guarantees exactly one blank line between the previous content and the new
    section header (and no leading blank line on an empty/whitespace journal).
    """
    section = format_section(kind, day, report)
    head = (journal or "").rstrip("\n")
    if head.strip() == "":
        return section
    return f"{head}\n\n{section}"


# --------------------------------------------------------------------------- #
# Drive glue (reuses lib/pull_drive.py)
# --------------------------------------------------------------------------- #
def _read_report(report_arg: str) -> str:
    if report_arg == "-":
        return sys.stdin.read()
    p = Path(report_arg)
    if not p.is_file():
        _eprint(f"ERROR: --report file not found: {p}")
        raise SystemExit(1)
    return p.read_text(encoding="utf-8")


def _preseed_instruction(journal_name: str, folder_id: str) -> str:
    return (
        f"ERROR: journal {journal_name!r} not found in Drive folder {folder_id}.\n"
        f"The service-account has no My-Drive quota and CANNOT create it.\n"
        f"PRE-SEED it ONCE yourself: create an empty file named {journal_name!r}\n"
        f"and drop it into the 'Senpai-AI-Chat' folder (drag-drop in Drive). "
        f"After that, archive.py will keep appending to it automatically."
    )


def run_archive(report_text, kind, day, journal_name, folder_id, out_dir, sa_file=None):
    """Pull journal -> append -> upload back. Returns the Drive file id on success.

    Raises SystemExit(non-zero) with a pre-seed instruction if the journal is
    absent (we never create it).
    """
    import pull_drive as pd

    creds = pd._load_credentials(sa_file, pd.SCOPES_RW)
    svc = pd._drive(creds)

    matches = pd._list_matches(svc, folder_id, journal_name, None)
    exact = [f for f in matches if f["name"] == journal_name]
    if not exact:
        _eprint(_preseed_instruction(journal_name, folder_id))
        raise SystemExit(2)

    fid = exact[0]["id"]
    out = Path(out_dir)
    local = out / journal_name

    # Lost-update guard: with cron automation two writers can interleave
    # (pull -> append -> upload). After uploading, re-download and verify our
    # section header survived; if a concurrent writer clobbered it, re-pull the
    # (now newer) journal and append again — one retry is enough for the
    # realistic two-writer case, and the loop stays bounded + deterministic.
    marker = f"## [{kind}] {day}"
    for attempt in (1, 2):
        pd._download_media(svc, fid, local)
        current = local.read_text(encoding="utf-8")
        updated = append_section(current, kind, day, report_text)
        local.write_text(updated, encoding="utf-8")
        # Upload back: the file exists -> pull_drive._upload does files.update.
        fid = pd._upload(svc, str(local), folder_id, journal_name)
        pd._download_media(svc, fid, local)
        if marker in local.read_text(encoding="utf-8"):
            return fid
        _eprint(f"WARNING: journal append verify failed (attempt {attempt}) — retrying")
    _eprint("ERROR: journal append lost twice (concurrent writer?) — giving up")
    raise SystemExit(3)


def main(argv=None):
    p = argparse.ArgumentParser(description="Append a finished report to the rolling Drive journal.")
    p.add_argument("--report", required=True, help="report file path, or '-' for stdin")
    p.add_argument("--kind", required=True, choices=KINDS, help="report kind")
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--journal", default=DEFAULT_JOURNAL, help=f"journal file name (default: {DEFAULT_JOURNAL})")
    p.add_argument("--folder", default=DEFAULT_FOLDER_ID, help="Drive folder ID (default: Senpai-AI-Chat)")
    p.add_argument("--out", default="./data", help="local scratch dir for the pulled journal")
    p.add_argument("--sa-file", help="path to service-account JSON (else env)")
    args = p.parse_args(argv)

    # Berlin-Kalendertag (nicht UTC): ein 23:30-Report darf nicht als "morgen"
    # (UTC-Datum) im Journal landen.
    day = args.date or clock.local_now().date().isoformat()
    report_text = _read_report(args.report)

    fid = run_archive(
        report_text=report_text,
        kind=args.kind,
        day=day,
        journal_name=args.journal,
        folder_id=args.folder,
        out_dir=args.out,
        sa_file=args.sa_file,
    )
    print(fid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
