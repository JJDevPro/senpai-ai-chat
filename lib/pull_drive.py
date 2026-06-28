#!/usr/bin/env python3
"""Google Drive bridge for senpai-ai-chat (read truth + read/write personal state).

Why this exists: in Claude Code on the web the session runs in an ephemeral cloud VM.
NOTHING personal lives in the git repo. The truth data (Health Auto Export JSON,
Garmin/HealthFit .fit, Trainings_v5, Gesundheitsdaten_v5) AND Senpai's curated state +
personal knowledge modules live in Google Drive. This script pulls what's needed onto
the VM disk (so only computed AGGREGATES enter the model context, never raw series),
and can WRITE the updated Senpai state back to the private `senpai-ai-chat` Drive folder.

Auth scopes:
  - reads  -> drive.readonly
  - --upload -> drive (read-write); the service-account must have write access to the
    target folder (only the senpai-ai-chat state folder; the truth sheets stay read-only).
Credentials (in order): env GOOGLE_SERVICE_ACCOUNT_B64 (base64 of JSON — use this in the
cloud env, .env-format can't hold multi-line JSON), env GOOGLE_SERVICE_ACCOUNT_JSON (raw),
env GOOGLE_SERVICE_ACCOUNT_FILE (path), or --sa-file.
  base64 -i service-account.json | tr -d '\\n'   # produce the B64 value (macOS)

CLI contract (used verbatim by the skills + CLAUDE.md):
  # newest file in a folder whose name contains a substring (+ optional extension):
  python3 lib/pull_drive.py --folder <ID> --match "Laufen outdoor" --ext .fit --newest --out ./data
  # a specific Health Auto Export day file:
  python3 lib/pull_drive.py --folder <ID> --match "HealthAutoExport-2026-06-24" --out ./data
  # list matches (name<TAB>id<TAB>modifiedTime), download nothing:
  python3 lib/pull_drive.py --folder <ID> --match "HealthAutoExport-" --list
  # read ONE tab of a Google Sheet to CSV (tab pinned BY NAME via the Sheets API;
  # Drive files.export(csv) fallback only if the Sheets API call fails):
  python3 lib/pull_drive.py --sheet <SHEET_ID> --tab "Trainings" --out ./data/Trainings_v5.csv
  # WRITE/UPDATE a file in the personal state folder (create or overwrite by name):
  python3 lib/pull_drive.py --upload ./data/senpai-state.md --folder <STATE_FOLDER_ID> [--name senpai-state.md]

Prints local path(s) on read, or the Drive file id on --upload. Never prints file contents.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

SCOPES_RO = ["https://www.googleapis.com/auth/drive.readonly"]
SCOPES_RW = ["https://www.googleapis.com/auth/drive"]
# --sheet reads use the Sheets API (tab-by-name, structured) with a Drive-export
# CSV fallback, so they need BOTH the spreadsheets-read and drive-read scopes.
SCOPES_SHEET = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _eprint(*a):
    print(*a, file=sys.stderr)


def _load_credentials(sa_file, scopes):
    try:
        from google.oauth2 import service_account
    except Exception as e:  # pragma: no cover
        _eprint("ERROR: google-auth not installed. pip install google-auth google-api-python-client")
        raise SystemExit(2) from e

    b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT_B64")
    if b64:
        import base64

        info = json.loads(base64.b64decode(b64))
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)

    path = sa_file or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if path and Path(path).is_file():
        return service_account.Credentials.from_service_account_file(path, scopes=scopes)

    _eprint(
        "ERROR: no service-account credentials. Set GOOGLE_SERVICE_ACCOUNT_B64 (base64 JSON), "
        "GOOGLE_SERVICE_ACCOUNT_JSON (raw), GOOGLE_SERVICE_ACCOUNT_FILE (path), or --sa-file."
    )
    raise SystemExit(2)


def _drive(creds):
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _sheets(creds):
    from googleapiclient.discovery import build

    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _q_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _list_matches(svc, folder_id, match, ext):
    clauses = [f"'{_q_escape(folder_id)}' in parents", "trashed = false"]
    if match:
        clauses.append(f"name contains '{_q_escape(match)}'")
    q = " and ".join(clauses)
    files, page = [], None
    while True:
        resp = (
            svc.files()
            .list(
                q=q,
                orderBy="modifiedTime desc",
                fields="nextPageToken, files(id, name, modifiedTime, mimeType, size)",
                pageSize=200,
                pageToken=page,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        page = resp.get("nextPageToken")
        if not page:
            break
    if ext:
        e = ext.lower()
        files = [f for f in files if f["name"].lower().endswith(e)]
    return files


def _download_media(svc, file_id, dest: Path):
    from googleapiclient.http import MediaIoBaseDownload

    req = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with io.FileIO(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = dl.next_chunk()


def _first_sheet_title(sheets_svc, spreadsheet_id):
    """Fetch the title of the FIRST tab via spreadsheets.get (used if --tab omitted)."""
    meta = (
        sheets_svc.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties(title,index)")
        .execute()
    )
    sheets = sorted(
        meta.get("sheets", []),
        key=lambda s: s.get("properties", {}).get("index", 0),
    )
    if not sheets:
        raise RuntimeError("spreadsheet has no sheets")
    return sheets[0]["properties"]["title"]


def _read_sheet_via_api(sheets_svc, spreadsheet_id, tab, dest: Path):
    """
    Read exactly ONE tab BY NAME via the Sheets API and write it as a proper CSV.

    Pins the tab by name (no silent first-tab / reorder hazard like Drive
    files.export), returns structured rows with a single deterministic render
    option (UNFORMATTED_VALUE + FORMATTED_STRING for dates). Returns the tab
    title actually read.
    """
    import csv

    if not tab:
        tab = _first_sheet_title(sheets_svc, spreadsheet_id)
    rng = f"{tab}!A:Z"
    resp = (
        sheets_svc.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=rng,
            valueRenderOption="UNFORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
        )
        .execute()
    )
    rows = resp.get("values", [])
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for row in rows:
            w.writerow(["" if c is None else c for c in row])
    return tab, len(rows)


def _export_sheet_csv(svc, file_id, dest: Path):
    """FALLBACK: Drive files.export(text/csv). Returns ONLY the first tab and is
    format-/tab-order-sensitive — used only if the Sheets-API read fails."""
    from googleapiclient.http import MediaIoBaseDownload

    req = svc.files().export_media(fileId=file_id, mimeType="text/csv")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with io.FileIO(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = dl.next_chunk()


def _upload(svc, local_path, folder_id, name=None):
    """Create or overwrite (by name, within the folder) a file in Drive. Returns file id."""
    from googleapiclient.http import MediaFileUpload

    local = Path(local_path)
    if not local.is_file():
        _eprint(f"ERROR: --upload file not found: {local}")
        raise SystemExit(1)
    name = name or local.name
    existing = _list_matches(svc, folder_id, name, None)
    exact = [f for f in existing if f["name"] == name]
    media = MediaFileUpload(str(local), resumable=False)
    if exact:
        fid = exact[0]["id"]
        svc.files().update(fileId=fid, media_body=media, supportsAllDrives=True).execute()
        return fid
    meta = {"name": name, "parents": [folder_id]}
    created = svc.files().create(
        body=meta, media_body=media, fields="id", supportsAllDrives=True
    ).execute()
    return created["id"]


def main(argv=None):
    p = argparse.ArgumentParser(description="Drive bridge: read truth (RO) + read/write personal state.")
    p.add_argument("--folder", help="Drive folder ID")
    p.add_argument("--match", help="substring the file name must contain")
    p.add_argument("--ext", help="filter to this extension, e.g. .fit / .json")
    p.add_argument("--newest", action="store_true", help="download only the newest match")
    p.add_argument("--all", action="store_true", help="download all matches")
    p.add_argument("--list", action="store_true", help="list matches, download nothing")
    p.add_argument("--sheet", help="Google Sheet ID to read as CSV (with --out FILE)")
    p.add_argument("--tab", help="sheet tab/worksheet name to read (--sheet); default = first tab")
    p.add_argument("--upload", help="local file to create/overwrite in --folder (write)")
    p.add_argument("--name", help="target Drive name for --upload (default: local basename)")
    p.add_argument("--out", default="./data", help="output dir (reads) or file path (--sheet)")
    p.add_argument("--sa-file", help="path to service-account JSON (else env)")
    args = p.parse_args(argv)

    # --- write path ---
    if args.upload:
        if not args.folder:
            _eprint("ERROR: --upload needs --folder (the personal state folder)")
            return 2
        creds = _load_credentials(args.sa_file, SCOPES_RW)
        svc = _drive(creds)
        fid = _upload(svc, args.upload, args.folder, args.name)
        print(fid)
        return 0

    # --- Google Sheet -> CSV (Sheets API, tab-by-name; Drive-export fallback) ---
    if args.sheet:
        out = Path(args.out)
        if out.suffix.lower() != ".csv":
            out = out / f"{args.sheet}.csv"
        creds = _load_credentials(args.sa_file, SCOPES_SHEET)
        try:
            tab, nrows = _read_sheet_via_api(_sheets(creds), args.sheet, args.tab, out)
            _eprint(f"INFO: read tab {tab!r} via Sheets API ({nrows} rows) -> {out}")
        except Exception as e:
            _eprint(f"WARNING: Sheets API read failed ({e!r}); falling back to Drive export(csv) — first tab only")
            _export_sheet_csv(_drive(creds), args.sheet, out)
        print(str(out))
        return 0

    creds = _load_credentials(args.sa_file, SCOPES_RO)
    svc = _drive(creds)

    if not args.folder:
        _eprint("ERROR: need --folder (+ --match), --sheet, or --upload")
        return 2

    matches = _list_matches(svc, args.folder, args.match, args.ext)
    if not matches:
        _eprint(f"ERROR: no files in folder {args.folder} matching match={args.match!r} ext={args.ext!r}")
        return 1

    if args.list:
        for f in matches:
            print(f"{f['name']}\t{f['id']}\t{f.get('modifiedTime','')}")
        return 0

    out_dir = Path(args.out)
    selected = matches if args.all else [matches[0]]  # newest-first
    if not args.all and not args.newest and len(matches) > 1:
        _eprint(
            f"WARNING: {len(matches)} files match; downloading newest "
            f"({matches[0]['name']}). Use --all or a tighter --match to change."
        )
    for f in selected:
        dest = out_dir / f["name"]
        _download_media(svc, f["id"], dest)
        print(str(dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
