---
name: payload-skill
description: "AI Coach Wochen-Payload-Generator für den Athleten. Laden bei dem Payload-Command oder am Sonntag-KW-Abschluss (SoT-Referenz = letzte Montag-Messung). Erzeugt ein verdichtetes, copy-paste-fertiges Wochen-Briefing (SoT-Snapshot, Trainings-Absolvierung, PRs, Makro-Compliance, HRV/VO2-Trend, Learnings, Persona-State, Next-KW-Fokus) als reinen Code-Fence-Block ohne Preamble und regeneriert daraus live.md (aus dem privaten Drive-Ordner) als autoritativen State-Seed für den nächsten KW-Chat. Erkennt außerdem einen Payload-Block am Chat-Anfang und integriert ihn priorisiert. NICHT für tägliche Checks (daily-check-skill) oder KW-Rekalibrierung (sync-skill)."
---

# Payload-Skill v2.0 — KW-Abschluss-Export (skriptiertes Rollup + PATCH)

> Senpai lädt diese Datei NUR bei `Payload`-Command oder am Sonntag-Abend (KW-Abschluss).
> **Zweck:** Verdichtetes Wochen-Briefing als State-Seed für den nächsten KW-Chat. **PATCHT** `live.md` (Schema v2, privater Drive-Ordner `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde`) — nie Voll-Ersatz.
> **v2.0:** Wochen-Aggregation skriptiert (`weekly_rollup.py` — 4 Makro-Ampeln × 7 Tage, Bedtime zweistufig, HRV-/Schlaf-Ø, Δ vs Vor-KW); live.md-Update = PATCH-Semantik.

---

## 0. ⛔ AKZEPTANZKRITERIUM (Definition of Done — KEIN nice-to-have)

> **Herkunft (wichtig):** Der Payload ist ein **Relikt aus claude.ai**. Dort war er ein reiner **Context-Dump** — die Wochendaten lagen (manuell hochgeladen) im Kontext, also genügte „gib aus, was geladen ist". **In Claude Code gilt das NICHT MEHR:** der Kontext enthält die Wochendaten NICHT automatisch. Ein „dump-what's-loaded"-Payload hätte hier zwangsläufig **Lücken**.

**Ein Payload mit Lücken aus NICHT-geholten Daten ist ein NO GO — er darf NICHT ausgegeben werden.** Vor der Ausgabe gilt verbindlich:

1. **Jedes Feld** des Templates (§2) ist entweder (a) aus einer **real gezogenen Quelle** befüllt, oder (b) als `[?]` markiert **NUR** nach einem dokumentierten, fehlgeschlagenen Pull-Versuch — **mit Quelle + Grund** („Ernährungs-Sheet endet 25.06", „Nutrition nicht im HAE-Export").
2. Ein `[?]`, das nur entstand, weil der Wert „nicht im Kontext lag" / nicht gezogen wurde, ist **unzulässig** → erst ziehen (§1, CLAUDE.md §0 Hol-Pflicht).
3. Bevor der Block emittiert wird: **Gap-Check** über alle Felder. Findet sich ein nicht-quellenbelegtes `[?]` oder ein still weggelassenes Feld → **STOPP, nachziehen, dann erst ausgeben.** Verschweigen = Halluzination.

> Kurz: In Claude Code ist der Payload ein **aktiver Daten-Sammler**, kein Context-Echo. Vollständigkeit (oder belegte, begründete Abwesenheit) ist Pflicht, nicht Kür.

---

## 1. Workflow

1. **Sonntag (oder KW-Ende):** KW-Abschluss. **Die SoT-Messung ist MONTAGS** (nüchtern nach dem Aufstehen, Richtwert ≤09:00 — CLAUDE.md §7); der Payload referenziert den **letzten Mo-SoT-Wert** (manuell gepostet bzw. aus `live.md`). KEINE Sonntag-Messung erwarten oder anfordern.
2. **User:** sendet `Payload`.
3. **Senpai:** generiert den Block unten — **copy-paste-fertig, NUR Code-Fence, kein Preamble/Postamble.**
4. **Senpai:** **PATCHT `./data/live.md` (Schema v2)** mit den Payload-Werten und lädt es per Write-Back hoch:
   - Erst ziehen (`--match live.md`), dann NUR die betroffenen Zeilen/Sektionen aktualisieren: `Stand: KW…`, `## SoT-Snapshot`, `## Trend-Metriken`, `## PRs` (Gym-Zeile = Spiegel von baselines.md), `## Streaks`, `## Race-Countdown` (nur wenn sich Termine geändert haben), `## Persona-State`.
   - **⛔ KEIN Voll-Ersatz:** Sektionen ohne neue Daten bleiben byte-gleich stehen (die Kontrakt-Sektionen werden von `bootstrap`/`make_ics`/`session_menu` geparst — ein Voll-Ersatz durch den Payload-Block hat sie früher zerstört). Der Payload-BLOCK ist der Chat-Output; `live.md` ist das strukturierte State-File — zwei Formate, ein Inhalt.
   ```bash
   python3 lib/pull_drive.py --upload ./data/live.md --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --name live.md
   ```
   **Hinweis:** `live.md` ist im Drive-Ordner **pre-seeded** (Service-Account kann nur updaten, nicht anlegen). **Drive bleibt die einzige Wahrheit — kein Sheet-Append, nichts ins Git-Repo.**
