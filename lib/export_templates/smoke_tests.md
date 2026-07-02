# Smoke-Tests S1–S13 (claude.ai) — prompten, Ergebnis in die Claude-Code-Session pasten

Reihenfolge einhalten: **S1–S6 gaten die Skill-Nutzung**, S7–S9 gaten die Write-Back-/Wetter-Flows, S10–S13 sind End-to-End. Jeder Test hat eine „Wenn FEHLGESCHLAGEN“-Zeile — nichts davon kippt den Plan, es schaltet nur den dokumentierten Fallback scharf.

## S1 — Skills feuern im Projekt (kritischste Unbekannte)
**Setup:** `dist/sync-skill.skill` im Web unter Settings → Features/Skills hochladen. Dann IM Senpai-Projekt prompten:
> Sync
**Erwartet:** sync-skill lädt (Checklisten-Output mit KW/Race-Countdown/Overrides).
**Verifiziert:** ZIP-Format akzeptiert + Account-Skills feuern in Projekt-Chats (offiziell undokumentiert).
**Wenn FEHLGESCHLAGEN:** Skill im Chat explizit benennen („nutze sync-skill“); falls auch das nicht zieht → Skills pro Chat anhängen; Rest des Plans unverändert.

## S2 — Sandbox + Mount-Pfade
> Führe in Python aus: `import sys; print(sys.version)` — und dann in bash: `ls /mnt/user-data/uploads /mnt/user-data/outputs /mnt/skills 2>&1; ls /mnt/skills/* 2>&1 | head -30`
**Erwartet:** Python 3.11.x; Pfade existieren (oder die korrigierten Pfade werden sichtbar).
**Verifiziert:** Sandbox erreichbar; echte Mount-Pfade (unsere Skills hardcoden sie nicht, aber die Preambles nennen sie als „typisch“).
**Wenn FEHLGESCHLAGEN (andere Pfade):** Pfade notieren + pasten → Export-Preambles werden angepasst.

## S3 — Sandbox-Uhr (schaltet die deterministische Zeit frei)
> Führe aus: `from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('Europe/Berlin')))` — sag mir NUR den Wert.
**Erwartet:** stimmt mit deiner Wanduhr auf ±1 min überein.
**Verifiziert:** echte Sandbox-Uhr → Header-Zeit + Bedtime-/Roast-Fenster laufen deterministisch.
**Wenn FEHLGESCHLAGEN:** Zeit-Regel fällt auf User-Angabe > `[Zeit n/a]` zurück (v9-Verhalten); Anweisungs-Patch folgt.

## S4 — pip / fitparse
> Führe aus: `pip install --use-pep517 fitparse` und danach `import fitparse; print(fitparse.__version__)`
**Erwartet:** Installation aus PyPI klappt, Version wird gedruckt.
**Verifiziert:** Package-Manager-Whitelist → FIT-Engine lauffähig.
**Wenn FEHLGESCHLAGEN:** run-bundle degradiert auf CSV-Engine (`analyze_run.py`) mit HealthFit-CSV-Uploads.

## S5 — Bundle-Skripte ausführbar
**Setup:** `dist/daily-check-skill.skill` hochladen. Dann:
> Finde dein daily-check-skill-Verzeichnis per `ls` unter /mnt/skills und führe dort `python3 scripts/slice_hae_day.py --help` und `python3 scripts/clock.py` aus.
**Erwartet:** Usage-Text + aktuelle Berlin-Zeit.
**Verifiziert:** gebündelte Skripte laufen aus dem Skill-Ordner; Sibling-Imports funktionieren.
**Wenn FEHLGESCHLAGEN:** Fehlermeldung pasten (vermutlich Pfad-/Import-Detail → Export-Fix).

## S6 — Negativ-Test: Projekt-Dateien sind Kontext-only
> Versuche in Python `open('athlete.md')` bzw. den Dateinamen einer Projekt-Datei zu öffnen und zeig mir das Ergebnis.
**Erwartet:** FileNotFoundError — Projekt-Wissen liegt NICHT im Sandbox-Dateisystem.
**Verifiziert:** das „Inhalt nach ./data/ schreiben“-Muster ist wirklich nötig (kein stiller Irrweg).
**Wenn ÜBERRASCHEND ERFOLGREICH:** melden — dann vereinfachen wir die Preambles (direkter Datei-Zugriff).

