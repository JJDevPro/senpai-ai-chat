# CHANGELOG — senpai-ai-chat (personal-data-frei)

> Repo-lokales Changelog (Trigger `Changelog`, CLAUDE.md §9). Nur Methode/Architektur —
> KEINE Personendaten. Das alte Drive-CHANGELOG ist Alt-Bestand (Putz-Liste PR-6).

## v10.1.1 — Twin-Fix: Hybrid-State-Bus (2026-07-02)

Live-Befund bei der Erst-Einrichtung: rohe `.md`-Drive-Dateien lassen sich NICHT
als synchronisierte Projekt-Dateien anbinden („URL-Auflösung fehlgeschlagen" —
der Projekt-Wissen-Sync kann nur Google-native Formate wie Docs/Sheets). Der
State-Bus wird zweistufig: **statische Uploads** für träge Dateien (athlete.md,
Kraft-Programm.md, Schuhe_Ausruestung.md, Schlaf_HRV_Baseline.md) + **Drive-
Connector-Read bei Chat-Start** für volatilen State (live.md, baselines.md,
learnings.md, gear.md, coaching_cues.md, backlog.md, trend_snapshot.md,
readiness-history.csv) — Connector-Stand schlägt statische Kopie und Memory.
Angepasst: Anweisungs-§0/§7/§9/§11, alle Skill-Preambles (`_PRE_STATEREAD`),
project-files.md (v2), Smoke-Test S13, README, Export-Doku.

## v10.1.0 — claude.ai-Twin: generierter Voll-Export (2026-07-02)

Das claude.ai-Projekt (Original bis v9.0.3, Skills-Snapshot 24./25.06.) wird ab
jetzt als **generierter Zwilling** gepflegt: Repo = SSoT, `claude-ai-chat-files/` =
Derivat. Kernstücke:

- **Exporter:** `lib/export_claude_ai.py` + Regel-Registry `lib/export_rules.py` +
  Templates `lib/export_templates/` — deterministisch (Doppellauf byte-identisch),
  `--check` als Drift-Gate, `--refresh-personal` für Personal-Assets,
  Bundle-Import-Smoke-Test. Output: 8 Skill-Zips (`dist/`), diffbare Quellen
  (`src/`), generierte Projekt-Anweisungen (v10-Port), Projekt-Datei-Checkliste,
  Smoke-Tests S1–S13, MANIFEST mit Re-Upload-Report.
- **Marker-Vertrag:** `cc-only`/`cai-only`-HTML-Marker in allen 8 SKILL.md — die
  claude.ai-Ersatzprosa lebt in der Quelldatei; unmarkierter Drive-Zugriff bricht
  den Export (FORBIDDEN-Gate).
- **Local-Mode-Chirurgie (nützt beiden Welten):** `readiness_history.py --csv-path`,
  `trend_snapshot.py --local`, `consolidate.py --local`, `weather.py --from-json`/
  `--print-url` — Drive-Glue jetzt konditional, offline testbar.
- **claude.ai-Laufzeit-Mapping:** State via Drive-synchronisierte Projekt-Dateien
  (auto-aktuell), Roh-Daten via Chat-Upload → Sandbox, Write-Back via
  Drive-Connector-Update (Fallback Code-Fence), Bright Sky via Chat-Fetch +
  `--from-json`, Zeit via Sandbox-Uhr. Briefing → daily-check-Sektion, Menu →
  sync-skill; `/automation` bleibt VM-only.
- **PII-Enklave:** `claude-ai-chat-files/` bewusst personalisiert (nur ganze
  Asset-Dateien; Prosa bleibt runtime-first) — Scanner-Ausnahme exakt gepinnt,
  Exporter-Quellen weiter PII-gescannt. Doku: `docs/CLAUDE_AI_EXPORT.md`.
- Alte Root-`.skill`-Snapshots (24./25.06.) entfernt — Historie bleibt in git.

## v10 — SSoT-Sanierung für Opus 4.8 + Reproduzierbarkeits-Garantie (2026-07-02)

Ausgangspunkt: Voll-Audit (90 Agenten, adversarial verifiziert — 73 CONFIRMED
Findings) + 17 User-Entscheidungen. Leitprinzip: **Skripte entscheiden** — jede
Zahl/Ampel/Gate kommt als maschinenlesbares JSON aus Python; das LLM liefert nur
Persona/Ton. Acht PR-Etappen:

