<!-- Dummy — echte Daten leben NUR in Drive. Diese Datei ist ein DATA-FREIES Template. -->
<!-- Vor dem Upload alle {{PLATZHALTER}} ersetzen und die Musterwerte überschreiben. -->

# Baselines (baselines.md) — REFERENZ-LINIEN

> Persönliche Baselines + watchOS-Vergleichbarkeit (CLAUDE.md §5). Bei
> Session-Start gezogen. Dient als Bezug für VO₂max-, HRV- und PR-Ampeln.

## VO₂max
- **Persönliche Baseline:** {{VO2_BASELINE}}  <!-- Dummy: 35.0 -->
- **watchOS-Versions-Hinweis:** {{WATCHOS_HINWEIS}}  <!-- Dummy: watchOS 11 Kalibrierung -->

## HRV
- **Rollender Median (60 Tage):** {{HRV_MEDIAN}} ms  <!-- Dummy: 60 ms -->
- **Sustained-Schwelle (CLAUDE.md §5):** <50 ms (2+ Tage)

## RHR
- **Rollender Median:** {{RHR_MEDIAN}} bpm  <!-- Dummy: 55 bpm -->
- **Elevation-Trigger:** Median + 5 bpm (CLAUDE.md §6)

## Kraft-Baselines (für PR-Detection)
| Übung | Baseline |
|---|---|
| {{UEBUNG_1}}  <!-- Dummy: Bench Press --> | {{BASELINE_1}}  <!-- Dummy: 60.0 kg --> |
| {{UEBUNG_2}}  <!-- Dummy: Squat --> | {{BASELINE_2}}  <!-- Dummy: 80.0 kg --> |
