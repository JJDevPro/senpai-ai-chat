<!-- Dummy — echte Daten leben NUR in Drive. Personal-Data-frei (nur Platzhalter). -->
# Senpai · Coaching-/Ideen-Backlog (mutable)

> **Zweck (längerfristige Vorhaben über die Session-Form-Cues hinaus):** Senpais persistierte,
> offene To-dos / Experimente / Hypothesen — das, was über mehrere Wochen verfolgt wird, NICHT in
> eine einzelne Session passt und sonst zwischen Chats verloren ginge. Beispiele: „VR aktiv unter
> 11 % testen", „Protein-Floor-Streak 5 Tage halten", „Gym-Re-Entry-Progression", „2. Race fixieren".
>
> **Wer schreibt (Nebeneffekt jeder Analyse):** `daily-check` (z. B. Protein-Floor-Fail → To-do),
> `run-bundle` (Form-Defizit über mehrere Läufe → Experiment), `payload`/`sync` (offene Learnings
> übernehmen). Items werden gegen den Bestand **dedupliziert**; Erledigtes wandert mit Datum nach
> `## Erledigt`.
>
> **Wer surft/reviewt:** `/briefing` + `/sync` zeigen die Top-offenen Items (kurz) und fragen bei
> mutmaßlicher Erledigung nach; `/menu` verweist drauf.
>
> **Abgrenzung:** `coaching_cues.md` = **metrische Form-Cues pro Lauf-Typ** (open→closed, transient).
> `backlog.md` = **breitere, längerfristige Vorhaben**. `learnings.md` = append-only, wiederkehrende
> Lehren (consolidate.py). Backlog ist mutable → eigenes File, kein learnings-Spam.
>
> **Format je Item:**
> ```
> - [YYYY-MM-DD] <Vorhaben/Hypothese> — Owner-Signal: <welche Metrik/welcher Trigger schließt es?>
> - [YYYY-MM-DD → ERLEDIGT YYYY-MM-DD] <Vorhaben> ✅ <1 Satz Ergebnis>
> ```
> Pro Sektion die **schärfsten ~5 offenen Items** oben; alte/erledigte nach `## Erledigt`.

## Aktiv
> Konkrete offene To-dos mit klarem Abschluss-Signal.
- {{BEISPIEL: [2026-01-01] Protein-Floor 150 g an 5 Tagen in Folge treffen — schließt bei 5er-Streak im nutrition-Tracking.}}

## Experimente
> Laufende Tests einer Intervention (n=1), bis ein Verdikt steht.
- {{BEISPIEL: [2026-01-01] Vertical Ratio aktiv <11 % über 3 Easy-Läufe — Verify via run-bundle run_form, dann Verdikt nach learnings.md.}}

## Hypothesen
> Vermutungen, die noch Daten brauchen, bevor sie Experiment/Regel werden.
- {{BEISPIEL: [2026-01-01] „Schlaf <6 h drückt die Z2-Pace am Folgetag messbar" — sammeln, bis genug Paarungen da sind.}}

---
<!-- Erledigt-Archiv (abgeschlossene Items, Verlauf) -->
## Erledigt
- {{leer}}
