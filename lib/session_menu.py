#!/usr/bin/env python3
"""Senpai Action-HUD — zeit-/wochentag-bewusste Aktions-Übersicht bei Session-Start.

Warum: der User hat „nicht immer im Kopf, welche Skills Senpai hat". Diese dritte
SessionStart-Hook-Zeile (nach preflight + bootstrap) mappt `(Wochentag × Zeitfenster)`
auf konkrete nächste Moves + einen Skill-Cheat-Sheet. LEICHTGEWICHT: das HUD
*routet* nur (kein Daten-Pull, keine Aggregat-Rechnung) — die schwere Arbeit bleibt
im Daily-Check / `/briefing`.

PERSONAL-DATA-FREI: hardcodet NUR die generische V3-Wochenstruktur (CLAUDE.md §4)
+ Skill-Trigger. Persönliche Würze (Race-Countdown) liest `--full` zur Laufzeit aus
`./data/live.md` (vom Bootstrap eh gezogen) — generischer Fallback, wenn absent.
NON-BLOCKING: jeder Fehler → still degradieren, exit 0.

CLI:  python3 lib/session_menu.py [--full] [--tz Europe/Berlin] [--now ISO8601] [--out ./data]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import clock  # noqa: E402

DEFAULT_OUT = "./data"
LIVE_NAME = "live.md"

# Generische V3-Wochenstruktur (Methode, keine Identität — Quelle: CLAUDE.md §4).
# slot_hour = ungefähre Slot-Startstunde für die Pre-Slot-Erkennung.
DAYS = {
    0: {"name": "Mo", "type": "Lauf + Core", "slot": "Run (Runna) + Core 20:00",
        "slot_hour": 20, "extra": "SoT-Wiegen nüchtern <09:00", "kw_action": "/sync (KW-Start)"},
    1: {"name": "Di", "type": "Ruhetag", "slot": None,
        "slot_hour": None, "extra": None, "kw_action": None},
    2: {"name": "Mi", "type": "Long Run", "slot": "Long Run (HR≤Z2 / Race-Sim)",
        "slot_hour": 20, "extra": None, "kw_action": None},
    3: {"name": "Do", "type": "Pure Gym", "slot": "Full Body ≤21:30",
        "slot_hour": 21, "extra": None, "kw_action": None},
    4: {"name": "Fr", "type": "Ruhetag", "slot": None,
        "slot_hour": None, "extra": None, "kw_action": None},
    5: {"name": "Sa", "type": "Parkrun + Gym", "slot": "Parkrun 09:00 + Gym Upper/Core",
        "slot_hour": 9, "extra": None, "kw_action": None},
    6: {"name": "So", "type": "Ruhetag", "slot": None,
        "slot_hour": None, "extra": None, "kw_action": "/payload (KW-Abschluss)"},
}

# Skill-/Command-Index (der „was kann Senpai"-Cheat-Sheet).
SKILL_INDEX = [
    ('„daily check" / „status"', "WHOOP-Tages-Dashboard"),
    ('„analysier den Lauf"', "Lauf-Report (FIT)"),
    ('„Gym-Report"', "Krafttraining-Analyse"),
    ('„makro" / „was soll ich essen"', "Ernährung"),
    ('„wetter" / „lauf"', "Wetter + Pre-Lauf"),
    ('„race" / „HM"', "Race-Projektion"),
    ('„Payload"', "Wochen-Export (So)"),
    ('„Sync"', "Rekalibrierung (KW-Start)"),
    ('„Backlog" / „was steht offen"', "offene Vorhaben/Experimente"),
    ("/briefing", "proaktiver Morgen-Flow"),
    ("/menu", "diese Übersicht (voll)"),
]

# Kompakte „immer"-Zeile (Teilmenge).
ALWAYS_COMPACT = '„daily check" · „makro/essen" · „analysier den Lauf" · „wetter" · /menu'

AUTOMATION_HINT = "Automation: inaktiv — /automation arm nach der Testphase"


def day_plan(weekday_idx: int) -> dict:
    """V3-Tagesplan für einen Wochentag (Mo=0 … So=6)."""
    return DAYS[weekday_idx % 7]


def _now_actions(dt, day) -> list[str]:
    """Kontextuelle „jetzt sinnvoll"-Aktionen aus Zeitfenster × Tagestyp."""
    h = dt.hour
    w = clock.time_window(dt)
    is_training = day["slot"] is not None
    acts: list[str] = []

    if w == "morgen":
        acts.append("/briefing (Recovery + Plan)")
        if is_training:
            acts.append('Wetter („wetter")')
        if day["name"] == "Mo":
            acts.append("SoT-Wiegen nüchtern <09:00")
    if 11 <= h < 14:
        acts.append('„makro/essen" (Mittag-Check)')
    # Pre-Slot: Trainingstag + Slot in den nächsten ~2h
    if is_training and day["slot_hour"] is not None and 0 <= day["slot_hour"] - h <= 2:
        acts.append('Pre-Lauf/Gym: „wetter" + Aufwärm-Check')
    # Nach dem Training (Slot durch): abends UND früh-nachts — ein 20:00-Lauf
    # wird oft erst nach 22:00 gemeldet (sonst fiele der Nudge ins „nacht"-Loch).
    if (is_training and day["slot_hour"] is not None
            and h >= day["slot_hour"] and w in ("abend", "nacht")):
        acts.append('nach Training: „analysier den Lauf" / „Gym-Report"')
    if clock.is_bedtime_window(dt):
        acts.append("🌙 Bedtime ≤00:30 — Handy weg")
    if day["name"] == "So":
        acts.append("📦 /payload (KW-Abschluss)")
    if day["name"] == "Mo" and w in ("morgen", "tag"):
        acts.append("/sync (KW-Start)")

    if not acts:
        acts.append("/briefing für den Überblick")
    return acts


