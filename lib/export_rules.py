#!/usr/bin/env python3
"""export_rules.py — deklarative Regel-Registry für den claude.ai-Export.

Ein Zuhause für alles, was der Exporter (lib/export_claude_ai.py) pro Skill
wissen muss: Kurz-Description (≤200 Zeichen, claude.ai-Trigger-Mechanismus!),
Bundle-Inhalt (Skripte/Referenzen/Assets), pip-Bedarf, Pfad-Rewrites und das
generierte "§0-CAI"-Preamble. Reine Daten + Mini-Helpers — unit-testbar,
keinerlei I/O.

Design-Anker (Plan "claude.ai VOLL-TWIN", 2026-07-02):
- Repo = SSoT; dieser Export ist DERIVAT. Skill-Logik wird NIE hier gepflegt.
- Marker in den Quell-SKILL.md steuern die Transformation:
  <!-- cc-only:start --> … <!-- cc-only:end -->   → im Export ENTFERNT
  <!-- cai-only:start … cai-only:end -->          → im Export ENTKOMMENTIERT
- Descriptions sind der EINZIGE Trigger-Mechanismus auf claude.ai (keine
  Slash-Commands) → Trigger-Phrasen müssen hier drinstehen, hart ≤200 Zeichen.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Verbotene Tokens im Export-ERGEBNIS (transformierte SKILL.md + generierte
# Dokumente — NICHT die verbatim kopierten Skripte, deren Repo-Kommentare
# harmlos sind). Ein Treffer = Export bricht laut ab (Drift-Stolperdraht).
# ---------------------------------------------------------------------------
FORBIDDEN_EXPORT_TOKENS = (
    "pull_drive",
    "GOOGLE_SERVICE_ACCOUNT",
    "lib/",
    ".claude/",
    "CronCreate", "CronList", "CronDelete",
    "cc-only", "cai-only",          # Marker dürfen das Transformat nie überleben
    "mcp__",                        # wird mechanisch zu Connector-Phrasen
    # Drive-IDs (Ordner/Sheets) — auf claude.ai läuft alles über den Connector
    # per Ordner-/Datei-NAME, IDs haben im Export nichts verloren.
    "1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde",
    "1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F",
    "1dpQUVeU3rjLFzA-xRANbC88RDV1JZwxf",
    "1zhNbm7f2SOeJL0QWGhaDt113R61tmHvi0KZCT1Z0sxU",
    "1ENUtb3LS5GgaDDhciBCuyUDqlwJTsjU6n6PTCZuIcDE",
    "1NLywaCKVZQlw8O4eZt20o2B14qgPIyFJ",
)

import re as _re  # noqa: E402

# "lib/" nur als Pfad-Anfang zählen — sonst matcht "matplotlib/pandas".
_FORBIDDEN_PATTERNS = tuple(
    (t, _re.compile((r"(?<![A-Za-z])" if t == "lib/" else "") + _re.escape(t)))
    for t in FORBIDDEN_EXPORT_TOKENS
)


def forbidden_hits(text: str) -> list[tuple[int, str, str]]:
    """(zeilennr, token, zeile)-Treffer verbotener Tokens — geteilte Logik für
    Exporter-Gate und test_claude_ai_export (eine Wahrheit, ein Verhalten)."""
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for tok, pat in _FORBIDDEN_PATTERNS:
            if pat.search(line):
                hits.append((n, tok, line))
    return hits

# ---------------------------------------------------------------------------
# Mechanische Rewrites (Tier B). Reihenfolge: erst per-Skill, dann global.
# Format: (regex, replacement). Bewusst konservativ — alles, was ein Rewrite
# nicht abdeckt, fängt der Forbidden-Check.
# ---------------------------------------------------------------------------
GLOBAL_REWRITES = (
    # Skill-interne wie skill-fremde Skriptpfade → bundle-relativ (Kopien liegen bei)
    (r"\.claude/skills/[A-Za-z0-9_-]+/scripts/", "scripts/"),
    # Strava-MCP-Toolnamen → Connector-Sprache (Tool-Namen bleiben erkennbar)
    (r"`?mcp__Strava__\*`?", "die Strava-Connector-Tools"),
    (r"mcp__Strava__([a-z_]+)", r"Strava-Connector-Tool \1"),
    # Schwellen-Registry: existiert im Export nicht als Datei — als Konzept benennen
    (r"`lib/constants\.py`", "die Schwellen-Registry des Repos"),
    (r"lib/constants\.py", "die Schwellen-Registry des Repos"),
    # Default für die VM-Uhr, wo kein Bundle-clock.py beiliegt (per-Skill-Regel
    # unten gewinnt, weil sie ZUERST läuft):
    (r"`lib/clock\.(is_[a-z_]+)`", r"`clock.\1` (Sandbox-Uhr, daily-check-Bundle)"),
    (r"`lib/clock\.py`", "der Sandbox-Uhr (scripts/clock.py, daily-check-Bundle)"),
    (r"lib/clock\.py", "der Sandbox-Uhr (scripts/clock.py, daily-check-Bundle)"),
)

_CLOCK_LOCAL = (
    (r"`lib/clock\.(is_[a-z_]+)`", r"`clock.\1` (scripts/clock.py)"),
    (r"`?lib/clock\.py`?", "scripts/clock.py"),
)

PER_SKILL_REWRITES = {
    "weather-runprep-skill": _CLOCK_LOCAL + (
        (r"`?lib/weather\.py`?", "scripts/weather.py"),
    ),
    "daily-check-skill": _CLOCK_LOCAL + (
        # daily-check verweist auf die Wetter-Engine des weather-Bundles
        (r"`?lib/weather\.py`?", "der Bright-Sky-Slot-Engine (weather-runprep-skill)"),
    ),
    "sync-skill": _CLOCK_LOCAL + (
        (r"`?lib/session_menu\.py`?", "scripts/session_menu.py"),
        (r"`?lib/consolidate\.py`?", "scripts/consolidate.py"),
    ),
}

# ---------------------------------------------------------------------------
# Gemeinsame Preamble-Bausteine (werden pro Skill zusammengesetzt)
# ---------------------------------------------------------------------------
_PRE_HEAD = (
    "## §0-CAI · Laufzeit & Datenbeschaffung (claude.ai)\n\n"
    "> Dieses Bundle ist der claude.ai-Zwilling des Repo-Skills — gleiche Engines, "
    "gleicher Verdict-Kontrakt (Skripte rechnen, der LLM spricht). Skripte laufen in "
    "der Code-Sandbox (Python 3.11). Vorbereitung: `mkdir -p ./data`. Den Skill-Ordner "
    "per `ls` unter `/mnt/skills/` finden (Pfade nie blind hardcoden), Skripte als "
    "`python3 scripts/<name>.py` aus dem Skill-Ordner aufrufen.\n"
)

_PRE_WRITEBACK = (
    "**Write-Back:** Google-Drive-Connector — die BESTEHENDE Datei im Drive-Ordner "
    "„Senpai-AI-Chat“ aktualisieren (nie ein Duplikat anlegen). Fallback bei "
    "fehlgeschlagenem Write: kompletten neuen Datei-Inhalt als Code-Fence ausgeben, "
    "der User ersetzt ihn in Drive.\n"
)

_PRE_KERNREGEL = (
    "**Kernregel:** Roh-Serien (Per-Sekunde/-Minute) erreichen NIE den Kontext — "
    "Skripte reduzieren in der Sandbox, gelesen werden nur die kompakten "
    "JSON-Aggregate. Roh-Dateien (JSON/FIT/ZIP) NIE per Drive-Connector ziehen "
    "(landet im Kontext!) — immer als Chat-Upload anfordern (landet in der Sandbox).\n"
)


def _pre(matrix_rows: list[tuple[str, str]], pip_line: str | None = None,
         extra: str | None = None) -> str:
    rows = "\n".join(f"| {a} | {b} |" for a, b in matrix_rows)
    parts = [
        _PRE_HEAD,
        "**Datenbeschaffung:**\n\n| Was | Woher |\n|---|---|\n" + rows + "\n",
        _PRE_WRITEBACK,
    ]
    if pip_line:
        parts.append(f"**Pip:** {pip_line}\n")
    parts.append(_PRE_KERNREGEL)
    if extra:
        parts.append(extra if extra.endswith("\n") else extra + "\n")
    return "\n".join(parts)


_UPLOADS = "Chat-Upload → Sandbox (typisch `/mnt/user-data/uploads`, per `ls` verifizieren)"
_PROJFILE = "Projekt-Datei (Kontext) → bei Skript-Bedarf Inhalt nach `./data/<name>` schreiben"

# ---------------------------------------------------------------------------
# SKILLS-Registry — die eine Quelle für den Exporter.
# scripts/references/assets: Liste (repo-relativer Quellpfad, arcname im Bundle).
# assets mit personal=True kommen aus ./data (Pull vor --refresh-personal) und
# fließen NICHT in den content_hash (personal_hash separat).
# ---------------------------------------------------------------------------
_DC = ".claude/skills/daily-check-skill/scripts/"
_RB = ".claude/skills/run-bundle-skill/scripts/"
_GB = ".claude/skills/gym-bundle-skill/scripts/"

SKILLS = {
    "run-bundle-skill": {
        "description": (
            "Senpais Lauf-Analyse (FIT-first, V3). Trigger: analysier den Lauf, "
            "runanalyse, Lauf-Report, wie war mein Lauf, FIT-/ZIP-Upload eines Laufs. "
            "Splits, Laufform, Decoupling, Pace@Z2, Verdict."
        ),
        "scripts": [
            (_RB + "analyze_run_fit.py", "scripts/analyze_run_fit.py"),
            (_RB + "analyze_run.py", "scripts/analyze_run.py"),
            (_RB + "banister.py", "scripts/banister.py"),
            (_RB + "dedup_trainings.py", "scripts/dedup_trainings.py"),
            (_RB + "pacing_card.py", "scripts/pacing_card.py"),
            (_RB + "parse_workout.py", "scripts/parse_workout.py"),
        ],
        "references": [
            ("modules/V3_Protocol.md", "references/V3_Protocol.md"),
            ("modules/Daten_Parsing.md", "references/Daten_Parsing.md"),
        ],
        "assets": [],
        "pip": ["fitparse"],
        "preamble": _pre(
            [
                ("FIT/ZIP des Laufs", _UPLOADS),
                ("live.md · gear.md · coaching_cues.md · baselines.md", _PROJFILE),
                ("readiness-history.csv (CTL/ATL-Anker)", "Projekt-Datei → nach `./data/readiness-history.csv` schreiben"),
                ("V3-Protokoll / Parsing-Referenz", "im Bundle: `references/V3_Protocol.md`, `references/Daten_Parsing.md`"),
            ],
            pip_line="`pip install --use-pep517 fitparse` einmal pro Konversation vor dem FIT-Parsing.",
        ),
    },
    "gym-bundle-skill": {
        "description": (
            "Senpais Gym-Analyse. Trigger: gymanalyse, Gym-Report, analysier den Gym, "
            "Krafttraining-ZIP oder Übungs-Text mit Gewichten. PR-Detection, Tonnage, "
            "HR-Profil, Re-Entry-Regel, Verdict."
        ),
        "scripts": [
            (_GB + "analyze_gym.py", "scripts/analyze_gym.py"),
            (_GB + "unzip_gym.py", "scripts/unzip_gym.py"),
        ],
        "references": [],
        "assets": [],
        "pip": [],
        "preamble": _pre(
            [
                ("Gym-ZIP (Apple-Watch/HealthFit)", _UPLOADS),
                ("baselines.md (PR-SSoT) · athlete.md (Geräte-Map) · live.md", _PROJFILE),
                ("Kraft-Programm.md (Geräte/Biomechanik)", "Projekt-Datei (Drive-synchronisiert)"),
            ],
        ),
    },
    "daily-check-skill": {
        "description": (
            "Senpais Daily Check: WHOOP-Tages-Dashboard (Recovery, Schlaf, HRV, Load, "
            "Heute-Plan, Urteil). Trigger: Daily Check, dailycheck, Status, wie war "
            "die Nacht, Briefing, Moin/Hi Senpai."
        ),
        "scripts": [(_DC + n, "scripts/" + n) for n in (
            "banister.py", "body_battery.py", "daily_signals.py", "dedup_trainings.py",
            "hrv_baseline.py", "hrv_heatmap.py", "readiness.py", "readiness_history.py",
            "running_tolerance.py", "safety_gate.py", "season.py", "sentinel.py",
            "slice_hae_day.py", "stats.py", "trend_snapshot.py", "weekly_rollup.py",
        )] + [("lib/clock.py", "scripts/clock.py")],
        "references": [],
        "assets": [],
        "pip": [],
        "preamble": _pre(
            [
                ("Tages-JSONs (heute + gestern, HealthAutoExport)", _UPLOADS + " — BEIDE anfordern (Mitternachts-Merge)"),
                ("live.md · baselines.md · learnings.md · backlog.md · trend_snapshot.md", _PROJFILE),
                ("readiness-history.csv", "Projekt-Datei → nach `./data/readiness-history.csv` schreiben (banister/readiness_history brauchen sie dort)"),
            ],
            extra="**Uhr:** `python3 scripts/clock.py` = Sandbox-Uhr (Europe/Berlin) für Header/Trigger-Fenster.",
        ),
    },
    "nutrition-skill": {
        "description": (
            "Senpais Ernährungs-Engine. Trigger: makro, essen, protein, kcal, "
            "supplement, casein, wasser, Gewichts-Update, Macros. Caps pro Tagestyp, "
            "Protein-Floor 150g, Ampel-Bewertung."
        ),
        "scripts": [],
        "references": [],
        "assets": [],
        "pip": [],
        "preamble": _pre(
            [
                ("live.md (Tagestyp, SoT-Gewicht, Streaks)", "Projekt-Datei (Kontext)"),
                ("Makro-Zahlen des Tages", "User-Post im Chat bzw. Tages-JSON-Upload (daily-check-Slicer)"),
            ],
        ),
    },
    "weather-runprep-skill": {
        "description": (
            "Senpais Wetter- & Pre-Lauf-Engine. Trigger: wetter, lauf, regen, hitze, "
            "pace, schuhe, Trainingstage Mo/Mi/Do/Sa. Bright-Sky-Stundenwerte, "
            "Impact-Matrix, Hitze-Tax, GO/ADJUST/SHIFT."
        ),
        "scripts": [
            ("lib/weather.py", "scripts/weather.py"),
            ("lib/clock.py", "scripts/clock.py"),
        ],
        "references": [],
        "assets": [("data/brightsky_url.txt", "assets/brightsky_url.txt", True)],
        "pip": [],
        "preamble": _pre(
            [
                ("Bright-Sky-Stundenwerte", "URL aus `assets/brightsky_url.txt` ({date} ersetzen) per CHAT-Web-Fetch holen → Antwort ungekürzt nach `./data/brightsky.json` → `python3 scripts/weather.py --from-json ./data/brightsky.json …`"),
                ("Wetterochs (Narrativ/Gewitter/Fallback)", "Chat-Web-Fetch RSS + Delphi-JSON (wie gehabt)"),
                ("gear.md · coaching_cues.md · live.md", _PROJFILE),
            ],
            extra="**Wichtig:** Die Sandbox hat KEIN freies Netz — Bright Sky wird auf CHAT-Ebene gefetcht, das Skript parst nur die gespeicherte JSON (`--from-json`).",
        ),
    },
    "race-projection-skill": {
        "description": (
            "Senpais Race-Engine. Trigger: race, Rennen, HM, Halbmarathon, 10km, "
            "Zielzeit, cutoff, Besenwagen, Pace-Strategie. 4-Szenarien-Projektion, "
            "Cutoff-Math, Pacing-Card."
        ),
        "scripts": [
            (_DC + "stats.py", "scripts/stats.py"),
            (_RB + "pacing_card.py", "scripts/pacing_card.py"),
            # stats.py lazy-importiert dedup_trainings (banister_fit-Pfad) — beilegen
            (_DC + "dedup_trainings.py", "scripts/dedup_trainings.py"),
        ],
        "references": [],
        "assets": [
            ("data/Race_Strategie.md", "assets/Race_Strategie.md", True),
            ("data/21km.gpx", "assets/21km.gpx", True),
        ],
        "pip": [],
        "preamble": _pre(
            [
                ("Race_Strategie.md · 21km.gpx", "im Bundle: `assets/` (beim Export aus Drive eingefroren — bei Race-Strategie-Änderung Re-Export nötig)"),
                ("live.md (Race-Kalender, Countdown, Gewicht)", "Projekt-Datei (Kontext)"),
                ("Referenz-Läufe (Decoupling-Quelle)", "letzter Run-Report bzw. FIT-Upload (run-bundle-skill)"),
            ],
        ),
    },
    "payload-skill": {
        "description": (
            "Senpais Wochen-Payload. Trigger: Payload, Sonntag-KW-Abschluss, "
            "Wochen-Export. Verdichtetes KW-Briefing als Code-Fence + live.md-PATCH — "
            "copy-paste-fertig für den nächsten KW-Chat."
        ),
        "scripts": [(_DC + n, "scripts/" + n) for n in (
            "weekly_rollup.py", "trend_snapshot.py", "readiness_history.py",
            "banister.py", "daily_signals.py", "slice_hae_day.py",
            "dedup_trainings.py",  # lazy-Import in trend_snapshot (CTL-Backfill)
        )],
        "references": [],
        "assets": [],
        "pip": [],
        "preamble": _pre(
            [
                ("readiness-history.csv (KW-Anker)", "Projekt-Datei → nach `./data/readiness-history.csv` schreiben"),
                ("Makro-/Tages-Detail (falls nötig)", "Tages-JSONs bzw. Monats-CSV als Chat-Upload anfordern — anfordern statt raten (Hol-Pflicht)"),
                ("live.md · backlog.md · trend_snapshot.md", _PROJFILE),
            ],
            extra="**Hinweis:** Der Sonntags-Payload läuft bevorzugt im Repo-Zwilling (Claude Code); diese Variante ist der mobile Fallback mit identischem Output-Kontrakt.",
        ),
    },
    "sync-skill": {
        "description": (
            "Senpais Rekalibrierung + Menu. Trigger: Sync, KW-Start, Drift-Verdacht, "
            "Menu, was kann ich gerade tun. Re-Anker auf Live-State + V3-Protokoll, "
            "knappe Checkliste bzw. Aktions-HUD."
        ),
        "scripts": [
            ("lib/session_menu.py", "scripts/session_menu.py"),
            ("lib/consolidate.py", "scripts/consolidate.py"),
            ("lib/clock.py", "scripts/clock.py"),
        ],
        "references": [],
        "assets": [],
        "pip": [],
        "preamble": _pre(
            [
                ("live.md · athlete.md · trend_snapshot.md · backlog.md", "Projekt-Dateien (Kontext) — nichts zu ziehen"),
                ("Konsolidierung (§3.5)", "senpai-journal.md/learnings.md/baselines.md per Connector nach `./data/` → `python3 scripts/consolidate.py --local --data-dir ./data` → learnings/baselines per Connector-Update zurück"),
            ],
        ),
    },
}

# Länge-Gate SOFORT beim Import — eine zu lange Description ist ein Build-Fehler,
# kein Runtime-Überraschungsei (claude.ai-Support-Doku: 200 Zeichen Limit).
for _name, _cfg in SKILLS.items():
    assert len(_cfg["description"]) <= 200, (
        f"{_name}: description {len(_cfg['description'])} Zeichen (>200)"
    )
    assert _name.islower() and len(_name) <= 64, _name


def bundle_files(name: str) -> list[tuple[str, str, bool]]:
    """Alle Bundle-Dateien eines Skills als (Quellpfad, arcname, personal)."""
    cfg = SKILLS[name]
    out: list[tuple[str, str, bool]] = []
    for src, arc in cfg["scripts"]:
        out.append((src, arc, False))
    for src, arc in cfg["references"]:
        out.append((src, arc, False))
    for entry in cfg["assets"]:
        src, arc, personal = entry
        out.append((src, arc, personal))
    return out


def rewrites_for(name: str) -> tuple:
    """Per-Skill-Rewrites zuerst, dann global (Reihenfolge ist Vertrag)."""
    return tuple(PER_SKILL_REWRITES.get(name, ())) + GLOBAL_REWRITES
