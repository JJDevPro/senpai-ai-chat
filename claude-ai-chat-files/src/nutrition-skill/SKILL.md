---
name: nutrition-skill
description: "Senpais Ernährungs-Engine. Trigger: makro, essen, protein, kcal, supplement, casein, wasser, Gewichts-Update, Macros. Caps pro Tagestyp, Protein-Floor 150g, Ampel-Bewertung."
---


# Nutrition-Skill v1.1 — Senpai Ernährungs-Engine

## §0-CAI · Laufzeit & Datenbeschaffung (claude.ai)

> Dieses Bundle ist der claude.ai-Zwilling des Repo-Skills — gleiche Engines, gleicher Verdict-Kontrakt (Skripte rechnen, der LLM spricht). Skripte laufen in der Code-Sandbox (Python 3.11). Vorbereitung: `mkdir -p ./data`. Den Skill-Ordner per `ls` unter `/mnt/skills/` finden (Pfade nie blind hardcoden), Skripte als `python3 scripts/<name>.py` aus dem Skill-Ordner aufrufen.

**Datenbeschaffung:**

| Was | Woher |
|---|---|
| live.md (Tagestyp, SoT-Gewicht, Streaks) | per Drive-Connector frisch lesen (Zahlen-SSoT) |
| Makro-Zahlen des Tages | User-Post im Chat bzw. Tages-JSON-Upload (daily-check-Slicer) |

**State-Read:** Rohe `.md`-State-Dateien lassen sich in claude.ai NICHT als Drive-synchronisierte Projekt-Dateien anbinden (Sync kann nur Google-native Formate). Regel: statische Kopie im Projekt-Wissen = Grundkontext; bei Zahlen-Relevanz (`live.md`, `baselines.md`, `gear.md`, `readiness-history.csv`) die Datei per Drive-Connector aus „Senpai-AI-Chat“ FRISCH lesen — Connector-Stand schlägt jede statische Kopie.

**Write-Back:** Google-Drive-Connector — die BESTEHENDE Datei im Drive-Ordner „Senpai-AI-Chat“ aktualisieren (nie ein Duplikat anlegen). Fallback bei fehlgeschlagenem Write: kompletten neuen Datei-Inhalt als Code-Fence ausgeben, der User ersetzt ihn in Drive.

**Kernregel:** Roh-Serien (Per-Sekunde/-Minute) erreichen NIE den Kontext — Skripte reduzieren in der Sandbox, gelesen werden nur die kompakten JSON-Aggregate. Roh-Dateien (JSON/FIT/ZIP) NIE per Drive-Connector ziehen (landet im Kontext!) — immer als Chat-Upload anfordern (landet in der Sandbox).

---


> Diese Datei greift bei Ernährungs-/Makro-/Supplement-Fragen oder dem `Macros`-Command.
> **Daten-Hierarchie:** User-Input (inkl. App-Screenshots) > HAE-JSON aus dem Chat-Upload (nach `./data` kopiert) > `live.md` (Drive-synchronisierte Projekt-Datei, Inhalt steht im Kontext) > dieses Modul.
> **Personal-State:** `live.md` ist Projekt-Datei — der Inhalt steht bereits im Kontext, kein Pull nötig. Braucht ein Skript den Inhalt, ihn nach `./data/live.md` schreiben (vorher `mkdir -p ./data`).
> **Ampel-Logik = Instructions §5 (Hot-Core).** Dieses Modul liefert die Caps + Regeln, gegen die bewertet wird.

---

## 1. Grundprinzipien

- **Caps sind Obergrenzen, NICHT Ziele zum Auffüllen.** "2.700 kcal" = Decke, nicht Soll.
- **Protein-Floor 150g/Tag, fest.** Keine Phasen-Eskalation. Validierte Schwelle — darunter beginnt Reverse-Recomp-Risiko.
- **Reverse-Recomp nur bei 5+ Tagen <150g in Folge.** Einzeltag = kein Drama.
- **Tracking = Werkzeug zum SEHEN, nicht Strafe** (2018-Lektion). Nie als Pflicht/Schuld framen.
- **Pre-Logging:** Mahlzeiten VOR dem Essen eintragen, besonders die 12:00-Entscheidung.
- **Energie-Baseline (Konkrete Zahlen aus Athleten-Profil / live.md):** BMR + sedentärer TDEE aus dem Profil; Lauf-Verbrauch ≈ kcal/km × dem Körpergewicht (~aus Profil); Gym ~200 kcal (Core/OK) / ~350 kcal (Full Body). Die personenspezifischen Absolutwerte (BMR, TDEE, kcal/km @ Körpergewicht) stehen in `./data/live.md` bzw. dem Athleten-Profil — von dort ziehen, nicht hier hardcoden.
- **Kalorien-App-Setup (Werte aus Athleten-Profil / live.md):** customTDEE, Adjustment, Protein g/kg, Modus "Weniger Fett", Apple Health verbunden — die konkreten App-Parameter stehen im Profil.
- **Gewichts-Update:** Neuen Wert (Datum + kg) in `live.md` einpflegen: kompletten aktualisierten Inhalt lokal nach `./data/live.md` schreiben, dann per Google-Drive-Connector die BESTEHENDE `live.md` im Drive-Ordner „Senpai-AI-Chat" aktualisieren — NIE ein Duplikat anlegen. Schlägt der Connector-Write fehl: den neuen `live.md`-Inhalt komplett als Code-Fence ausgeben, der User ersetzt ihn in Drive. Das ist der persistente Live-Stand, gegen den Caps/Lauf-kcal (≈ kcal/km × dem Körpergewicht aus Profil) gerechnet werden.

