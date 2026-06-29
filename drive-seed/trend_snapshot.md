<!-- Dummy — echte Daten leben NUR in Drive. Personal-Data-frei (nur Platzhalter). -->
# Senpai · Trend-Snapshot (Stand {{YYYY-MM-DD}})

> Schneller Read statt Sheet-Replay (CLAUDE.md §7). Abgeschlossene Wochen/Monate; HEUTE wird frisch gerechnet, nie hier gelesen. Bei Lücke/Deep-Dive → Roh-Sheets in Drive. Abk.: CTL (Fitness) · ATL (Fatigue) · TSB (Form) · KFA (Körperfett-%).
>
> **Wer schreibt:** `trend_snapshot.py` regeneriert diese Datei aus `readiness-history.csv`
> (+ `live.md`-SoT, `baselines.md`-PRs) und lädt sie via `pull_drive.py --upload` zurück.
> Daily-Check aktualisiert die laufende Woche, Payload versiegelt am KW-Ende die abgeschlossene
> Woche + rollt den Monat. **Idempotent** — rollt das Fenster (8 Wochen / 12 Monate).

### 📅 Letzte Wochen
| ISO-Woche | ⚖️ Gewicht | KFA % | 💓 HRV-Ø | ❤️ RHR | 🫁 VO2 | CTL (Fitness) | ATL (Fatigue) | TSB (Form) | 🏃 km |
|---|---|---|---|---|---|---|---|---|---|
| {{YYYY-KWnn}} | — | — | — | — | — | — | — | — | — |

### 🗓️ Letzte Monate
| Monat | ⚖️ Gewicht | KFA % | 💓 HRV-Ø | ❤️ RHR | 🫁 VO2 | CTL (Fitness) | ATL (Fatigue) | TSB (Form) | 🏃 km |
|---|---|---|---|---|---|---|---|---|---|
| {{YYYY-MM}} | — | — | — | — | — | — | — | — | — |
