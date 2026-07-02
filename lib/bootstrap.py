#!/usr/bin/env python3
"""SessionStart identity-bootstrap for senpai-ai-chat (Claude Code on the web).

Warum das existiert: `lib/preflight.py` prüft die Plumbing (Deps + Credential),
ist aber BEWUSST offline und zieht KEINE Identität. Ohne diesen Schritt startet
eine Session ungrounded — Senpai kennt weder Name noch KW noch Live-State und
müsste raten. Dieses Skript zieht den State-Seed (`athlete.md` + `live.md`) aus
dem privaten `Senpai-AI-Chat`-Drive-Ordner nach `./data` und druckt EINEN
kompakten Banner, damit Identität so verlässlich lädt wie die Instruktionen.

Es ist NON-BLOCKING: der Netz-Zugriff ist in try/except gekapselt. Bei JEDEM
Fehler druckt es einen WARN-Banner ("Seed unavailable, do not fabricate athlete
state.") und beendet IMMER mit Exit 0 — es warnt, es blockt nie die Session.

`build_banner(athlete_text, live_text)` ist eine PURE Funktion (kein Drive, kein
FS) und extrahiert Name/KW/Gewicht/HRV/VO2/Overrides aus den beiden Markdown-
Texten — best-effort, "n/a" wenn ein Feld fehlt. Die Tests prüfen sie gegen
SYNTHETISCHE Strings (kein echter Personenwert lebt je in dieser Datei).

CLI:  python3 lib/bootstrap.py [--folder ID] [--out ./data]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# bootstrap.py liegt neben pull_drive.py in lib/ — importierbar machen (wie archive.py).
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

# Der private State-Ordner (Senpai-AI-Chat). Überschreibbar via --folder.
DEFAULT_FOLDER_ID = "1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde"
DEFAULT_OUT = "./data"
ATHLETE_NAME = "athlete.md"
LIVE_NAME = "live.md"


def _eprint(*a):
    print(*a, file=sys.stderr)


# --------------------------------------------------------------------------- #
# Pure Extraktions-/Banner-Logik (kein Drive, kein FS, voll unit-testbar)
# --------------------------------------------------------------------------- #
def _extract_name(athlete_text: str) -> str:
    """Ziehe den Namen aus der athlete.md-Zeile `**Name:** X` (best-effort)."""
    m = re.search(r"\*\*Name:\*\*\s*(.+)", athlete_text or "")
    if not m:
        return "n/a"
    # Vorname vor einer Klammer/Komma, ohne abschließende Satzzeichen ("Max
    # (Max Mustermann)." -> "Max") — das ist {Name} aus dem Anrede-Mapping.
    raw = m.group(1).strip()
    name = re.split(r"\s*[(,]", raw, 1)[0]
    return name.strip(" .*") or "n/a"


def _extract_kw(live_text: str) -> str:
    """Ziehe die KW aus der live.md-Zeile `Stand: KW...` (best-effort)."""
    m = re.search(r"Stand:\s*(KW\s*\S+)", live_text or "")
    return m.group(1).strip() if m else "n/a"


def _extract_metric(live_text: str, label: str) -> str:
    """Ziehe einen Tabellen-/Zeilen-Wert für `label` aus live.md (best-effort).

    Matcht sowohl Markdown-Tabellenzeilen (`| Gewicht | 80.0 kg |`) als auch
    einfache `Gewicht: 80.0`-Zeilen. Gibt den ersten Wert-Token zurück, sonst
    "n/a" — ein fehlender Wert ist nie ein Fehler, nur eine Lücke.
    """
    text = live_text or ""
    # Tabellen-Zeile: | <label> ... | <wert> ... |  (kein \b: "VO2" soll auch
    # "VO2Max aktuell" matchen — zwischen "2" und "M" gibt es keine Wortgrenze).
    m = re.search(
        rf"\|\s*{re.escape(label)}[^|]*\|\s*([^|]+?)\s*\|",
        text,
        re.IGNORECASE,
    )
    if not m:
        # Schlichte Zeile: <label>: <wert>
        m = re.search(rf"{re.escape(label)}[^\n:=]*[:=]\s*(.+)", text, re.IGNORECASE)
    if not m:
        return "n/a"
    # Markdown-Hervorhebung (**...**) entfernen, damit der Banner sauber bleibt.
    val = m.group(1).replace("*", "").strip()
    return val if val else "n/a"


def _count_overrides(live_text: str) -> int:
    """Zähle Bullet-Punkte unter dem Abschnitt `## Aktive Overrides` (best-effort).

    Ein leerer Abschnitt oder ein expliziter `- keine`/`(keine)`-Platzhalter zählt
    als 0. Gezählt werden nur echte `-`/`*`-Bullets bis zur nächsten Überschrift.
    """
    text = live_text or ""
    # Heading-Zeile bis Zeilenende erlauben — die echte Überschrift trägt einen
    # Zusatz ("## Aktive Overrides (zeitlich begrenzt)").
    m = re.search(r"##\s*Aktive Overrides[^\n]*\n", text, re.IGNORECASE)
    if not m:
        return 0
    rest = text[m.end():]
    # Bis zur nächsten Überschrift (## ...) abschneiden.
    nxt = re.search(r"\n#{1,6}\s", rest)
    block = rest[: nxt.start()] if nxt else rest
    count = 0
    for line in block.splitlines():
        s = line.strip()
        mb = re.match(r"[-*]\s+(.*)", s)
        if not mb:
            continue
        body = mb.group(1).strip().lower()
        if body in ("", "keine", "(keine)", "none", "-", "n/a"):
            continue
        count += 1
    return count


def build_banner(athlete_text: str, live_text: str) -> str:
    """Baue den kompakten Identity-Banner aus athlete.md- + live.md-Text.

    PURE: kein Drive, kein FS. Jedes Feld ist best-effort und fällt auf "n/a"
    zurück, damit ein Teil-Seed dennoch einen brauchbaren Banner liefert.
    """
    name = _extract_name(athlete_text)
    kw = _extract_kw(live_text)
    gewicht = _extract_metric(live_text, "Gewicht")
    hrv = _extract_metric(live_text, "HRV")
    vo2 = _extract_metric(live_text, "VO2")
    overrides = _count_overrides(live_text)
    return (
        f"Senpai bootstrap OK — Athlet: {name} · {kw} · "
        f"Gewicht {gewicht} · HRV {hrv} · VO2 {vo2} · Overrides: {overrides}"
    )


def _warn_banner(reason: str) -> str:
    return (
        f"Senpai bootstrap WARN — Identity-Pull down ({reason}) — "
        f"Seed unavailable, do not fabricate athlete state."
    )


# --------------------------------------------------------------------------- #
# Drive-Glue (reuse lib/pull_drive.py) — non-blocking
# --------------------------------------------------------------------------- #
def _pull_seed(folder_id: str, out_dir: str, sa_file=None):
    """Ziehe athlete.md + live.md aus dem Drive-Ordner nach out_dir.

    Gibt (athlete_text, live_text) zurück; ein fehlendes File liefert "" für
    diesen Teil (best-effort). Netz-Fehler propagieren an den Caller, der sie
    in einen WARN-Banner übersetzt.
    """
    import pull_drive as pd

    creds = pd._load_credentials(sa_file, pd.SCOPES_RO)
    svc = pd._drive(creds)
    out = Path(out_dir)

    texts = {}
    for name in (ATHLETE_NAME, LIVE_NAME):
        matches = pd._list_matches(svc, folder_id, name, None)
        exact = [f for f in matches if f["name"] == name]
        if not exact:
            texts[name] = ""
            continue
        dest = out / name
        pd._download_media(svc, exact[0]["id"], dest)
        texts[name] = dest.read_text(encoding="utf-8")
    return texts.get(ATHLETE_NAME, ""), texts.get(LIVE_NAME, "")


def run_bootstrap(folder, out_dir, sa_file=None) -> int:
    """Pull den State-Seed, druck den Banner. IMMER 0 — non-blocking.

    Bei JEDEM Fehler (Credential, Netz, Drive) wird ein WARN-Banner gedruckt und
    die Session NICHT blockiert.
    """
    try:
        athlete_text, live_text = _pull_seed(folder, out_dir, sa_file)
    except SystemExit as e:  # pull_drive nutzt SystemExit für Credential-Fehler
        print(_warn_banner(f"credentials/exit {e.code}"))
        return 0
    except Exception as e:
        print(_warn_banner(type(e).__name__))
        return 0
    # Ehrlichkeit vor "OK": Ein Pull, der technisch klappt, aber KEINEN Seed
    # findet, ist kein Erfolg — der alte Code druckte "bootstrap OK" mit lauter
    # n/a-Feldern (Audit-CONFIRMED). Fehlende Dateien werden benannt.
    if not athlete_text and not live_text:
        print(_warn_banner("seed fehlt: athlete.md + live.md nicht im Drive-Ordner"))
        return 0
    banner = build_banner(athlete_text, live_text)
    missing = [n for n, t in ((ATHLETE_NAME, athlete_text), (LIVE_NAME, live_text)) if not t]
    if missing:
        banner += f" · ⚠️ Seed unvollständig: {', '.join(missing)} fehlt im Drive-Ordner"
    print(banner)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="SessionStart identity-bootstrap: pull state-seed + print banner (non-blocking)."
    )
    p.add_argument("--folder", default=DEFAULT_FOLDER_ID, help="Drive folder ID (default: Senpai-AI-Chat)")
    p.add_argument("--out", default=DEFAULT_OUT, help="local scratch dir for the pulled seed (default: ./data)")
    p.add_argument("--sa-file", help="path to service-account JSON (else env)")
    args = p.parse_args(argv)
    return run_bootstrap(args.folder, args.out, args.sa_file)


if __name__ == "__main__":
    raise SystemExit(main())