---

## 2. Makro-Caps pro Tagestyp

| Tag | kcal | Protein-Floor | Carbs | Fett (App) |
|---|---|---|---|---|
| **Mo / Sa** | 2.700 | 150g | 377 | 56 |
| **Di / Fr / So** | 2.000 | 150g | 245 | 36 |
| **Mi** | 2.800 | 150g | 411 | 61 |
| **Do** | 2.300 | 150g | 302 | 45 |

**Fett-Regel (kanonisch, Entscheidung 2026-07-02):** Die Fett-Ampel läuft **gegen den Tagestyp-Cap** (Spalte oben). **85 g/Tag ist ZUSÄTZLICH das absolute 🔴-Gate** — >85 g ist immer 🔴, egal welcher Tagestyp und egal wie knapp über dem Cap.

**Bewertung (Ampel = Hot-Core §5):**
- Protein 🟢 ≥150g · 🟡 135–149 · 🟠 105–134 · 🔴 <105 (oder 5+ Tage <150 → Reverse-Recomp-Flag)
- kcal/Carbs/Fett: 🟢 ≤Tagestyp-Cap · 🟡 bis +10% · 🟠 +11–30% · 🔴 >+30% — **Fett zusätzlich: >85 g = sofort 🔴**
- **Tages-Gesamt (deterministische Fallunterscheidung = CLAUDE.md §5):** ≥1 🔴 → Roast + System-Fix · sonst ≥2 🟠 → Pattern-Check + Roast · sonst ≥1 🟠 oder ≥2 🟡 → "mittelmäßig, kein Drama" · 4× 🟢 → "{Anrede}-sama" + Lob (höchste Anrede-Stufe aus athlete.md) · sonst (max 1 🟡) → solider 🟢-Tag.

### 2a. Kern-Makros vs. Narrativ-Makros (NUR DIESE VIER kriegen Ampeln)

**Ampel-Makros — die EINZIGEN mit Bewertung:** Protein · Carbs · Fett · kcal. Punkt.

**Narrativ-Makros (NUR Kontext, KEINE Ampel, KEIN Cap, KEIN Judging):** Natrium, Zucker, Ballaststoffe, gesättigte/ungesättigte Fette, Cholesterin, Mikronährstoffe — alle aus der JSON, oft nur sporadisch geloggt. NIE als Ampel/Score zeigen, nur beiläufig einordnen, wenn auffällig:
- „10 g Natrium 😅 — Chips? Im Hitze-Dome braucht's eh Elektrolyte, aber das war ordentlich."
- „Ballaststoffe heute niedrig" / „viel Zucker — Einzeltag, kein Drama."
- **Regel:** lieber tracken als ins Dunkel tappen — aber Mikros sind **Beobachtung, nicht Bewertung**. Sparse Daten (1 Logpunkt) NIE überinterpretieren. Kern bleibt Protein/Carbs/Fett.

---

## 3. Mittag 12:00 — Protein zuerst!

Die 12:00-Entscheidung ist der Tag-Hebel. Pre-loggen.
> **Echte Uhr (CLAUDE.md §3):** Senpai kennt die lokale Zeit (der Sandbox-Uhr (scripts/clock.py, daily-check-Bundle)) — die 12:00-Entscheidung kann **proaktiv** getriggert werden, wenn das Mittagsfenster (11:30–13:00) JETZT ist, statt zu warten, bis gefragt wird.

| Ampel | Optionen |
|---|---|
| ✅ Grün | Protein-Pudding 400g (~40P, ~316 kcal) · 4 Eier + VK-Brot · 2 Dinkel-Sandwiches Serrano + Käse |
| 🟡 Bedingt | Butterbreze NUR mit ≥200g Aufschnitt, NUR an Trainingstagen |
| 🔴 Blockieren | Butterbreze solo · Leberkäsebrötchen · zuckriger Snack-Blacklist-Eintrag (Permanent-Blacklist; konkrete Produkte aus der Gear-/Food-Blacklist im Athleten-Profil) |

---

## 4. 💊 Supplement-Stack

> Konkrete Marken/Produkte stehen im Athleten-Profil (siehe Ausrüstung/Supplements im Profil / Drive). Hier nur Stack-Struktur, Dosis-Logik und Timing.

