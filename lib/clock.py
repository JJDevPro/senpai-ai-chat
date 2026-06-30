#!/usr/bin/env python3
"""Deterministische lokale Zeitquelle für senpai-ai-chat (Claude Code on the web).

Warum das existiert: claude.ai hatte KEINE verlässliche Uhr → CLAUDE.md §3 baute
eine Hierarchie aus Raten + `[Zeit n/a]` und ließ Zeit-Trigger no-oppen. Die
Claude-Code-VM hat eine ECHTE Systemuhr. Dieses Modul liefert die lokale Zeit
deterministisch (System-Uhr → Europe/Berlin), damit Zeit-Trigger (Roast-Morgen,
Bedtime-Attacke, Mittag-Gate) wieder ZUVERLÄSSIG feuern statt zu raten. KEIN
API-Call, kein Halluzinieren — echte Uhr + Zeitzone.

Geteilt von `lib/session_menu.py` (HUD) und den Skills (§3). Alle Funktionen sind
pure/injizierbar: `now` ist durchreichbar, damit Tests deterministisch bleiben —
der einzige impure Punkt ist der Default-Clock-Read in `local_now`.

CLI:  python3 lib/clock.py [--tz Europe/Berlin] [--now ISO8601]
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Default-Zeitzone — abgeleitet aus dem athlete-Wohnort (PERSONAL-DATA-FREI: der
# Ort selbst lebt in Drive; hier nur die generische IANA-TZ). Override via
# --tz / Env SENPAI_TZ.
DEFAULT_TZ = os.environ.get("SENPAI_TZ", "Europe/Berlin")


def local_now(tz: str = DEFAULT_TZ, now: datetime | None = None) -> datetime:
    """Aktuelle lokale Zeit in `tz`.

    `now` ist injizierbar (Test/Override) — **naiv = bereits LOKALE Zeit in `tz`**
    (so liest sich `--now 2026-07-04T08:00` als 08:00 Berlin, wie in den CLI-
    Beispielen gemeint); ein tz-aware `now` wird in `tz` umgerechnet. Ohne `now`
    wird die System-Uhr gelesen (der EINZIGE impure Punkt im Modul).
    """
    z = ZoneInfo(tz)
    if now is None:
        return datetime.now(z)
    if now.tzinfo is None:
        return now.replace(tzinfo=z)   # naiv = schon lokale Zeit (kein UTC-Shift)
    return now.astimezone(z)           # tz-aware → in Ziel-TZ umrechnen


def time_window(dt: datetime) -> str:
    """Grobes Tagesfenster fürs HUD/Routing (generisch, keine Personendaten)."""
    h = dt.hour
    if 5 <= h < 10:
        return "morgen"
    if 10 <= h < 17:
        return "tag"
    if 17 <= h < 22:
        return "abend"
    return "nacht"  # 22–05


def is_roast_morning(dt: datetime) -> bool:
    """Roast-Morgen-Fenster (CLAUDE.md §3): 05:00–09:59."""
    return 5 <= dt.hour < 10


def is_bedtime_window(dt: datetime) -> bool:
    """Bedtime-Attacke (CLAUDE.md §3/§6): ab 22:00."""
    return dt.hour >= 22


# Trainingstage (CLAUDE.md §4 Wochen-Rhythmus): Mo=Run+Core · Mi=Long Run ·
# Do=Gym · Sa=Parkrun. Di/Fr/So = Rest. weekday(): Mo=0 … So=6.
TRAINING_DAYS = {0, 2, 3, 5}   # Mo, Mi, Do, Sa
RUN_DAYS = {0, 2, 5}           # Mo, Mi, Sa (Do = Pure-Gym, Lauf nur bei Flex-Regel)


def is_training_day(dt: datetime) -> bool:
    """Trainingstag (Mo/Mi/Do/Sa) — triggert Wetter/Pre-Lauf im Daily Check (§4/§12.5)."""
    return dt.weekday() in TRAINING_DAYS


def is_run_day(dt: datetime) -> bool:
    """Lauftag (Mo/Mi/Sa) — Pre-Lauf-Briefing rendert hier (Do nur bei aktiver Flex-Regel)."""
    return dt.weekday() in RUN_DAYS


def parse_now(s: str | None) -> datetime | None:
    """ISO8601 → datetime (für --now / Tests). None bei leerem Wert."""
    if not s:
        return None
    return datetime.fromisoformat(s)


def main(argv=None):
    p = argparse.ArgumentParser(description="Deterministische lokale Zeit (System-Uhr → TZ).")
    p.add_argument("--tz", default=DEFAULT_TZ, help=f"IANA-Zeitzone (default: {DEFAULT_TZ})")
    p.add_argument("--now", help="ISO8601 LOKALE Zeit injizieren (z. B. 2026-07-04T08:00 = 08:00 in --tz); sonst System-Uhr")
    args = p.parse_args(argv)
    dt = local_now(args.tz, parse_now(args.now))
    print(
        f"{dt.strftime('%A %d.%m. %H:%M %Z')} · KW{dt.isocalendar().week}"
        f" · window={time_window(dt)} · roast_morning={is_roast_morning(dt)}"
        f" · bedtime={is_bedtime_window(dt)} · training_day={is_training_day(dt)}"
        f" · run_day={is_run_day(dt)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
