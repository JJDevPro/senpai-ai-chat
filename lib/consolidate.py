#!/usr/bin/env python3
"""Memory-Konsolidierung im claude.ai-Stil — destilliert dauerhafte Learnings.

Warum dieses Skript existiert: das rollende `senpai-journal.md` (siehe
`lib/archive.py`) wächst mit jedem Daily-Check/Run/Weekly/Payload. Die meisten
Sektionen sind tagesaktuell und vergänglich. Ein paar Einsichten aber sind
DAUERHAFT — wiederkehrende Muster ("an 3 Tagen wieder zu spät ins Bett"), neue
PRs aus `## [run]`-Sektionen, neue Baselines aus `## [weekly]`-Sektionen. Diese
gehören in den persistenten State (`learnings.md` / `baselines.md`), nicht ins
ephemere Journal.

Dieses Skript liest das Journal + den bestehenden State, EXTRAHIERT die
dauerhaften Learnings, DEDUPLIZIERT gegen das schon Bekannte (kein Re-Promote),
RENDERT einen datierten, quellen-markierten Patch (Append-Stil) und lädt den
gepatchten State zurück nach Drive. AUTONOM + SICHTBAR: der promotete Diff wird
auf stdout gedruckt (nur kompakte Aggregate — die destillierten Learning-Zeilen,
NIE die Roh-Journal-Serie), nie still.

HARD CONSTRAINT (wie archive.py, verifiziert): der Service-Account hat KEINE
My-Drive-Quota — er kann eine Ziel-Datei nur UPDATEN, nicht ANLEGEN. `learnings.md`
und `baselines.md` müssen daher vom Nutzer EINMALIG vor-seeded sein. Fehlt eine,
druckt dieses Skript eine klare Anweisung und beendet sich non-zero — es legt
NIE eine Datei an (Mirror von `archive.run_archive`).

Flow (Mirror von archive.run_archive):
  1. Journal + Ziel-State (learnings.md / baselines.md) aus Drive pullen.
  2. extract_candidates(journal) -> Kandidaten (pure, testbar).
  3. dedup(candidates, existing_state) -> nur Neues (pure, testbar).
  4. render_patch(existing, new) -> gepatchter State (pure, testbar, Append-Stil).
  5. gepatchten State zurück nach Drive uploaden (files.update auf der
     existierenden Datei).
IDEMPOTENT: ein zweiter Lauf ohne neues Journal-Material promotet NICHTS.

CLI:
  python3 lib/consolidate.py [--target learnings|baselines]
      [--as-of YYYY-MM-DD] [--journal senpai-journal.md]
      [--learnings learnings.md] [--baselines baselines.md]
      [--folder <ID>] [--out ./data]

Die Extraktions-/Dedup-/Render-Logik nimmt NUR Strings und fasst Drive nie an,
also testen die Tests sie rein lokal (siehe tests/test_consolidate.py).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date as _date
from pathlib import Path

# consolidate.py lebt neben pull_drive.py in lib/ — so oder so importierbar machen.
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

# Der private State-Ordner (Senpai-AI-Chat). Per --folder überschreibbar.
DEFAULT_FOLDER_ID = "1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde"
DEFAULT_JOURNAL = "senpai-journal.md"
DEFAULT_LEARNINGS = "learnings.md"
DEFAULT_BASELINES = "baselines.md"
TARGETS = ("learnings", "baselines")

# Wieviele Treffer ein Muster über das Journal braucht, um als DAUERHAFTES
# Learning zu zählen (ein Einzeltag ist Rauschen, kein Pattern — vgl. CLAUDE.md
# §5 "Pattern-Check bei 2+ Tagen").
RECURRENCE_MIN = 2

# Marker, mit dem promotete Zeilen geschrieben + wiedererkannt werden. Eine
# Konsolidierungs-Zeile sieht so aus:
#   - [2026-06-28] (run) Pace@Z2 PR: 8:42/km   <!--consolidated-->
_MARK = "<!--consolidated-->"


def _eprint(*a):
    print(*a, file=sys.stderr)


# --------------------------------------------------------------------------- #
# Reine Extraktions-/Dedup-/Render-Logik (kein Drive, voll unit-getestet)
# --------------------------------------------------------------------------- #
def _split_sections(journal_text: str):
    """Zerlege das Journal in (kind, body)-Sektionen anhand der archive.py-Header.

    Header-Form (von archive.format_section): "## [kind] YYYY-MM-DD". Gibt eine
    Liste von (kind, body)-Tupeln zurück; Material vor dem ersten Header wird
    ignoriert.
    """
    sections = []
    header_re = re.compile(r"^##\s+\[([a-z]+)\]\s+\d{4}-\d{2}-\d{2}\s*$")
    cur_kind = None
    cur_lines: list[str] = []
    for line in (journal_text or "").splitlines():
        m = header_re.match(line)
        if m:
            if cur_kind is not None:
                sections.append((cur_kind, "\n".join(cur_lines).strip()))
            cur_kind = m.group(1)
            cur_lines = []
        elif cur_kind is not None:
            cur_lines.append(line)
    if cur_kind is not None:
        sections.append((cur_kind, "\n".join(cur_lines).strip()))
    return sections


def _norm(text: str) -> str:
    """Normalisiere einen Learning-Text für Dedup/Recurrence (case/space-insensitiv)."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def extract_candidates(journal_text: str) -> list[dict]:
    """Destilliere DAUERHAFTE Learning-Kandidaten aus dem Journal-Text.

    Zwei Quellen (vgl. archive.py-Header):
      - WIEDERKEHRENDE Muster: identische "- "-Bullet-Zeilen, die in >= RECURRENCE_MIN
        Sektionen auftauchen, sind kein Tagesrauschen mehr -> Pattern-Learning.
      - NEUE PRs/Baselines: Zeilen in "## [run]"-Sektionen mit "PR" und in
        "## [weekly]"-Sektionen mit "Baseline" sind dauerhafte Fakten.

    Gibt eine Liste kompakter Kandidaten-Dicts {source, text, count} zurück —
    NIE die Roh-Journal-Serie. Reihenfolge ist deterministisch (erstes Auftreten).
    """
    sections = _split_sections(journal_text)

    bullet_re = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
    # Erst-Auftreten merken (für Text + Reihenfolge), Vorkommen zählen.
    order: list[str] = []
    first_text: dict[str, str] = {}
    # Pro Schlüssel die DISTINKTEN Sektions-Indizes sammeln — Recurrence zählt
    # Sektionen (Tage), nicht Roh-Zeilen (ein Tag mit Doppel-Bullet ist kein Muster).
    section_hits: dict[str, set] = {}

    candidates: list[dict] = []
    seen_keys: set[str] = set()

    def _emit(source: str, text: str):
        key = _norm(text)
        if not key or key in seen_keys:
            return
        seen_keys.add(key)
        candidates.append({"source": source, "text": text, "count": len(section_hits.get(key, ())) or 1})

    for sec_idx, (kind, body) in enumerate(sections):
        for line in body.splitlines():
            m = bullet_re.match(line)
            if not m:
                continue
            text = m.group(1).strip()
            key = _norm(text)
            if not key:
                continue
            if key not in first_text:
                order.append(key)
                first_text[key] = text
            section_hits.setdefault(key, set()).add(sec_idx)

            low = text.lower()
            # Neue PRs aus run-Sektionen, neue Baselines aus weekly-Sektionen:
            # sofort dauerhaft (ein einziger Beleg genügt für einen Fakt).
            if kind == "run" and "pr" in low:
                _emit("run", text)
            elif kind == "weekly" and "baseline" in low:
                _emit("weekly", text)

    # Wiederkehrende Muster (in >= RECURRENCE_MIN DISTINKTEN Sektionen).
    for key in order:
        if len(section_hits.get(key, ())) >= RECURRENCE_MIN:
            _emit("pattern", first_text[key])

    return candidates