5. **User:** kopiert Block als erste Message in den neuen KW-Chat → sendet danach `Sync`.

**Datenquellen:** der Live-State aus dem privaten Drive-Ordner (`live.md` + die übrigen State-Files) + Chat-Verlauf der Woche + ggf. Vor-KW-Payload (für Trends). Pull der State-Files vor Gebrauch:
```bash
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data       # dann ./data/live.md lesen
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match athlete.md --out ./data    # dann ./data/athlete.md lesen
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match baselines.md --out ./data   # dann ./data/baselines.md lesen
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match learnings.md --out ./data    # dann ./data/learnings.md lesen
```
**Zusätzlich PFLICHT (CLAUDE.md §0 Hol-Pflicht): die Wochen-Metriken ZIEHEN, die der Block braucht** — nicht nur die State-Files. Vor dem Block holen:
- **HAE-Tages-JSONs** der KW via `pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-{tag}" --out ./data` (alle 7 Tage + Vortag des Montags).
- **Trainings_v5** + **Gesundheitsdaten_v5** (`--sheet …`) für Absolvierung/CTL-ATL-TSB + Body-Comp/KW-Trend.

**⚙️ DANN das skriptierte KW-Rollup (die Zahlen des Blocks — KEIN Kopfrechnen):**
```bash
python3 .claude/skills/daily-check-skill/scripts/weekly_rollup.py --as-of {kw_sonntag} --data-dir ./data
```
→ `macros.counts` (4 Ampeln × 7 Tage, Tagestyp-Caps + 85-g-Gate aus constants), `sleep.bedtime` (zweistufig: N×voll ≤00:00 + N×halb ≤00:30 → Score), `sleep_avg_h`, `history` (HRV-/RHR-/Readiness-Ø + **Δ vs Vor-KW** aus readiness-history.csv) und **`template_lines`** (die §2-Zeilen vorgerendert). **`days_missing_hae` ≠ leer → diese Tage ERST nachziehen, Rollup neu, dann Block** (§0 Gap-Check — das Script rechnet nur über real vorhandene Dateien).

Erst nach einem **echten, fehlgeschlagenen Pull-Versuch** gilt: fehlender Wert = `[?]` markieren — **mit Quelle + Grund** („Sheet X leer", „Nutrition nicht im HAE-Export"). Nie erfinden, **nie ein Feld stillschweigend weglassen** (Verschweigen = Halluzination, §0).

---

## 2. Output-Template (exakt diese Struktur)

```
# 📦 PAYLOAD KW[Nr] — [Datumsbereich]

## 🎯 SoT-Snapshot (Mo-SoT dieser KW, Körperwaage)
- Gewicht: [X,X kg] (Δ [±X,X] vs Vor-KW)
- KFA: [XX,X%] | Bauchumfang: [XXX cm] | LBM/Muskel: [X,X]
- RHR: [XX] | VO2Max: [XX,X] [Ampel]

## 🏃 Trainings-Absolvierung
- Mo Run+Core/OK: [✅/❌/🔄] [Details]
- Mi Long Run: [✅/❌] [km/Pace/HR]
- Do Pure Gym: [✅/❌] [Highlights]
- Sa Parkrun + Partner: [✅/❌] [Zeit]
- Skips/Ausfälle + Gründe: [...]

## 🏆 Neue PRs / Meilensteine
- [Liste konkreter PRs oder "Keine"]

## 🚦 Makro-Compliance (4 Ampeln × 7 Tage)
- Protein 🟢[X]/🟡[X]/🟠[X]/🔴[X]
- Kalorien 🟢[X]/🟡[X]/🟠[X]/🔴[X]
- Carbs 🟢[X]/🟡[X]/🟠[X]/🔴[X]
- Fett 🟢[X]/🟡[X]/🟠[X]/🔴[X]
- Tages-Gesamt 🟢🟢🟢🟢: [X/7]

## 💤 HRV- & VO2-Trend
- HRV Wochen-Ø: [XX ms] [Ampel] | Trend: [↑→↓]
- VO2Max: [XX,X → XX,X] [Ampel]
- Schlaf Ø: [Xh Xmin] | Bedtime-Score: [X,X/7] ([N]×🟢 ≤00:00 voll + [N]×🟡 ≤00:30 halb)

## 🎓 Offene Learnings für KW[Nr+1]
- [1–3 konkrete Takeaways]

## 🤖 Persona-State
- Modus aktuell: [SCHARF/STOLZ]
- Letzte Anrede: [{Anrede} / {Roast-Anrede}]   # echte Formen aus athlete.md (Anrede-Tier + Roast-Bank)
- Aktive Protokolle: V3 Heavy Hybrid Polarized, Protein-Floor 150g

## 📅 Next-KW-Fokus
- Haupt-Session: [...]
- Haupt-Risiko: [...]
- Countdown: [Race-XX / Parkrun-XX / Stadtlauf-XX Tage]   # konkrete Races aus Renn-Kalender (live.md)
```

