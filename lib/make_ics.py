#!/usr/bin/env python3
"""make_ics.py — V3 training-plan → Apple-Calendar .ics (hand-rolled, NO icalendar lib).

WHY: turn Senpai's stable weekly rhythm (``athlete.md`` → ## Wochen-Rhythmus) plus the
live race calendar (``live.md`` → ## Race-Countdown) into a single importable .ics:
  * recurring weekly VEVENTs (RRULE:FREQ=WEEKLY;BYDAY=…) for the training days,
  * one-off VEVENTs for each dated race.

DATA-FLOW: pulls the two markdown files from the personal Drive folder via
``lib/pull_drive.py`` into ``./data`` (only the curated state, never raw series), then
parses them. Both the rhythm and the race list are tolerant to the markdown shape, and
can be fully overridden for testing via ``--rhythm`` / ``--races`` (so the generator is
unit-testable with zero Drive access and zero personal data).

CLI:
  python lib/make_ics.py --out ./data/senpai-plan.ics [--weeks 8]
  # offline / test (no Drive):
  python lib/make_ics.py --out plan.ics \\
      --rhythm "Mo=Run+Core@20:00;Mi=Long Run@18:00;Do=Gym@21:30;Sa=Parkrun@09:00" \\
      --races  "Stadtlauf 6km|2026-07-21@09:00"

Override grammar (semicolon-separated):
  --rhythm  DAY=Title@HH:MM[;…]      DAY ∈ Mo Di Mi Do Fr Sa So (German abbrevs)
  --races   Title|YYYY-MM-DD[@HH:MM][;…]

The .ics uses floating local time (no TZID) so Apple Calendar files the events in the
device's own timezone — robust for a single-user, single-timezone athlete.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

# Personal Drive folder "Senpai-AI-Chat" (state only — never raw data).
DEFAULT_FOLDER = "1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde"

# German weekday abbrev → (ICS BYDAY token, python weekday index Mon=0).
DAY_MAP = {
    "mo": ("MO", 0), "di": ("TU", 1), "mi": ("WE", 2), "do": ("TH", 3),
    "fr": ("FR", 4), "sa": ("SA", 5), "so": ("SU", 6),
}
# Plain-language rest markers → no event.
_REST_RE = re.compile(r"\brest\b", re.I)
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
# A race line carries a DD.MM.YYYY (or YYYY-MM-DD) date; "Datum TBC" lines are skipped.
_RACE_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})|(\d{4})-(\d{1,2})-(\d{1,2})")
_KM_RE = re.compile(r"\(?\s*(\d+(?:[.,]\d+)?)\s*km\b", re.I)

# Default start time / duration per day when the rhythm text omits an explicit clock.
_DAY_DEFAULT_TIME = {
    "mo": (20, 0), "mi": (18, 0), "do": (21, 30), "sa": (9, 0),
}
_DEFAULT_DUR_MIN = 60
_RACE_DUR_MIN = 75


# ─────────────────────────── Drive pull ───────────────────────────
def pull_state(folder: str, out_dir: Path, sa_file: str | None) -> dict[str, Path]:
    """Pull athlete.md + live.md from Drive into ``out_dir`` via pull_drive.py.

    Returns a dict {name: local_path}. Missing files are simply absent (the caller
    falls back to overrides / local copies), so this never hard-fails the generator.
    """
    here = Path(__file__).resolve().parent
    pull = here / "pull_drive.py"
    found: dict[str, Path] = {}
    for name in ("athlete.md", "live.md"):
        cmd = [sys.executable, str(pull), "--folder", folder, "--match", name,
               "--newest", "--out", str(out_dir)]
        if sa_file:
            cmd += ["--sa-file", sa_file]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except Exception as e:  # noqa: BLE001 — Drive optional; fall back to local
            print(f"WARNING: pull {name} failed: {e!r}", file=sys.stderr)
            continue
        if r.returncode == 0 and r.stdout.strip():
            found[name] = Path(r.stdout.strip().splitlines()[-1])
        else:
            print(f"WARNING: pull {name} rc={r.returncode}: {r.stderr.strip()[:200]}",
                  file=sys.stderr)
    return found


# ─────────────────────────── parsing ───────────────────────────
def _section(md: str, header_substr: str) -> str:
    """Return the body of the first ``## …`` section whose header contains the substr."""
    lines = md.splitlines()
    out, capturing = [], False
    for ln in lines:
        if ln.lstrip().startswith("## "):
            if capturing:
                break
            capturing = header_substr.lower() in ln.lower()
            continue
        if capturing:
            out.append(ln)
    return "\n".join(out)


def parse_rhythm_md(md: str) -> list[dict]:
    """Parse the ## Wochen-Rhythmus markdown table → training-day events.

    Each table row is ``| **Mo** | <plan text> |``. Rest days (plan matches /rest/)
    produce no event. The title is the de-cluttered plan text; the time is the first
    HH:MM found, else a per-day default.
    """
    body = _section(md, "Wochen-Rhythmus") or md
    events: list[dict] = []
    for ln in body.splitlines():
        ln = ln.strip()
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 2:
            continue
        day_raw = re.sub(r"[*`]", "", cells[0]).strip().lower()[:2]
        if day_raw not in DAY_MAP:
            continue  # header / separator row
        plan = re.sub(r"[*`]", "", cells[1]).strip()
        if not plan or _REST_RE.search(plan):
            continue
        ev = _rhythm_event(day_raw, plan)
        if ev:
            events.append(ev)
    return events


