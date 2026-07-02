---
name: payload-skill
description: "Senpais Wochen-Payload. Trigger: Payload, Sonntag-KW-Abschluss, Wochen-Export. Verdichtetes KW-Briefing als Code-Fence + live.md-PATCH — copy-paste-fertig für den nächsten KW-Chat."
---


# Payload-Skill v2.0 — KW-Abschluss-Export (skriptiertes Rollup + PATCH)

## §0-CAI · Laufzeit & Datenbeschaffung (claude.ai)

> Dieses Bundle ist der claude.ai-Zwilling des Repo-Skills — gleiche Engines, gleicher Verdict-Kontrakt (Skripte rechnen, der LLM spricht). Skripte laufen in der Code-Sandbox (Python 3.11). Vorbereitung: `mkdir -p ./data`. Den Skill-Ordner per `ls` unter `/mnt/skills/` finden (Pfade nie blind hardcoden), Skripte als `python3 scripts/<name>.py` aus dem Skill-Ordner aufrufen.

**Datenbeschaffung:**

| Was | Woher |
|---|---|
| readiness-history.csv (KW-Anker) | Projekt-Datei → nach `./data/readiness-history.csv` schreiben |
| Makro-/Tages-Detail (falls nötig) | Tages-JSONs bzw. Monats-CSV als Chat-Upload anfordern — anfordern statt raten (Hol-Pflicht) |
| live.md · backlog.md · trend_snapshot.md | State-Read (Projekt-Wissen bzw. Drive-Connector frisch, siehe unten) → bei Skript-Bedarf Inhalt nach `./data/<name>` schreiben |

**State-Read:** Rohe `.md`-State-Dateien lassen sich in claude.ai NICHT als Drive-synchronisierte Projekt-Dateien anbinden (Sync kann nur Google-native Formate). Regel: statische Kopie im Projekt-Wissen = Grundkontext; bei Zahlen-Relevanz (`live.md`, `baselines.md`, `gear.md`, `readiness-history.csv`) die Datei per Drive-Connector aus „Senpai-AI-Chat“ FRISCH lesen — Connector-Stand schlägt jede statische Kopie.

**Write-Back:** Google-Drive-Connector — die BESTEHENDE Datei im Drive-Ordner „Senpai-AI-Chat“ aktualisieren (nie ein Duplikat anlegen). Fallback bei fehlgeschlagenem Write: kompletten neuen Datei-Inhalt als Code-Fence ausgeben, der User ersetzt ihn in Drive.

**Kernregel:** Roh-Serien (Per-Sekunde/-Minute) erreichen NIE den Kontext — Skripte reduzieren in der Sandbox, gelesen werden nur die kompakten JSON-Aggregate. Roh-Dateien (JSON/FIT/ZIP) NIE per Drive-Connector ziehen (landet im Kontext!) — immer als Chat-Upload anfordern (landet in der Sandbox).

**Hinweis:** Der Sonntags-Payload läuft bevorzugt im Repo-Zwilling (Claude Code); diese Variante ist der mobile Fallback mit identischem Output-Kontrakt.

---


