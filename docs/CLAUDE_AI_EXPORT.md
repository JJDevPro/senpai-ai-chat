# claude.ai-Twin-Export — Architektur, Workflow, Entscheidungs-Log

> v10.1.0 (2026-07-02). Ergebnis des Plans „claude.ai VOLL-TWIN“: das claude.ai-Projekt
> („Senpai“, Claude Max, primär iOS) wird als **generierter Zwilling** dieses Repos
> gepflegt — beste Chat-Usability dort, Determinismus + Automation hier.

## Warum

Das claude.ai-Projekt war das Original (bis v9.0.3); der Repo hat es überholt (v10:
Verdict-Kontrakt, Engines, Golden-Tests). Statt zwei Wahrheiten: **Repo = SSoT,
`claude-ai-chat-files/` = Derivat**, deterministisch generiert von
`lib/export_claude_ai.py` aus `.claude/skills/` + `lib/` + `modules/` + `CLAUDE.md`.

## Transformations-Vertrag (3 Ebenen)

1. **Marker (Tier A)** in den Quell-SKILL.md: `<!-- cc-only:start/end -->` = nur
   Claude Code (Drive-Pulls, VM-Spezifika, wird beim Export entfernt);
   `<!-- cai-only:start … cai-only:end -->` = nur claude.ai (im Repo ein inerter
   HTML-Kommentar, beim Export entkommentiert). Ersatzprosa lebt IN der Quelldatei —
   wer einen Skill ändert, sieht beide Varianten.
2. **Mechanische Rewrites (Tier B):** Skript-Pfade → `scripts/…`, Strava-MCP-Namen →
   Connector-Sprache, `lib/clock|weather|…` → Bundle-Kopien (`lib/export_rules.py`).
3. **Generierte Blöcke (Tier C):** ≤200-Zeichen-Description (claude.ai-Trigger!),
   „§0-CAI“-Preamble (Datenbeschaffungs-Matrix), Footer-Stempel (Version · Commit ·
   Content-Hash).

**Stolperdraht:** Jeder Drive-/VM-Rest im Transformat (`FORBIDDEN_EXPORT_TOKENS`)
bricht den Export ab — neuer Drive-Zugriff ohne cai-Äquivalent KANN nicht exportiert
werden. `tests/test_claude_ai_export.py` (`--check --skip-personal`) macht pytest zum
Merge-Gate: Skill geändert + nicht re-exportiert = Suite rot.

## claude.ai-Laufzeit-Mapping (recherchiert 2026-07-02, Doku-Links im Plan)

| Repo (Claude Code VM) | claude.ai-Twin |
|---|---|
| `pull_drive.py` (Service-Account) | **Hybrid-State-Bus** (v10.1.1): träge Dateien (athlete.md, Kraft-Programm, Schuhe, Schlaf-HRV) = statische Uploads im Projekt-Wissen; volatiler State (live.md & Co.) = **Drive-Connector-Read bei Chat-Start** (rohe `.md` lassen sich NICHT als synchronisierte Projekt-Dateien anbinden — Sync kann nur Google-native Formate); Roh-Daten: **Chat-Upload** → Sandbox |
| State-Write-Back `--upload` | **Drive-Connector-Update** derselben Datei (Fallback: Code-Fence) |
| `lib/weather.py` (HTTP) | Bright-Sky-URL (`assets/brightsky_url.txt`) per **Chat-Web-Fetch** → `scripts/weather.py --from-json` |
| `lib/clock.py` (VM-Uhr) | Sandbox-Uhr (`scripts/clock.py` in daily-check/weather/sync-Bundles) |
| Sheet-Voll-Replay (Banister) | `readiness-history.csv`-Anker (Projekt-Datei) + `banister.py` inkrementell; Voll-Replay bleibt Repo-Sache |
| `/automation` (VM-Cron) | — nicht portierbar (kein Cron auf claude.ai) |
| Strava MCP | Strava-Connector (Streams-Verbot unverändert) |
| Sandbox-Netz | NUR Package-Manager (pip fitparse ✓); alles andere via Chat-Fetch/Connector |

## PII-Enklave (bewusste Ausnahme, 2026-07)

`claude-ai-chat-files/` darf personalisierte Assets enthalten (Race_Strategie.md,
21km.gpx, Bright-Sky-URL mit Heim-Koordinaten) — Entscheidung des Users, privater
Repo, Copy-Paste-Fertigkeit hat Vorrang. Absicherung:
- Scanner-Ausnahme exakt gepinnt (`tests/test_claude_ai_export.py::test_pii_exception_exactly_pinned`).
- Exporter-Quellcode + Templates liegen AUSSERHALB der Enklave und werden gegen
  `tests/denylist.py` geprüft.
- Personal-Assets fließen NICHT in `content_hash` → Tests bleiben hermetisch/data-free.
- Skill-PROSA bleibt personalisierungsfrei (runtime-first: Identität kommt zur
  Laufzeit aus `athlete.md`/`live.md` als Projekt-Dateien) — personalisiert sind nur
  ganze Asset-DATEIEN.

## Workflows

**Nach jeder Skill-/Modul-/CLAUDE.md-Änderung:**
```bash
python3 lib/export_claude_ai.py     # druckt RE-UPLOAD/PASTE-Report
# → geänderte dist/*.skill in claude.ai neu hochladen, PASTE-Dateien neu einpasten
```

**Personal-Assets auffrischen** (Race-Strategie/GPX/Koordinaten in Drive geändert):
```bash
python3 lib/pull_drive.py --folder <personal-folder-id> --match "Race_Strategie.md" --exact --out ./data
python3 lib/pull_drive.py --folder <personal-folder-id> --match "21km.gpx" --exact --out ./data
python3 lib/export_claude_ai.py --refresh-personal
```
Bright-Sky-Koordinaten: optionaler ` ```senpai-export ``` `-YAML-Block in `athlete.md`
(Drive) mit `lat:`/`lon:`; Fallback = „Koordinaten ~lat/lon“-Anker im Fließtext.

**Erst-Einrichtung + Smoke-Tests:** siehe generierte `claude-ai-chat-files/README.md`,
`project-files.md` und `smoke-tests.md` (S1–S13; Ergebnisse zurück in die
Claude-Code-Session pasten).

## Grenzen des Twins (by design)

- Kein Cron/proaktive Routinen (Briefing nur on-demand als daily-check-Sektion).
- Sonntags-Payload + Journal-/Archiv-Pflege bevorzugt im Repo (Connector-Write ist
  best-effort, Code-Fence-Fallback dokumentiert).
- KW-HRV-Heatmap nur bei Multi-Tages-Upload/Range-Datei.
- Voll-Sheet-Replay (Season/Backfill) bleibt Repo-exklusiv.
