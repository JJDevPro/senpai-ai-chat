"""Tests für das drive-seed/ Template-Kit (T9).

ZWECK: drive-seed/ liefert DATA-FREIE Platzhalter-Vorlagen, damit der Nutzer den
privaten Drive-Ordner einmalig vor-seeden kann (der Service-Account kann Dateien
nur UPDATEN, nicht ANLEGEN — siehe lib/archive.py). Diese Tests sichern zwei Dinge:

  1. VOLLSTÄNDIGKEIT: jede laut Ticket geforderte Vorlage existiert.
  2. DATA-FREE-LINT: KEINE Datei unter drive-seed/ enthält einen verbotenen
     echten Marker (Name/Stadt/Equipment/Gewichts-Token). Die Vorlagen dürfen nur
     {{PLATZHALTER}} + offensichtliche Dummy-Werte tragen.

DRIVE-FREI: kein Google-Drive-Zugriff, reines Dateisystem-Lesen.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "drive-seed"

# Laut Ticket geforderte Vorlagen + README.
REQUIRED_FILES = [
    "README.md",
    "athlete.md",
    "live.md",
    "baselines.md",
    "learnings.md",
    "senpai-journal.md",
    "readiness-history.csv",
    "trend_snapshot.md",
    "backlog.md",
    "Schlaf_HRV_Baseline.md",
    "Kraft-Programm.md",
    "Race_Strategie.md",
    "Schuhe_Ausruestung.md",
    "Historie.md",
    "Archiv_Historie.md",
    "Project_Index.md",
    "CHANGELOG.md",
]

# Verbotene echte Marker (Identität/Equipment/Gewichts-Token). "116.0" wird als
# eigenständiges Token geprüft (nicht als Teilstring von z. B. "1116.0").
FORBIDDEN_SUBSTRINGS = [
    "Javier",
    "Garcell",
    "Nürnberg",
    "Janna",
    "Withings Body Scan",
]
FORBIDDEN_TOKEN = "116.0"


def _seed_files():
    return sorted(p for p in SEED_DIR.rglob("*") if p.is_file())


def test_seed_dir_exists():
    assert SEED_DIR.is_dir(), f"drive-seed/ fehlt: {SEED_DIR}"


def test_all_required_templates_present():
    missing = [name for name in REQUIRED_FILES if not (SEED_DIR / name).is_file()]
    assert not missing, f"Fehlende Vorlagen in drive-seed/: {missing}"


def test_readiness_history_header_only():
    """readiness-history.csv hat NUR die Header-Zeile (keine Datenzeilen) und matcht
    den kanonischen Header aus readiness_history.HEADER (kein Drift)."""
    import sys
    scripts = SEED_DIR.parents[0] / ".claude" / "skills" / "daily-check-skill" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import readiness_history as rh
    header = ",".join(rh.HEADER)
    text = (SEED_DIR / "readiness-history.csv").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines == [header], f"CSV soll nur den (kanonischen) Header haben, ist aber: {lines}"


def test_journal_has_example_entry():
    """senpai-journal.md trägt genau einen Beispiel-Eintrag im archive.py-Format."""
    text = (SEED_DIR / "senpai-journal.md").read_text(encoding="utf-8")
    assert "## [daily] 2026-01-01" in text


def test_no_forbidden_real_markers_anywhere():
    """DATA-FREE-LINT: keine Datei unter drive-seed/ enthält echte Marker."""
    offenders = []
    for path in _seed_files():
        text = path.read_text(encoding="utf-8", errors="strict")
        for marker in FORBIDDEN_SUBSTRINGS:
            if marker in text:
                offenders.append((path.name, marker))
        # Standalone-Token-Check für "116.0": durch Nicht-Zahl-/Nicht-Punkt-Grenzen.
        import re
        if re.search(r"(?<![\d.])" + re.escape(FORBIDDEN_TOKEN) + r"(?![\d])", text):
            offenders.append((path.name, FORBIDDEN_TOKEN))
    assert not offenders, f"Verbotene Marker gefunden: {offenders}"


def test_every_template_has_dummy_header_comment():
    """Jede Markdown-Vorlage trägt den Dummy-Header-Kommentar (außer reine CSV)."""
    needle = "Dummy — echte Daten leben NUR in Drive"
    missing = []
    for name in REQUIRED_FILES:
        if not name.endswith(".md"):
            continue
        text = (SEED_DIR / name).read_text(encoding="utf-8")
        if needle not in text:
            missing.append(name)
    assert not missing, f"Vorlagen ohne Dummy-Header-Kommentar: {missing}"