def _clean_title(plan: str) -> str:
    """Shorten a noisy plan cell to a calendar-friendly title."""
    t = plan.split("(")[0]                 # drop first parenthetical aside
    t = re.sub(r"≤\s*\d{1,2}:\d{2}", "", t)  # drop "≤21:30"
    t = re.sub(r"\d{1,2}:\d{2}", "", t)      # drop explicit clock
    t = re.sub(r"\s+", " ", t).strip(" +-—·")
    return t or plan.strip()


def _rhythm_event(day_raw: str, plan: str) -> dict | None:
    byday, _ = DAY_MAP[day_raw]
    m = _TIME_RE.search(plan)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
    else:
        hh, mm = _DAY_DEFAULT_TIME.get(day_raw, (18, 0))
    return {
        "day": day_raw, "byday": byday, "hh": hh, "mm": mm,
        "title": f"🏃 {_clean_title(plan)}", "dur_min": _DEFAULT_DUR_MIN,
    }


def parse_rhythm_override(spec: str) -> list[dict]:
    """``Mo=Run+Core@20:00;Mi=Long Run@18:00;…`` → training-day events."""
    events = []
    for part in spec.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        day, rest = part.split("=", 1)
        day = day.strip().lower()[:2]
        if day not in DAY_MAP:
            continue
        title, _, clock = rest.partition("@")
        if _REST_RE.search(title):
            continue
        m = _TIME_RE.search(clock)
        ev = _rhythm_event(day, f"{title.strip()} {clock.strip()}".strip())
        if not m:  # no clock given → fall back to per-day default
            ev["title"] = f"🏃 {_clean_title(title.strip())}"
        events.append(ev)
    return events


def parse_races_md(md: str) -> list[dict]:
    """Parse the ## Race-Countdown section → one-off dated race events.

    Lines without a full DD.MM.YYYY / YYYY-MM-DD date (e.g. "Datum TBC") are skipped.
    """
    body = _section(md, "Race-Countdown") or md
    races: list[dict] = []
    for ln in body.splitlines():
        d = _parse_race_date(ln)
        if not d:
            continue
        title = re.sub(r"[*`>]", "", ln).strip().lstrip("-· ").strip()
        title = re.split(r"→|—\s*\d|\bZiel\b", title)[0].strip(" —-·")
        km = None
        mk = _KM_RE.search(ln)
        if mk:
            km = float(mk.group(1).replace(",", "."))
        m = _TIME_RE.search(ln)
        hh, mm = (int(m.group(1)), int(m.group(2))) if m else (9, 0)
        races.append({"date": d, "title": f"🏁 {title}", "km": km,
                      "hh": hh, "mm": mm, "dur_min": _RACE_DUR_MIN})
    return races


def _parse_race_date(text: str) -> dt.date | None:
    m = _RACE_DATE_RE.search(text)
    if not m:
        return None
    try:
        if m.group(1):  # DD.MM.YYYY
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return dt.date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
    except ValueError:
        return None


def parse_races_override(spec: str) -> list[dict]:
    """``Title|YYYY-MM-DD[@HH:MM];…`` → one-off race events."""
    races = []
    for part in spec.split(";"):
        part = part.strip()
        if not part or "|" not in part:
            continue
        title, datespec = part.split("|", 1)
        d = _parse_race_date(datespec)
        if not d:
            continue
        m = _TIME_RE.search(datespec)
        hh, mm = (int(m.group(1)), int(m.group(2))) if m else (9, 0)
        km = None
        mk = _KM_RE.search(title)
        if mk:
            km = float(mk.group(1).replace(",", "."))
        races.append({"date": d, "title": f"🏁 {title.strip()}", "km": km,
                      "hh": hh, "mm": mm, "dur_min": _RACE_DUR_MIN})
    return races


# ─────────────────────────── ICS emit ───────────────────────────
def _next_weekday(start: dt.date, py_weekday: int) -> dt.date:
    """First date >= start that falls on py_weekday (Mon=0)."""
    delta = (py_weekday - start.weekday()) % 7
    return start + dt.timedelta(days=delta)