## S7 — Drive-Connector: Lesen
> Lies `live.md` aus dem Drive-Ordner „Senpai-AI-Chat“ per Google-Drive-Connector und zitiere NUR die erste Sektion-Überschrift.
**Erwartet:** korrekter aktueller Inhalt.
**Verifiziert:** Connector-Read auf den State-Ordner.
**Wenn FEHLGESCHLAGEN:** Connector-Berechtigung im Web prüfen (Mobile-Install ist Beta) → am Desktop verbinden.

## S8 — Drive-Connector: Schreiben + Update-in-place (gated ALLE Write-Backs)
> Erzeuge eine Datei `senpai-connector-test.md` mit aktuellem Zeitstempel und speichere sie per Drive-Connector in den Ordner „Senpai-AI-Chat“. Danach: aktualisiere DIESELBE Datei mit einer zweiten Zeile.
**Erwartet (in Drive prüfen!):** Datei existiert EINMAL, mit beiden Zeilen — kein Duplikat.
**Verifiziert:** Update-Semantik des Connector-Writes → live.md/baselines.md-Write-Backs sind sicher. (Testdatei danach in Drive löschen.)
**Wenn FEHLGESCHLAGEN (Duplikat/kein Write):** Copy-Paste-Fence wird der primäre Write-Back (die Skills nennen ihn bereits als Fallback); Anweisungs-Patch folgt.

## S9 — Chat-Fetch: Bright Sky + Wetterochs
> Hole per Web-Fetch diese URL und zeig mir NUR die erste Stunde des JSON: {{BRIGHTSKY_URL_HEUTE}} — danach hole den Wetterochs-RSS (wetterochs.de) und fasse die aktuelle Ausgabe in einem Satz zusammen.
**Erwartet:** JSON-Stundenwerte + RSS-Text.
**Verifiziert:** beide Wetter-Quellen sind auf Chat-Ebene erreichbar (Sandbox braucht kein Netz).
**Wenn FEHLGESCHLAGEN (Bright Sky):** Wetterochs + User-Screenshot bleiben die Quellen (Prioritätenliste greift unverändert).

## S10 — End-to-End: Lauf-Analyse
**Setup:** `dist/run-bundle-skill.skill` hochladen; einen aktuellen `.fit` aus HealthFit in den Chat teilen.
> analysier den Lauf
**Erwartet:** run-bundle feuert, `pip install fitparse`, `analyze_run_fit.py` liefert das Aggregat-JSON, voller Report (Splits, Laufform, Decoupling, Pace@Z2, 💀 SENPAIS URTEIL) — KEINE Roh-Serien im Chat.
**Verifiziert:** Upload→Sandbox→Engine→Verdict-Kontrakt end-to-end.

## S11 — End-to-End: Daily Check
**Setup:** HAE-JSONs von heute + gestern in den Chat teilen.
> Daily Check
**Erwartet:** WHOOP-Dashboard komplett (Recovery-Ampel, Schlaf, Load, HRV-Feinverlauf, Heute-Plan, Urteil); readiness/safety_gate/sentinel liefen als Skripte; readiness-history.csv wurde aktualisiert (Connector oder Fence).
**Verifiziert:** die daily-check-Kette inkl. `readiness_history.py --csv-path` Local-Mode.

## S12 — Strava-Enrichment (während S10 prüfen)
**Erwartet:** §18-Abschnitt im Run-Report: Activity aufgelöst (±5 min/±2 %), Gear-km aktualisiert, KEIN Streams-Aufruf.
**Verifiziert:** Strava-Connector-Tools sind unter claude.ai verfügbar/benannt wie erwartet.
**Wenn FEHLGESCHLAGEN:** §18 wird per Marker auf „nur wenn Strava-Connector verbunden“ konditioniert — Report bleibt sonst vollständig.

## S13 — State-Bus-Roundtrip (Connector, beide Richtungen)
**Setup:** Der Repo-Zwilling ändert `live.md` in Drive (normaler Betrieb, z. B. nach einem Run-Report). Danach auf claude.ai:
> Lies live.md per Drive-Connector frisch und zitiere NUR die Trend-Metriken-Sektion.
**Erwartet:** der NEUE Wert (Connector liest immer den aktuellen Drive-Stand — kein Sync nötig).
**Verifiziert:** der geteilte State-Bus Repo ⇄ claude.ai über den Connector; zusammen mit S8 (Write) ist der Kreis geschlossen.
**Wenn FEHLGESCHLAGEN:** Fehlermeldung pasten — dann liegt ein Connector-Berechtigungsproblem vor (S7 erneut prüfen), kein Architektur-Problem.