def _tomorrow_line(dt) -> str:
    nd = day_plan(dt.weekday() + 1)
    bits = [f"{nd['name']} — {nd['type']}"]
    if nd["slot"]:
        bits.append(nd["slot"])
    if nd["extra"]:
        bits.append(nd["extra"])
    if nd["kw_action"]:
        bits.append("→ " + nd["kw_action"])
    return " · ".join(bits)


def _race_line(live_text: str) -> str | None:
    """Best-effort: erste Zeile unter '## Race-Countdown' aus live.md (--full).

    Reine Anzeige des vorhandenen Texts (kein Datums-Parsing → robust). None,
    wenn nicht ableitbar.
    """
    if not live_text:
        return None
    m = re.search(r"##\s*Race-?Countdown[^\n]*\n", live_text, re.IGNORECASE)
    if not m:
        return None
    for line in live_text[m.end():].splitlines():
        s = line.strip()
        if s.startswith("#"):
            break
        mb = re.match(r"[-*]\s+(.*\S)", s)
        if mb:
            return re.sub(r"\s+", " ", mb.group(1).replace("*", "")).strip()[:90]
    return None


def build_hud(now, athlete_text: str, live_text: str, full: bool = False) -> str:
    """Baue das HUD (kompakt oder voll). PURE: kein Clock-Read, kein FS/Drive."""
    day = day_plan(now.weekday())
    head = (f"🗺️ Senpai HUD — {day['name']} {now.strftime('%H:%M')} · "
            f"KW{now.isocalendar().week} · Heute: {day['type']} (V3)")
    jetzt = "   Jetzt:   " + " · ".join(_now_actions(now, day))
    morgen = "   Morgen:  " + _tomorrow_line(now)

    lines = [head, jetzt, morgen]

    if full:
        race = _race_line(live_text)
        if race:
            lines.append("   Race:    " + race)
        lines.append("   Skills & Commands:")
        for trig, desc in SKILL_INDEX:
            lines.append(f"     • {trig:34} → {desc}")
    else:
        lines.append("   Immer:   " + ALWAYS_COMPACT)
    lines.append("   " + AUTOMATION_HINT)
    return "\n".join(lines)


def _read_local(out_dir: str, name: str) -> str:
    try:
        return (Path(out_dir) / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Senpai Action-HUD (Wochentag × Zeitfenster → Aktionen). Non-blocking."
    )
    p.add_argument("--full", action="store_true", help="volle Liste + kompletter Skill-Index (für /menu)")
    p.add_argument("--tz", default=clock.DEFAULT_TZ, help=f"Zeitzone (default: {clock.DEFAULT_TZ})")
    p.add_argument("--now", help="ISO8601 LOKALE Zeit injizieren (z. B. 2026-07-04T08:00 = 08:00 in --tz)")
    p.add_argument("--out", default=DEFAULT_OUT, help="lokaler Ordner mit live.md (default: ./data)")
    args = p.parse_args(argv)

    try:
        now = clock.local_now(args.tz, clock.parse_now(args.now))
        live_text = _read_local(args.out, LIVE_NAME) if args.full else ""
        print(build_hud(now, "", live_text, full=args.full))
    except Exception as e:  # nie die Session blocken
        print(f"🗺️ Senpai HUD n/a ({type(e).__name__}) — frag 'was kann ich gerade tun?' oder /menu")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