def _fmt_local(d: dt.date, hh: int, mm: int) -> str:
    """Floating local time (no Z, no TZID) — Apple files it in the device tz."""
    return f"{d:%Y%m%d}T{hh:02d}{mm:02d}00"


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC5545 line folding at 75 octets (Apple-tolerant; ASCII-safe approximation)."""
    if len(line) <= 75:
        return line
    out, rest = [line[:75]], line[75:]
    while rest:
        out.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(out)


def build_ics(events: list[dict], races: list[dict], weeks: int = 8,
              start: dt.date | None = None, now: dt.datetime | None = None) -> str:
    """Assemble the full VCALENDAR text. ``weeks`` bounds the weekly RRULE COUNT."""
    start = start or dt.date.today()
    now = now or dt.datetime.now()
    stamp = f"{now:%Y%m%dT%H%M%S}"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Senpai AI Coach//V3 Training Plan//DE",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:Senpai V3 Plan",
    ]
    seq = 0
    for ev in events:
        _, pyw = DAY_MAP[ev["day"]]
        first = _next_weekday(start, pyw)
        dtstart = _fmt_local(first, ev["hh"], ev["mm"])
        end_dt = dt.datetime(first.year, first.month, first.day, ev["hh"], ev["mm"]) \
            + dt.timedelta(minutes=ev["dur_min"])
        dtend = _fmt_local(end_dt.date(), end_dt.hour, end_dt.minute)
        seq += 1
        uid = f"senpai-rhythm-{ev['day']}-{seq}@senpai"
        lines += [
            "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
            f"DTSTART:{dtstart}", f"DTEND:{dtend}",
            f"RRULE:FREQ=WEEKLY;BYDAY={ev['byday']};COUNT={weeks}",
            _fold(f"SUMMARY:{_ics_escape(ev['title'])}"),
            "CATEGORIES:Training",
            "END:VEVENT",
        ]
    for rc in races:
        dtstart = _fmt_local(rc["date"], rc["hh"], rc["mm"])
        end_dt = dt.datetime(rc["date"].year, rc["date"].month, rc["date"].day,
                             rc["hh"], rc["mm"]) + dt.timedelta(minutes=rc["dur_min"])
        dtend = _fmt_local(end_dt.date(), end_dt.hour, end_dt.minute)
        seq += 1
        uid = f"senpai-race-{rc['date']:%Y%m%d}-{seq}@senpai"
        desc = "V3 race day."
        if rc.get("km"):
            desc = f"V3 race day — {rc['km']:g} km."
        lines += [
            "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
            f"DTSTART:{dtstart}", f"DTEND:{dtend}",
            _fold(f"SUMMARY:{_ics_escape(rc['title'])}"),
            _fold(f"DESCRIPTION:{_ics_escape(desc)}"),
            "CATEGORIES:Race",
            "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-P1D",
            _fold(f"DESCRIPTION:{_ics_escape(rc['title'])} morgen"),
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ─────────────────────────── CLI ───────────────────────────
def _resolve_inputs(args) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    races: list[dict] = []
    if args.rhythm:
        events = parse_rhythm_override(args.rhythm)
    if args.races:
        races = parse_races_override(args.races)
    if events and (races or not args.want_drive):
        return events, races

    # Otherwise pull (or read local) the markdown state.
    data_dir = Path(args.data)
    paths: dict[str, Path] = {}
    if args.want_drive:
        paths = pull_state(args.folder, data_dir, args.sa_file)
    # Local fallback (committed synthetic seed or a previous pull).
    for name in ("athlete.md", "live.md"):
        if name not in paths:
            for cand in (data_dir / name, data_dir / "senpai-drive-seed" / name):
                if cand.is_file():
                    paths[name] = cand
                    break
    if not events and "athlete.md" in paths:
        events = parse_rhythm_md(paths["athlete.md"].read_text(encoding="utf-8"))
    if not races and "live.md" in paths:
        races = parse_races_md(paths["live.md"].read_text(encoding="utf-8"))
    return events, races


def main(argv=None):
    p = argparse.ArgumentParser(description="V3 weekly rhythm + races → Apple-Calendar .ics")
    p.add_argument("--out", default="./data/senpai-plan.ics", help="output .ics path")
    p.add_argument("--weeks", type=int, default=8, help="how many weeks the weekly events repeat")
    p.add_argument("--folder", default=DEFAULT_FOLDER, help="Drive folder ID for state pull")
    p.add_argument("--data", default="./data", help="dir to pull/read athlete.md + live.md")
    p.add_argument("--sa-file", help="service-account JSON (else env)")
    p.add_argument("--rhythm", help="override: 'Mo=Run+Core@20:00;Mi=Long Run@18:00;…'")
    p.add_argument("--races", help="override: 'Title 6km|2026-07-21@09:00;…'")
    p.add_argument("--no-drive", dest="want_drive", action="store_false",
                   help="do not hit Drive; use local ./data copies / overrides only")
    p.add_argument("--start", help="weekly-recurrence start date YYYY-MM-DD (default: today)")
    args = p.parse_args(argv)

    start = dt.date.fromisoformat(args.start) if args.start else None
    events, races = _resolve_inputs(args)
    if not events and not races:
        print("ERROR: no training days or races resolved (check Drive / --rhythm / --races)",
              file=sys.stderr)
        return 1
    ics = build_ics(events, races, weeks=args.weeks, start=start)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ics, encoding="utf-8")
    n_vevent = ics.count("BEGIN:VEVENT")
    print(f"{out}  ({len(events)} weekly + {len(races)} race = {n_vevent} VEVENTs, "
          f"{args.weeks} weeks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
