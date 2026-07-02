<!-- Dummy — echte Daten leben NUR in Drive. Diese Datei ist ein DATA-FREIES Template. -->
<!-- Vor dem Upload alle {{PLATZHALTER}} ersetzen und die Musterwerte überschreiben. -->

# Live-State (live.md) — VOLATILER LIVE-STATE · Schema v2

> Wird bei Session-Start via `pull_drive.py` gezogen und per `--upload`
> zurückgeschrieben (CLAUDE.md §0 Write-Back). Autoritativer State-Seed.
>
> **⚡ PATCH-Semantik (Schema v2):** Updates (Payload, PR-Spiegel, SoT-Werte)
> ändern NUR die betroffenen Zeilen/Sektionen — NIE die Datei als Ganzes
> ersetzen. Sektionen, für die ein Update keine Daten hat, bleiben
> unangetastet (kein Voll-Ersatz, kein stiller Sektions-Verlust).
>
> **Kontrakt (von Skripten geparst — Sektions-Namen NICHT umbenennen):**
> die "Stand:"-Zeile mit der KW (bootstrap-Banner) · die Sektionen
> "Race-Countdown" (make_ics + session_menu --full; Zeilenform siehe unten)
> und "Aktive Overrides" (bootstrap zählt die Bullets) · die Zeilen-Labels
> Gewicht/HRV/VO2 (bootstrap-Metriken). Keine dieser Token-Sequenzen darf
> zusätzlich in Prosa/Kommentaren auftauchen (Parser nehmen den ERSTEN Treffer).

Stand: KW{{KW}} · {{STAND_DATUM}}  <!-- Dummy: 2026-01-05, KW-Nr. einsetzen -->

## SoT-Snapshot (manuell, Mo nüchtern nach dem Aufstehen — Richtwert ≤09:00)
- **Gewicht (SoT):** {{GEWICHT_KG}} kg  <!-- Dummy: 80.0 kg -->
- **KFA:** {{KFA_PCT}} %  <!-- Dummy: 18.0 % -->
- **Bauchumfang (optional, manuell):** {{BAUCHUMFANG_CM}} cm  <!-- Dummy: 90 cm -->
- **SoT-Datum:** {{SOT_DATUM}}  <!-- Dummy: der letzte Montag -->

## Trend-Metriken
- **HRV (Nacht-Ø):** {{HRV_MS}} ms  <!-- Dummy: 60 ms -->
- **VO2max:** {{VO2}}  <!-- Dummy: 35.0 -->
- **Pace@Z2 (temp-normalisiert 18°C, Engine-Wert aus run-bundle §8c):** {{PACE_Z2}}  <!-- Dummy: 9:00/km -->

## PRs (Loot)
<!-- Lauf-PRs leben HIER; Gym-PRs: SSoT = baselines.md (Gym-PR-Abschnitt),
     diese Zeile ist nur der SPIEGEL (gym-bundle §6). -->
- **5k:** {{PR_5K}}  <!-- Dummy: 28:00 -->
- **HM:** {{PR_HM}}  <!-- Dummy: 2:10:00 -->
- **Gym PRs (Spiegel, Stand-KW s. o.):** {{GYM_PR_MIRROR}}  <!-- Dummy: Beinpresse 95 kg · Waden 110 kg -->

## Race-Countdown
<!-- Renn-Kalender-SSoT (sync-skill §2, race-projection §1, make_ics).
     Zeilenform: "- <Event> — TT.MM.JJJJ [@HH:MM] · <X> km [· Ziel <Zeit>]"
     Zeilen ohne volles Datum ("TBC") überspringt make_ics.
     ⚠️ KEINE echten Datums-Angaben in Kommentaren dieser Sektion —
     der Parser liest auch Kommentare. -->
- {{RACE_1}}
- {{RACE_2}}

## Streaks
- **Gym-Streak:** {{GYM_STREAK}}  <!-- Dummy: 0 Wochen -->
- **Parkrun-Counter:** {{PARKRUN_N}}  <!-- Dummy: #0 -->

## Aktive Overrides
<!-- Ein Bullet je Override (bootstrap zählt sie); "- keine" zählt als 0. -->
- keine

## Persona-State
- **Modus:** {{PERSONA_STATE}}  <!-- Dummy: SCHARF -->
