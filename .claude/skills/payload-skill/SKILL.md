---
name: payload-skill
description: "AI Coach Wochen-Payload-Generator für den Athleten. Laden bei dem Payload-Command oder am Sonntag-KW-Abschluss nach der SoT-Messung. Erzeugt ein verdichtetes, copy-paste-fertiges Wochen-Briefing (SoT-Snapshot, Trainings-Absolvierung, PRs, Makro-Compliance, HRV/VO2-Trend, Learnings, Persona-State, Next-KW-Fokus) als reinen Code-Fence-Block ohne Preamble und regeneriert daraus live.md (aus dem privaten Drive-Ordner) als autoritativen State-Seed für den nächsten KW-Chat. Erkennt außerdem einen Payload-Block am Chat-Anfang und integriert ihn priorisiert. NICHT für tägliche Checks (daily-check-skill) oder KW-Rekalibrierung (sync-skill)."
---

# Payload-Skill v1.0 — KW-Abschluss-Export

> Senpai lädt diese Datei NUR bei `Payload`-Command oder Sonntag-Abend nach SoT.
> **Zweck:** Verdichtetes Wochen-Briefing als State-Seed für den nächsten KW-Chat. Regeneriert `live.md` (im privaten Drive-Ordner `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde`) als volatile Senpai-State.

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
Fehlende Werte = `[?]` markieren, nicht erfinden.

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
- Alle Felder ausfüllen. Fehlende Daten → `[?]`, User ergänzt im Folge-Chat manuell.
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

**Ende payload-skill v1.0.** Code-Fence only. Felder vollständig oder `[?]`. V3, nicht V2.
