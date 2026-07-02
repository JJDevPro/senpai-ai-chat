# claude-ai-chat-files/ — der claude.ai-Twin (generiert)

> **⚠️ PII-ENKLAVE:** Dieser Ordner ist die EINZIGE bewusst personalisierte Zone des Repos (Entscheidung 2026-07, siehe `docs/CLAUDE_AI_EXPORT.md`). Der PII-Scanner (`tests/test_no_personal_data.py`) klammert genau diesen Präfix aus. Personal-Assets liegen ausschließlich unter `src/*/assets/`.
> **⚠️ GENERIERT:** Alles hier erzeugt `python3 lib/export_claude_ai.py` aus `.claude/skills/` + `lib/` + `modules/` + `CLAUDE.md`. **Nie von Hand editieren** — Änderungen im Repo machen und neu exportieren.

## Layout

| Pfad | Was |
|---|---|
| `dist/<skill>.skill` | Upload-fertige Skill-ZIPs (deterministisch gebaut) |
| `src/<skill>/` | Entpackte, diffbare Quelle jedes Zips |
| `project-instructions.md` | Projekt-Anweisungen für claude.ai (ersetzt v9.0.3 komplett) |
| `project-files.md` | Ziel-Zustand des Projekt-Wissens + Umbau-Checkliste |
| `smoke-tests.md` | S1–S13-Prompts zum Verifizieren der claude.ai-Fähigkeiten |
| `MANIFEST.json` | Versions-/Hash-Stand pro Artefakt (Re-Upload-Anker) |

## Erst-Einrichtung (einmalig, am besten im Web — iOS kann Skills nutzen, Upload ist Web-Sache)

1. **Skills hochladen:** claude.ai → Settings → Features/Skills → jede Datei aus `dist/` hochladen (bereits vorhandene Alt-Versionen vorher entfernen).
2. **Projekt-Anweisungen ersetzen:** Inhalt von `project-instructions.md` komplett in die Projekt-Anweisungen des Senpai-Projekts einpasten.
3. **Projekt-Wissen umbauen:** Checkliste in `project-files.md` abarbeiten (4 statische Uploads rein, volatiler State läuft per Drive-Connector, große Referenzen raus — die stecken jetzt in den Skill-Zips). **Achtung:** rohe `.md`-Drive-Dateien lassen sich NICHT als synchronisierte Projekt-Dateien anbinden — deshalb das Hybrid-Modell.
4. **Smoke-Tests fahren:** `smoke-tests.md` von S1 an durchgehen, Ergebnisse in die Claude-Code-Session pasten.

## Laufender Sync (nach jeder Skill-/Modul-Änderung im Repo)

```
python3 lib/export_claude_ai.py          # regeneriert diesen Ordner
```
Der Exporter druckt einen **Re-Upload-Report** (welche `dist/*.skill` sich geändert haben → nur die neu hochladen; `PASTE:`-Zeilen → Anweisungen neu einpasten). `MANIFEST.json` committen — `pytest` (Drift-Guard) erzwingt, dass Export und Quellen synchron bleiben.

**Nie nötig:** State-Dateien (live.md & Co.) syncen — Senpai liest sie auf claude.ai per Drive-Connector immer frisch (Step-0) und schreibt per Connector-Update zurück. Nur die 4 statischen Uploads (athlete.md, Kraft-Programm, Schuhe, Schlaf-HRV-Baseline) brauchen bei inhaltlicher Änderung ein manuelles Re-Upload.

## Personal-Assets auffrischen

Race-Strategie/GPX/Bright-Sky-URL ändern sich in Drive → einmalig:
```
python3 lib/pull_drive.py --folder <personal-folder> --match "Race_Strategie.md" --exact --out ./data
python3 lib/pull_drive.py --folder <personal-folder> --match "21km.gpx" --exact --out ./data
python3 lib/export_claude_ai.py --refresh-personal
```