- **PR-1 · Kanon (#24):** `lib/constants.py` als einzige Konstanten-Registry
  (HR-Zonen, HRV/VO2/Atmung/TRIMP/TSB-Bänder, Hitze-Tax 3,5, Bedtime zweistufig
  00:00/00:30, Fett = Tagestyp-Cap + 85-g-Gate, SoT-Wiegetag Mo);
  `test_threshold_consistency.py` erzwingt Skript+Doku-Gleichstand.
  Doku-Widersprüche getilgt (Pace@Z2 = Steady-Z2-Segment, Viszeralfett als KPI
  gestrichen, VR <11 %, tote Referenzen).
- **PR-2 · lib-Härtung (#25):** consolidate-PR-Regex, make_ics-Zielzeit-Crash,
  pull_drive (`--exact`, Upload-Whitelist + Ordner-Guard, Tab-Fehler statt
  stillem Fallback), weather Slot-Floor + Wind-Einheiten, Berlin-Datum überall,
  bootstrap-WARN, archive Lost-Update-Guard. Tests für die lib-Kerne.
- **PR-3 · daily-check-Determinismus (#26):** daily_signals Tag-Shift-Fix
  (as_of pinnt Kalendertage, kein Zukunfts-Leck, Wasser-Tagessumme,
  kJ/kcal-Autodetect); safety_gate WARN+data_gaps statt Fail-open + CSV-Vortags-
  HRV; sentinel kalender-konsekutiv + rhr_deviation; EIN Readiness-Score
  (Sentinel-Pflicht-Input); Body-Battery-Verkettung (--prev-bb); trend_snapshot
  Backfill-Sort + Partial-Marker; stats MM:60-Fix + Event-Hardcode raus;
  slice weiches SoT-Fenster (<12:00); banister.day_trimp.
- **PR-4 · run-bundle + Race (#27):** banister-Kopien byte-identisch + Parity-
  Tripwire; analyze_run_fit v3.14 (Kadenz-Absenz ≠ 0 spm, Start-Temp-Label,
  Top-Speed-Spike-Schutz, §11-Ampeln + EF engine-seitig, fastest_km,
  schema_version); analyze_run = echte CSV-Engine (geteilte Funktionen);
  parse_workout Mismatch-Flag; Race-Pfad skriptiert (stats hm_projection mit
  Cutoff-/Gehpausen-Budget, pacing_card saniert, race-projection v1.1);
  run-SKILL-Diät (Changelog-Block raus, H1-Paces → Drive-State).
- **PR-5 · gym-bundle-Engine (#28):** analyze_gym v2.0 als deterministische
  CLI-Engine (Text-Parser, Segment-Mapping ohne Raten, PR-Detection +
  baseline_updates, Tonnage-Bänder 50–65/25–35/8–15, Belastungs-Score,
  Bedtime-Ampel, Re-Entry-80 %); PR-Write-Back autonom + sichtbar nach
  baselines.md (SSoT), live.md nur Spiegel.
- **PR-6 · State-Layer & Drive (#29):** live.md Schema v2 (Kontrakt-Sektionen für
  bootstrap/make_ics/session_menu, Race-Countdown = Renn-Kalender-SSoT);
  Payload v2.0 mit PATCH-Semantik statt Voll-Ersatz + skriptiertem KW-Rollup
  (`weekly_rollup.py`: 4 Makro-Ampeln × 7 Tage, Bedtime zweistufig, HRV-/
  Schlaf-Ø, Δ vs Vor-KW); sync-skill Renn-Kalender-Fix; senpai-journal.md
  registriert + Append-Pflicht; CHANGELOG ins Repo; Drive-Write-Backs +
  Putz-Liste als Session-Aktionen.
- **PR-7 · Privacy strikt + Golden-Tests (#30):** Identitäts-Tokens nur noch
  als gesaltete SHA-256-Hashes (tests/denylist.py), Scanner über tests/ +
  Dateinamen + Koordinaten-Muster; Heim-Strecke/Partner-Layer/Beispielwerte →
  athlete.md-Pointer. Golden-Tests: FIT-Engine-Vollreport (assemble()-Refactor
  + Fake-Fit), Daily-Kette, Gym-Engine, Banister-Multi-Step-Drift; Suite ohne
  Skips.
- **PR-8 · CLAUDE.md v10.0.0:** Verdict-Kontrakt dokumentiert (Skripte rechnen,
  LLM spricht), Betriebsmodus präzisiert (Opus 4.8 + ultracode; Workflow erbt
  Session-Modell, nie Haiku), Pace@Z2-Quick-Command liest live.md-Engine-Wert,
  Anrede-Platzhalter-Lock, Schwellen-SSoT-Pointer in §5.

## v9.0.x — SSoT-Edition (Port aus claude.ai)

Hot-Core schlank, Detail in Skills/Modulen; Identität/State in Drive
(personal-data-freies Repo); Kernregel „nur Aggregate in den Kontext";
echte VM-Uhr via `lib/clock.py`; Metaphern-Rebalancing (Anime · IT · Gaming).
Details: Git-Historie.