> Senpai lädt diese Datei NUR bei `Payload`-Command oder am Sonntag-Abend (KW-Abschluss).
> **Zweck:** Verdichtetes Wochen-Briefing als State-Seed für den nächsten KW-Chat. **PATCHT** `live.md` (Schema v2, Drive-synchronisierte Projekt-Datei; Write-Back per Google-Drive-Connector in den Ordner „Senpai-AI-Chat") — nie Voll-Ersatz.
> **v2.0:** Wochen-Aggregation skriptiert (`weekly_rollup.py` — 4 Makro-Ampeln × 7 Tage, Bedtime zweistufig, HRV-/Schlaf-Ø, Δ vs Vor-KW); live.md-Update = PATCH-Semantik.

---

## 0. ⛔ AKZEPTANZKRITERIUM (Definition of Done — KEIN nice-to-have)

> **Herkunft (wichtig):** Der Payload war ursprünglich ein reiner **Context-Dump** — „gib aus, was geladen ist". **Das gilt NICHT MEHR:** auch hier liegen die WOCHEN-Daten (HAE-Tages-JSONs, Trainings-Detail) NICHT automatisch im Kontext — nur die State-Projekt-Dateien. Ein „dump-what's-loaded"-Payload hätte zwangsläufig **Lücken**.

**Ein Payload mit Lücken aus NICHT-geholten Daten ist ein NO GO — er darf NICHT ausgegeben werden.** Vor der Ausgabe gilt verbindlich:

1. **Jedes Feld** des Templates (§2) ist entweder (a) aus einer **real gezogenen Quelle** befüllt, oder (b) als `[?]` markiert **NUR** nach einem dokumentierten, fehlgeschlagenen Pull-Versuch — **mit Quelle + Grund** („Ernährungs-Sheet endet 25.06", „Nutrition nicht im HAE-Export").
2. Ein `[?]`, das nur entstand, weil der Wert „nicht im Kontext lag" / nicht gezogen wurde, ist **unzulässig** → erst ziehen (§1, CLAUDE.md §0 Hol-Pflicht).
3. Bevor der Block emittiert wird: **Gap-Check** über alle Felder. Findet sich ein nicht-quellenbelegtes `[?]` oder ein still weggelassenes Feld → **STOPP, nachziehen, dann erst ausgeben.** Verschweigen = Halluzination.

> Kurz: Der Payload ist ein **aktiver Daten-Sammler**, kein Context-Echo — fehlende Wochen-Daten werden ANGEFORDERT (Chat-Upload) statt geraten. Vollständigkeit (oder belegte, begründete Abwesenheit) ist Pflicht, nicht Kür.

---

## 1. Workflow

> **CAI-Twin-Notiz:** Der Sonntags-Payload läuft bevorzugt im Repo-Zwilling (Claude Code on the web); diese claude.ai-Variante ist der mobile Fallback — identischer Output-Kontrakt (§2-Block, PATCH-Semantik, Gap-Check §0).

1. **Sonntag (oder KW-Ende):** KW-Abschluss. **Die SoT-Messung ist MONTAGS** (nüchtern nach dem Aufstehen, Richtwert ≤09:00 — CLAUDE.md §7); der Payload referenziert den **letzten Mo-SoT-Wert** (manuell gepostet bzw. aus `live.md`). KEINE Sonntag-Messung erwarten oder anfordern.
2. **User:** sendet `Payload`.
3. **Senpai:** generiert den Block unten — **copy-paste-fertig, NUR Code-Fence, kein Preamble/Postamble.**
4. **Senpai:** **PATCHT `./data/live.md` (Schema v2)** mit den Payload-Werten und schreibt es zurück:
   - `live.md` ist Drive-synchronisierte Projekt-Datei (Inhalt im Kontext) → Inhalt 1:1 nach `./data/live.md` schreiben, dann NUR die betroffenen Zeilen/Sektionen aktualisieren: `Stand: KW…`, `## SoT-Snapshot`, `## Trend-Metriken`, `## PRs` (Gym-Zeile = Spiegel von baselines.md), `## Streaks`, `## Race-Countdown` (nur wenn sich Termine geändert haben), `## Persona-State`.
   - **⛔ KEIN Voll-Ersatz:** Sektionen ohne neue Daten bleiben byte-gleich stehen (die Kontrakt-Sektionen werden von anderen Routinen geparst — ein Voll-Ersatz durch den Payload-Block hat sie früher zerstört). Der Payload-BLOCK ist der Chat-Output; `live.md` ist das strukturierte State-File — zwei Formate, ein Inhalt.
   - **Write-Back:** die BESTEHENDE `live.md` im Drive-Ordner „Senpai-AI-Chat" per Google-Drive-Connector aktualisieren — NIE ein Duplikat anlegen. Schlägt der Connector-Write fehl → kompletten neuen `live.md`-Inhalt als Code-Fence ausgeben, der User ersetzt ihn in Drive. **Drive bleibt die einzige Wahrheit.**
5. **User:** kopiert Block als erste Message in den neuen KW-Chat → sendet danach `Sync`.

**Datenquellen:** der Live-State (`live.md` + die übrigen State-Files) + Chat-Verlauf der Woche + ggf. Vor-KW-Payload (für Trends). Die State-Files (`live.md`, `athlete.md`, `baselines.md`, `learnings.md`) sind Drive-synchronisierte Projekt-Dateien — ihr Inhalt steht im Kontext; was das Rollup-Skript braucht, 1:1 nach `./data/<name>` schreiben.
**Zusätzlich PFLICHT (Hol-Pflicht): die Wochen-Metriken BESCHAFFEN, die der Block braucht** — anfordern statt raten, nicht nur die State-Files. Vor dem Block:
- **Anker:** `readiness-history.csv` (Projekt-Datei) 1:1 nach `./data/readiness-history.csv` schreiben — speist HRV-/RHR-/Readiness-Ø + Δ vs Vor-KW im Rollup.
- **HAE-Tages-JSONs der KW** (alle 7 Tage + Vortag des Montags) als **Chat-Upload anfordern** — Roh-JSON/FIT/ZIP NIE per Drive-Connector in den Kontext ziehen (§0-Kernregel: nur Aggregate). Upload-Verzeichnis per `ls` lokalisieren (typisch `/mnt/user-data/uploads`, nie blind hardcoden), Dateien nach `./data/` kopieren.
- **Makro-/Trainings-Detail bei Bedarf:** die Monats-/Range-CSV (Trainings-/Gesundheits-Export) bzw. fehlende Tages-JSONs ebenfalls als Chat-Upload anfordern — fehlende Daten werden ANGEFORDERT, nie geraten, nie verschwiegen.

**⚙️ DANN das skriptierte KW-Rollup (die Zahlen des Blocks — KEIN Kopfrechnen):**
```bash
python3 scripts/weekly_rollup.py --as-of {kw_sonntag} --data-dir ./data
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
- **Protokoll = V3 Heavy Hybrid Polarized** (NICHT mehr V2). Countdown-Anker = aktuelle Races aus den State-Files (Projekt-Dateien, §1) — Renn-Strategie bei Bedarf aus `Race_Strategie.md` per Google-Drive-Connector lesen (Ordner „Senpai-AI-Chat"; Markdown-Modul, kein Roh-Datenfile → Connector-Read erlaubt).

---

## 4. Integration im Folge-Chat

Payload-Block am Chat-Anfang erkannt (`# 📦 PAYLOAD KW...`):
1. Payload als **autoritative Wahrheit** (Priorität über `live.md` aus dem privaten Drive-Ordner bei Konflikt).
2. `sync-skill` automatisch triggern, falls User nicht explizit `Sync` sendet.
3. Erste Antwort mit KW-Übergangsbezug: "KW[X] abgeschlossen, KW[X+1] beginnt. [Haupt-Learning]."

---

## 5. Archiv (NACH dem Block — best-effort, optional)

Nach der Payload-Ausgabe den Block best-effort ins rollende Journal archivieren: `senpai-journal.md` per Google-Drive-Connector lesen, den Payload-Block als neue Sektion (KW + Datum) anhängen und die BESTEHENDE Drive-Datei aktualisieren (kein Duplikat). Schlägt der Connector-Write fehl oder fehlt die Datei → Hinweis melden, NICHT blockieren. (`live.md`-Regeneration bleibt der separate Write-Back-Schritt, §1 Schritt 4.)

---

## 6. Trend-Snapshot versiegeln (PR2, NACH dem Block, best-effort)

Am KW-Ende versiegelt der Payload die **abgeschlossene Woche** als Snapshot-Zeile + rollt den Monat — nutzt die schon beschafften Daten (kein zweiter Fetch). Der Snapshot ist ab dann der schnelle Multi-Wochen-Read für Daily/Sync:
```bash
python3 scripts/trend_snapshot.py --local --history ./data/readiness-history.csv --out-file ./data/trend_snapshot.md
```
Danach `./data/trend_snapshot.md` per Google-Drive-Connector als Update der BESTEHENDEN `trend_snapshot.md` (Ordner „Senpai-AI-Chat") zurückschreiben — kein Duplikat; Fallback: Inhalt als Code-Fence ausgeben. Fehlt `readiness-history.csv`/`trend_snapshot.md` → Hinweis melden, NICHT blockieren.

---

## 7. Backlog pflegen (PR3, NACH dem Block, best-effort)

Am KW-Ende `backlog.md` (Drive-synchronisierte Projekt-Datei — Inhalt im Kontext, sonst per Google-Drive-Connector lesen) mit den KW-Learnings abgleichen: **offene Learnings dieser KW** als Items übernehmen (`## Aktiv`/`## Hypothesen`, dedup gegen Bestand), in der KW **abgeschlossene** Vorhaben nach `## Erledigt` mit Datum. Aktualisierte Fassung per Connector-Update der BESTEHENDEN `backlog.md` zurückschreiben (kein Duplikat; Fallback: Code-Fence). Fehlt `backlog.md` → Hinweis melden, NICHT blockieren. (Mutable Drive-State wie `coaching_cues.md`.)

---

**Ende payload-skill v2.0.** Code-Fence only. Zahlen aus `weekly_rollup.py`. live.md wird GEPATCHT, nie ersetzt. Felder vollständig oder belegtes `[?]`.

---
> Export-Stand: payload-skill v2.0 · senpai-ai-chat@ebb935d · content da87d0a04028 · generiert von export_claude_ai.py — NICHT von Hand editieren.
