#!/usr/bin/env python3
"""
unzip_gym.py — Entpackt eine HealthFit-Gym-Bundle-ZIP und lokalisiert die für die
Gym-Analyse relevanten Innen-Dateien.

Erwartete ZIP-Namen (gym-bundle-skill SKILL.md §1):
    *-Funktionelles_Krafttraining-*.zip
    *-Krafttraining-*.zip

Relevante Innen-Dateien:
    - die Workout-Master-Markdown (*.md)          → Session-Aggregate
    - die Segmente-CSV (*-segmente.csv)           → HR pro Übungs-Segment

CLI:
    python3 unzip_gym.py <zip_path> --out ./data

Gibt die lokalen Pfade der gefundenen Dateien aus (einer pro Zeile), gelabelt:
    md=<pfad>
    segments=<pfad>

Robust: fehlende Teile werden mit 'md=NOT_FOUND' / 'segments=NOT_FOUND' gemeldet,
NIE werden Datei-Inhalte ausgegeben.
"""
import argparse
import os
import sys
import zipfile


def _is_segments_csv(name: str) -> bool:
    base = os.path.basename(name).lower()
    return base.endswith("-segmente.csv") or base.endswith("_segmente.csv") or "segmente" in base and base.endswith(".csv")


def _is_markdown(name: str) -> bool:
    return os.path.basename(name).lower().endswith(".md")


def main() -> int:
    ap = argparse.ArgumentParser(description="Entpackt eine Gym-Bundle-ZIP und findet .md + *-segmente.csv.")
    ap.add_argument("zip_path", help="Pfad zur Gym-Bundle-ZIP")
    ap.add_argument("--out", default="./data", help="Zielverzeichnis für die Extraktion (Default: ./data)")
    args = ap.parse_args()

    zip_path = args.zip_path
    out_dir = args.out

    if not os.path.isfile(zip_path):
        print(f"error=ZIP nicht gefunden: {zip_path}", file=sys.stderr)
        return 2
    if not zipfile.is_zipfile(zip_path):
        print(f"error=Keine gültige ZIP-Datei: {zip_path}", file=sys.stderr)
        return 2

    os.makedirs(out_dir, exist_ok=True)

    md_path = None
    segments_path = None
    other_count = 0

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            # Schutz gegen Pfad-Traversal beim Entpacken
            extracted = zf.extract(info, out_dir)
            if _is_segments_csv(name) and segments_path is None:
                segments_path = extracted
            elif _is_markdown(name) and md_path is None:
                md_path = extracted
            else:
                other_count += 1

    print(f"md={os.path.abspath(md_path) if md_path else 'NOT_FOUND'}")
    print(f"segments={os.path.abspath(segments_path) if segments_path else 'NOT_FOUND'}")
    print(f"other_files={other_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