def dedup(candidates: list[dict], existing_text: str) -> list[dict]:
    """Wirf Kandidaten raus, die im bestehenden State schon stehen (kein Re-Promote).

    Vergleicht normalisiert: schon promotete Zeilen tragen den `_MARK`, aber auch
    eine manuell im State vorhandene Formulierung zählt als bekannt. Reihenfolge
    der verbleibenden Kandidaten bleibt erhalten.
    """
    known = set()
    for line in (existing_text or "").splitlines():
        stripped = line.replace(_MARK, "")
        # Bullet-/Marker-Rauschen abziehen, damit der reine Text-Kern matcht.
        stripped = re.sub(r"^\s*[-*]\s+", "", stripped)
        stripped = re.sub(r"^\[\d{4}-\d{2}-\d{2}\]\s*", "", stripped.strip())
        stripped = re.sub(r"^\([a-z]+\)\s*", "", stripped)
        n = _norm(stripped)
        if n:
            known.add(n)

    out = []
    seen = set()
    for c in candidates:
        n = _norm(c["text"])
        if n in known or n in seen:
            continue
        seen.add(n)
        out.append(c)
    return out


def render_patch(existing_text: str, new_learnings: list[dict], day: str) -> str:
    """Hänge die neuen Learnings als datierten, quellen-markierten Block an.

    Append-Stil mit genau EINEM Trenner (eine Leerzeile) zwischen Alt-State und
    dem neuen Block. Jede Zeile:
        - [YYYY-MM-DD] (source) <text>   <!--consolidated-->
    Sind keine neuen Learnings da, bleibt der State BYTE-IDENTISCH (Idempotenz).
    """
    if not new_learnings:
        return existing_text or ""

    lines = [
        f"- [{day}] ({c['source']}) {c['text']}   {_MARK}" for c in new_learnings
    ]
    block = "\n".join(lines)

    head = (existing_text or "").rstrip("\n")
    if head.strip() == "":
        return block + "\n"
    return f"{head}\n\n{block}\n"


