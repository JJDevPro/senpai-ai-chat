# Senpai AI Coach — Claude Code Edition

**Senpai** ist ein sadistisch-scharfer Anime/IT/Gaming-Running-Coach (V3 Heavy Hybrid
Polarized, v9.0.3) — portiert von Claude.ai in einen **Claude-Code-Repo**, der **vom Handy
aus über die Claude iOS-App** ("Claude Code on the web") bedient wird. Jede Session läuft
in einer ephemeren Anthropic-Cloud-VM mit diesem Repo als CWD.

Grund für den Repo: Der Claude.ai-Chat erstickte an den großen Roh-Uploads
(Health-Auto-Export-JSON, `.fit`). Hier wird zuerst **reduziert**, und nur
**Aggregate + Persona-Verdict** landen im Modell-Kontext.

## Architektur — zwei Datentöpfe, NICHTS Persönliches in git

- **Dieses Repo = reine Coaching-Engine.** CLAUDE.md (Persona/V3-Regeln/Ampel/Safety),
  `.claude/skills/` (Analyse-Logik), `lib/` + Skripte, und die **Methoden-Module**
  (`modules/`: V3_Protocol, Daten_Parsing; CHANGELOG + Project_Index leben im
  Drive-Personal-Ordner). **Keine personenbezogenen/Health-Daten.** Teilbar.
- **Google Drive = alle Daten.** Zwei Bereiche:
  - **Truth (read-only):** HAE-JSON, `.fit`, `Trainings_v5`, `Gesundheitsdaten_v5` — vom
    iPhone aktuell gehalten, Senpai schreibt nie.
  - **Privater Ordner `Senpai-AI-Chat`** (`1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde`): Senpais
    **State** (`live`/`athlete`/`baselines`/`learnings`) + die **persönlichen Module**
    (Historie, Archiv_Historie, Schlaf_HRV_Baseline, Kraft-Programm, Race_Strategie,
    21km.gpx, Schuhe_Ausruestung). Senpai **liest** sie pro Session via `lib/pull_drive.py`
    und **schreibt** State-Updates dorthin zurück (`--upload`).
- **Nur Aggregate im Kontext.** Skripte emittieren kompaktes JSON/Tabellen auf stdout —
  **niemals** rohe Sekunden-/Minuten-Serien.

## One-Time-Setup

1. **Claude GitHub App** mit diesem privaten Repo verbinden.
2. **Env-Var `GOOGLE_SERVICE_ACCOUNT_B64`** setzen — die Cloud-Env-Settings akzeptieren nur
   `.env`-Format (einzeilig), daher das Service-Account-JSON **base64-kodiert**
   (`base64 -i service-account.json | tr -d '\n'`). Der Account braucht **Read** auf die
   Truth-Ordner und **Write** auf den `Senpai-AI-Chat`-Ordner.
3. **Network** auf *Custom*/*Full* inkl. `*.googleusercontent.com` (Drive-Downloads) und
   `wetterochs.de` (Wetter).
4. **Deps (Setup-Skript):**
   `pip install --use-pep517 pandas numpy fitparse google-api-python-client google-auth`
   — `--use-pep517` ist **Pflicht**: `fitparse` hat kein PyPI-Wheel, und sein legacy
   `setup.py`-Build scheitert auf Ubuntu 24.04 am Debian-setuptools (`install_layout`) ohne
   Build-Isolation. Inline statt `-r requirements.txt`, weil der Setup-Skript nicht zwingend
   im Repo-Root läuft. Fallback: der SessionStart-Hook (`CLAUDE_CODE_REMOTE=true`) macht
   `pip install --use-pep517 -r requirements.txt` im Repo-Root.
5. **Persönliche Dateien EINMALIG in den Drive-Ordner legen** (drag-drop). Hintergrund:
   ein Service-Account hat **keine eigene Drive-Quota** und kann in „My Drive" keine
   Dateien *anlegen* — nur **bestehende, dir gehörende Dateien aktualisieren**. Lege also
   die State-Dateien + persönlichen Module einmal selbst in den Ordner; danach
   aktualisiert Senpai den State dort automatisch. (Die Start-Dateien liegen bereit; s.
   Morgen-Notiz.)
   - **Zur Seed-Liste gehört auch eine leere `senpai-journal.md`** — das rollende
     Coaching-Journal (s.u.). Aus demselben Quota-Grund kann der Service-Account es
     **nicht selbst anlegen**: einmal leer reinlegen, danach hängt `archive.py` jeden
     fertigen Report dort an.

## Usage (vom Handy)

- **Sync** — zieht State + aktuellen Drive-Stand, re-anchored die Persona.
- **Daily Check** — HAE-Tagesscheibe + Tages-Signale + CTL/ATL/TSB + Verdict.
- **Run-Analyse** — `.fit`-Run → Aggregate (Walking-Filter v3.5, Splits, Form, Pace@Z2) →
  Verdict.

State-Updates schreibt Senpai per `pull_drive.py --upload` zurück in den Drive-Ordner.

### Coaching-Journal (rollende Historie)

Fertige Reports werden mit `lib/archive.py` als datierte Abschnitte an **ein**
markdown-Journal im Drive-Ordner angehängt — eine durchsuchbare Coaching-Historie:

```bash
python3 lib/archive.py --report ./data/daily.md --kind daily            # oder run|weekly|payload
echo "Verdict…" | python3 lib/archive.py --report - --kind run --date 2026-06-28
```

Ablauf: zieht `senpai-journal.md` (via `pull_drive.py`), hängt
`## [kind] YYYY-MM-DD\n<report>` an und lädt es per `files.update` zurück. Fehlt das
Journal, bricht es mit einer Pre-Seed-Anweisung ab (legt es **nie** selbst an — Quota).