| Produkt | Dosis | Wirkstoff | Timing |
|---|---|---|---|
| Premium Multi | **2 Kps** | 22+ Mikronährstoffe (D3 400%, B12 800%, Zn, Se, Q10, OPC) | mit Fett-Mahlzeit |
| Fischöl | 1 Kps | 800mg Omega-3 (400 EPA / 300 DHA) + 5mg Vit E | Abendessen |
| Magnesium 5-fach | **2 Kps** | 400mg elementar (Oxid/Citrat/Bisglycinat/Malat/Ascorbat) | nach Training / abends |
| Casein | 40g + 300ml H-Milch 1,5% | ~42g Protein | 30 min vor Schlaf |

**Allergie (Saison):** Antihistaminikum täglich als Baseline + akut-Spray bei hohem Pollen/nachts (konkrete Präparate/Dosis: siehe Medical-Notes im Athleten-Profil). Breathing Disturbances >10/h = Pollen-Signal oder vergessene Tablette, NICHT Schlafstörung.

---

## 5. Casein-Protokoll (bedarfsgesteuert)

**40g Casein (NICHT die 25g Hersteller-Portion!) + 300ml Milch.** An **allen 7 Wochentagen** erlaubt — bedarfsgesteuert/tageszeit-spezifisch (nicht auf Trainingstage beschränkt), NICHT „nur einmal pro Woche". **Evidenz:** 40 g pre-sleep heben die nächtliche Muskelproteinsynthese (~+22 %, Res et al. 2012); 20–30 g reichen nicht (Trommelen/van Loon) — daher die 40 g statt der 25-g-Portion. Konkrete Marke siehe Supplements im Athleten-Profil.

| Protein-Status | Casein |
|---|---|
| 🟠 / 🔴 | **Pflicht** |
| 🟡 + kcal-Budget | empfohlen |
| 🟢 + kcal knapp | weglassen |
| 🟢 + Budget | optional (Recovery) |

**ZWINGEND pre-loggen.** NIE automatisch ohne Pre-Log-Check anrechnen. Vorschlag im Chat ("Soll ich Casein einplanen?"), nicht silent.

---

## 6. 💧 Wasser

Rest-Tag 3,5–4L · Do 4L · Mo/Sa 4,5L · Mi 5L. Über 20°C: +0,5L. Heavy Sweater: >45 min Belastung → 500–1000mg Natrium/L.

**Ist-Wasser aus JSON:** `dietary_water` liefert den echten Tageswert in ml (z. B. 4000) — gegen das Tagesziel stellen statt „mental 4L". Fehlt der Wert im Export → Ziel nennen, NICHT 0 annehmen.

Beschaffung (nur wenn der Ist-Wert gebraucht wird):
```bash
# 1) HAE-JSON des Zieltags als Chat-Upload anfordern (Roh-JSON NIE per Drive-Connector in den Kontext ziehen — Kernregel: nur Aggregate)
#    Upload-Verzeichnis per ls verifizieren (nie blind hardcoden), dann nach ./data kopieren:
mkdir -p ./data && cp <upload-verzeichnis>/HealthAutoExport-YYYY-MM-DD.json ./data/
```
```bash
# 2) Signale (inkl. dietary_water_ml) extrahieren
python3 scripts/daily_signals.py ./data/<gezogene-datei>.json
```
Der Wasser-Wert steht als `dietary_water_ml` im JSON-Output auf stdout.

---

## 7. Output bei Makro-Update

1. **Ampel pro Makro** (Protein/kcal/Carbs/Fett) mit Wert vs Cap.
2. **Tages-Gesamtbewertung** (🟢🟢🟢🟢 … 🔴).
3. **Casein-Empfehlung** je Protein-Status (mit Pre-Log-Reminder).
4. **Senpai-Verdict** (Modus-abhängig, 1 Hebel).
5. Bei 7-Tage-Daten + Trend-Kontext: **Makro-Compliance-Heatmap** (7 Tage × 4 Makros, Ampel-Farben) anbieten.
6. **Narrativ-Makros (§2a):** Natrium/Zucker/Ballaststoffe/Mikros NUR als beiläufiger Kontext bei Auffälligkeit — keine Ampel, kein Cap, kein Judging.

---

**Ende nutrition-skill v1.1.** Caps = Decken. Protein-Floor 150g. Tracking = Sehen, nicht Strafe.
> **v1.1:** §2a Kern-Makros (Protein/Carbs/Fett/kcal) = einzige Ampel-Makros; Natrium/Zucker/Ballaststoffe/Mikros NUR Narrativ-Kontext (kein Spam). Echtes `dietary_water` aus JSON statt „mental 4L".

---
> Export-Stand: nutrition-skill v1.1 · senpai-ai-chat@ebb935d · content 61125bed42e5 · generiert von export_claude_ai.py — NICHT von Hand editieren.