# --------------------------------------------------------------------------- #
# Drive-Glue (reuse von lib/pull_drive.py — Mirror von archive.run_archive)
# --------------------------------------------------------------------------- #
def _preseed_instruction(name: str, folder_id: str) -> str:
    return (
        f"ERROR: state file {name!r} not found in Drive folder {folder_id}.\n"
        f"The service-account has no My-Drive quota and CANNOT create it.\n"
        f"PRE-SEED it ONCE yourself: create an empty file named {name!r}\n"
        f"and drop it into the 'Senpai-AI-Chat' folder (drag-drop in Drive). "
        f"After that, consolidate.py will keep patching it automatically."
    )


def _pull_existing(pd, svc, folder_id, name, out: Path) -> str:
    """Pull eine VORHANDENE State-/Journal-Datei nach `out`; non-zero wenn absent."""
    matches = pd._list_matches(svc, folder_id, name, None)
    exact = [f for f in matches if f["name"] == name]
    if not exact:
        _eprint(_preseed_instruction(name, folder_id))
        raise SystemExit(2)
    fid = exact[0]["id"]
    dest = out / name
    pd._download_media(svc, fid, dest)
    return dest.read_text(encoding="utf-8")


def run_consolidate(
    target,
    day,
    journal_name,
    target_name,
    folder_id,
    out_dir,
    sa_file=None,
):
    """Pull Journal+State -> extract -> dedup -> render -> upload. Mirror archive.

    `target` waehlt die Extraktions-Quelle (learnings = Muster, baselines = neue
    PRs/Baselines), `target_name` ist die zu patchende Drive-Datei. Gibt
    (file_id, promoted_lines) zurueck; promoted_lines ist die kompakte Liste der
    sichtbar promoteten Learning-Texte (leer = nichts Neues, idempotent).

    Wirft SystemExit(non-zero) mit Pre-Seed-Anweisung, wenn Journal oder
    Ziel-State fehlt (wir legen NIE eine Datei an).
    """
    import pull_drive as pd

    creds = pd._load_credentials(sa_file, pd.SCOPES_RW)
    svc = pd._drive(creds)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    journal_text = _pull_existing(pd, svc, folder_id, journal_name, out)
    existing_text = _pull_existing(pd, svc, folder_id, target_name, out)

    candidates = extract_candidates(journal_text)
    if target == "baselines":
        # baselines.md erhaelt die harten neuen Fakten (PRs/Baselines).
        candidates = [c for c in candidates if c["source"] in ("run", "weekly")]
    else:
        # learnings.md erhaelt die wiederkehrenden Verhaltens-Muster.
        candidates = [c for c in candidates if c["source"] == "pattern"]

    new_learnings = dedup(candidates, existing_text)
    patched = render_patch(existing_text, new_learnings, day)

    local = out / target_name
    local.write_text(patched, encoding="utf-8")

    # Upload zurueck: die Datei existiert -> pull_drive._upload macht files.update.
    fid = pd._upload(svc, str(local), folder_id, target_name)
    promoted = [c["text"] for c in new_learnings]
    return fid, promoted


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Konsolidiere dauerhafte Learnings aus dem Journal in den State (Drive)."
    )
    p.add_argument(
        "--target",
        default="learnings",
        choices=TARGETS,
        help="Ziel-State: learnings (Muster) oder baselines (neue PRs/Baselines)",
    )
    p.add_argument("--as-of", help="YYYY-MM-DD (default: heute)")
    p.add_argument("--journal", default=DEFAULT_JOURNAL, help=f"Journal-Dateiname (default: {DEFAULT_JOURNAL})")
    p.add_argument("--learnings", default=DEFAULT_LEARNINGS, help=f"learnings-Dateiname (default: {DEFAULT_LEARNINGS})")
    p.add_argument("--baselines", default=DEFAULT_BASELINES, help=f"baselines-Dateiname (default: {DEFAULT_BASELINES})")
    p.add_argument("--folder", default=DEFAULT_FOLDER_ID, help="Drive-Ordner-ID (default: Senpai-AI-Chat)")
    p.add_argument("--out", default="./data", help="lokaler Scratch-Dir fuer die gepullten Dateien")
    p.add_argument("--sa-file", help="Pfad zur Service-Account-JSON (sonst env)")
    args = p.parse_args(argv)

    day = args.as_of or _date.today().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        print('{"error": "bad --as-of; expected YYYY-MM-DD"}', file=sys.stderr)
        return 1

    target_name = args.learnings if args.target == "learnings" else args.baselines

    fid, promoted = run_consolidate(
        target=args.target,
        day=day,
        journal_name=args.journal,
        target_name=target_name,
        folder_id=args.folder,
        out_dir=args.out,
        sa_file=args.sa_file,
    )

    # SICHTBAR: den promoteten Diff drucken (nur die destillierten Zeilen).
    if promoted:
        print(f"# consolidated -> {target_name} ({fid}): {len(promoted)} new")
        for text in promoted:
            print(f"+ [{day}] {text}")
    else:
        print(f"# consolidated -> {target_name} ({fid}): 0 new (idempotent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
