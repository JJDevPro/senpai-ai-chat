---
name: payload-skill
description: "AI Coach Wochen-Payload-Generator für den Athleten. Laden bei dem Payload-Command oder am Sonntag-KW-Abschluss nach der SoT-Messung. Erzeugt ein verdichtetes, copy-paste-fertiges Wochen-Briefing (SoT-Snapshot, Trainings-Absolvierung, PRs, Makro-Compliance, HRV/VO2-Trend, Learnings, Persona-State, Next-KW-Fokus) als reinen Code-Fence-Block ohne Preamble und regeneriert daraus live.md (aus dem privaten Drive-Ordner) als autoritativen State-Seed für den nächsten KW-Chat. Erkennt außerdem einen Payload-Block am Chat-Anfang und integriert ihn priorisiert. NICHT für tägliche Checks (daily-check-skill) oder KW-Rekalibrierung (sync-skill)."
---

# Payload-Skill v1.1 — KW-Abschluss-Export

> Senpai lädt diese Datei NUR bei `Payload`-Command oder Sonntag-Abend nach SoT.
> **Zweck:** Verdichtetes Wochen-Briefing als State-Seed für den nächsten KW-Chat. Regeneriert `live.md` (im privaten Drive-Ordner `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde`) als volatile Senpai-State.

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

1. **Sonntag (oder KW-Ende):** SoT-Messung (die Körperwaage als SoT, manuell gepostet).
2. **User:** sendet `Payload`.
3. **Senpai:** generiert den Block unten — **copy-paste-fertig, NUR Code-Fence, kein Preamble/Postamble.**
4. **Senpai:** schreibt denselben Block lokal nach `./data/live.md` (volatile Senpai-State = der Payload) und lädt ihn per Write-Back in den privaten Drive-Ordner hoch:
   ```bash
   python3 lib/pull_drive.py --upload ./data/live.md --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --name live.md
   ```
   **Hinweis:** Die Datei `live.md` muss im Drive-Ordner **vom User vorab angelegt (pre-seeded)** sein — der Service-Account kann via `files.update` aktualisieren, aber keine neue Datei in My Drive anlegen. **Drive bleibt die einzige Wahrheit — es wird KEIN Sheet angehängt, und nichts ins Git-Repo geschrieben.**
5. **User:** kopiert Block als erste Message in den neuen KW-Chat → sendet danach `Sync`.

**Datenquellen:** der Live-State aus dem privaten Drive-Ordner (`live.md` + die übrigen State-Files) + Chat-Verlauf der Woche + ggf. Vor-KW-Payload (für Trends). Pull der State-Files vor Gebrauch:
```bash
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data       # dann ./data/live.md lesen
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match athlete.md --out ./data    # dann ./data/athlete.md lesen
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match baselines.md --out ./data   # dann ./data/baselines.md lesen
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match learnings.md --out ./data    # dann ./data/learnings.md lesen
```
**Zusätzlich PFLICHT (CLAUDE.md §0 Hol-Pflicht): die Wochen-Metriken ZIEHEN, die der Block braucht** — nicht nur die State-Files. Vor dem Block holen + reduzieren:
- **HAE-Tages-JSONs** der KW (Schlaf-Ø, Bedtime-Count, HRV-Trend, Load) via `pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-{tag}" --out ./data` → über `slice_hae_day.py`/`daily_signals.py` reduzieren.
- **Trainings_v5** + **Gesundheitsdaten_v5** (`--sheet …`) für Absolvierung/CTL-ATL-TSB + Body-Comp/KW-Trend.
- **Makro-Quelle** für die 4-Ampeln-Compliance (Source-of-Truth siehe `nutrition-skill` — NICHT aus der Luft, NICHT pauschal `[?]`).

Erst nach einem **echten, fehlgeschlagenen Pull-Versuch** gilt: fehlender Wert = `[?]` markieren — **mit Quelle + Grund** („Sheet X leer", „Nutrition nicht im HAE-Export"). Nie erfinden, **nie ein Feld stillschweigend weglassen** (Verschweigen = Halluzination, §0).

---

## 2. Output-Template (exakt diese Struktur)

```
# 📦 PAYLOAD KW[Nr] — [Datumsbereich]

## 🎯 SoT-Snapshot (Wochen-Messung, Körperwaage)
- Gewicht: [X,X kg] (Δ [±X,X] vs Vor-KW)
- KFA: [XX,X%] | Viszeralfett: [X,X] | LBM/Muskel: [X,X]
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
- Schlaf Ø: [Xh Xmin] | Bedtime ≤00:30: [X/7]

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
- Ampeln immer mit Symbol (🟢🟡🟠🔴), nicht nur Wort.
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

## 5. Archiv (T7, NACH dem Block, best-effort)

Nach der Payload-Ausgabe den Block ins rollende Journal archivieren (ändert die Ausgabe NICHT — reiner Post-Schritt):
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

**Ende payload-skill v1.1.** Code-Fence only. Felder vollständig oder `[?]`. V3, nicht V2.