---

## 3. Ausgabe-Regeln

- **Kein Preamble, kein Postamble** — nur der Block als Code-Fence.
- **Erst ZIEHEN, dann `[?]` (§0 Hol-Pflicht).** Alle Felder ausfüllen — vorher die Wochen-Daten aktiv holen (§1). `[?]` NUR für einen Wert, dessen Quelle real gepullt wurde und leer war (mit Quelle + Grund). **Niemals `[?]` als Abkürzung statt eines Pulls, niemals ein Feld stillschweigend weglassen** — Verschweigen = Halluzination. „User ergänzt manuell" gilt erst, nachdem ICH die Quelle erfolglos gezogen habe.
- **⛔ GAP-CHECK vor dem Emit (Akzeptanzkriterium §0):** Vor der Ausgabe alle Template-Felder durchgehen. Findet sich ein nicht-quellenbelegtes `[?]` oder ein still weggelassenes Feld → **STOPP, nachziehen, DANN erst ausgeben.** Ein Payload mit Lücken aus nicht-geholten Daten ist ein NO GO und darf nicht emittiert werden.
- Ampeln immer mit Symbol (🟢🟡🟠🔴), nicht nur Wort — **Makro-/Bedtime-/HRV-Zeilen 1:1 aus `weekly_rollup.py` (`template_lines`), nie im Kopf gezählt.**
- Trend-Pfeile aus KW-Vergleich (Vor-KW-Payload falls vorhanden).
- Persona-State ehrlich aus aktuellem Chat extrahieren — keine Fake-Diagnose. Anrede-Tier + Roast-Anrede aus `athlete.md`, nicht erfinden.
- **Protokoll = V3 Heavy Hybrid Polarized** (NICHT mehr V2). Countdown-Anker = aktuelle Races aus den State-Files (privater Drive-Ordner, oben gepullt) — Renn-Strategie aus `Race_Strategie.md`, ebenfalls aus dem privaten Drive-Ordner ziehen: `python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match Race_Strategie.md --out ./data` (dann `./data/Race_Strategie.md` lesen).

---

## 4. Integration im Folge-Chat

Payload-Block am Chat-Anfang erkannt (`# 📦 PAYLOAD KW...`):
1. Payload als **autoritative Wahrheit** (Priorität über `live.md` aus dem privaten Drive-Ordner bei Konflikt).
2. `sync-skill` automatisch triggern, falls User nicht explizit `Sync` sendet.
3. Erste Antwort mit KW-Übergangsbezug: "KW[X] abgeschlossen, KW[X+1] beginnt. [Haupt-Learning]."

---

## 5. Archiv (T7, NACH dem Block — PFLICHT-Post-Schritt)

Nach der Payload-Ausgabe den Block ins rollende Journal archivieren — **Auslassen = Skill-Bruch** (das Journal ist die Langzeit-Retro-Quelle). Non-blocking NUR, wenn `senpai-journal.md` in Drive fehlt (Pre-Seed-Hinweis melden):
```bash
python3 lib/archive.py --report - --kind payload --date {kw_sonntag}   # Payload-Block via stdin
```
Fehlt `senpai-journal.md` → Pre-Seed-Hinweis melden, nicht blockieren. (`live.md`-Regeneration bleibt der separate Write-Back-Schritt.)

---

## 6. Trend-Snapshot versiegeln (PR2, NACH dem Block, best-effort)

Am KW-Ende versiegelt der Payload die **abgeschlossene Woche** als Snapshot-Zeile + rollt den Monat — nutzt die schon
gezogenen Daten (kein zweiter Pull). Der Snapshot ist ab dann der schnelle Multi-Wochen-Read für Daily/Sync (§7 CLAUDE.md):
```bash
python3 .claude/skills/daily-check-skill/scripts/trend_snapshot.py --as-of {kw_sonntag}
```
Regeneriert `trend_snapshot.md` aus `readiness-history.csv` (die Tageszeilen der KW sind via daily-check/run-bundle schon
geschrieben) und lädt ihn nach Drive. Fehlt `readiness-history.csv`/`trend_snapshot.md` → Pre-Seed-Hinweis melden, NICHT blockieren.

---

## 7. Backlog pflegen (PR3, NACH dem Block, best-effort)

Am KW-Ende `backlog.md` ziehen (`pull_drive.py --match backlog.md --out ./data`) und mit den KW-Learnings
abgleichen: **offene Learnings dieser KW** als Items übernehmen (`## Aktiv`/`## Hypothesen`, dedup gegen Bestand),
in der KW **abgeschlossene** Vorhaben nach `## Erledigt` mit Datum. Lokal regenerieren + `pull_drive.py --upload
--name backlog.md`. Fehlt `backlog.md` → Pre-Seed-Hinweis melden, NICHT blockieren. (Mutable Drive-State wie `coaching_cues.md`.)

---

**Ende payload-skill v2.0.** Code-Fence only. Zahlen aus `weekly_rollup.py`. live.md wird GEPATCHT, nie ersetzt. Felder vollständig oder belegtes `[?]`.
