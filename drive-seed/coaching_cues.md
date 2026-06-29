<!-- Dummy — echte Cues leben NUR in Drive. Personal-Data-frei (nur Platzhalter). -->
# Senpai · Coaching-Cues (session-typ-keyed, mutable)

> **Zweck (session-übergreifende Coaching-Schleife):** Der **Run-Bundle-Skill** schreibt nach jedem
> Lauf OPEN-Cues für jedes Form-Defizit (🟡/🟠/🔴 vs V3-Ziel) unter den passenden Session-Typ. Der
> **nächste gleichartige Lauf verifiziert** sie (→ CLOSED bei Erfolg, sonst carry-forward). Der
> **Pre-Lauf (weather-runprep §5)** zieht die offenen Cues und zeigt sie als „🎯 Mental Cues".
>
> **Warum eigenes File (nicht `learnings.md`):** Cues sind **mutable** (open→closed) und
> session-typ-transient — das beißt sich mit dem append-only/Recurrence-Modell von `consolidate.py`.
>
> **Format je Cue:**
> ```
> - [YYYY-MM-DD → OPEN] <Metrik> <Ist> vs Ziel <Ziel> (Ref). Cue: "<Phrase>". Verify: <KPI> nächster <Typ>.
> - [YYYY-MM-DD → CLOSED YYYY-MM-DD] <Metrik> <Ist→Neu> ✅  (oder ❌ carry-forward)
> ```
> Pro Session-Typ **max ~3 OFFENE Cues** (die schärfsten Defizite); erledigte CLOSED unten sammeln.
> Cue-Phrasen + Ziele referenzieren die SSoT: `modules/V3_Protocol.md` (Form-Ziele + Cue-Spalte) und
> `learnings.md` (z. B. VR < 11 % / „Vorlage").

## Easy/Z2
- {{BEISPIEL: [2026-01-01 → OPEN] Vertical Ratio 12.5 % vs Ziel <11 % (learnings.md). Cue: "Vorlage aus den Knöcheln, Stride folgt — kein Trampolin." Verify: VR ≤11 % nächster Easy.}}

## Long
- {{leer — wird vom Run-Bundle befüllt}}

## Race-Sim
- {{leer}}

## Parkrun
- {{leer}}

## Tempo/Intervalle
- {{leer}}

---
<!-- CLOSED-Archiv (erledigte Cues, Verlauf) -->
## Archiv (CLOSED)
- {{leer}}
