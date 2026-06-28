---
name: nutrition-skill
description: "AI Coach Ernährungs-Engine für den Athleten. PFLICHT laden, sobald es um Essen, Makros, Kalorien, Protein, Supplements, Casein, Wasser oder Body-Recomp-Ernährung geht — auch ohne explizites Stichwort. Trigger: Makro-Update, Tages-Bilanz, Mittag-12:00-Entscheidung, Pre-Logging, Gewichts-Update, Supplement-/Casein-Frage, Wasser, Cap-Frage, der Macros-Command. Liefert: Cap-Tabellen pro Tagestyp, Protein-Floor 150g, Mahlzeiten-Whitelist/Blacklist, Supplement-Stack, Casein-Protokoll mit Pre-Log-Pflicht, Wasser-Plan, Ampel-Bewertung. NICHT für Lauf-/Gym-/Schlaf-Analyse."
---

# Nutrition-Skill v1.1 — Senpai Ernährungs-Engine

> Diese Datei greift bei Ernährungs-/Makro-/Supplement-Fragen oder dem `Macros`-Command.
> **Daten-Hierarchie:** User-Input (inkl. App-Screenshots) > gepullte HAE-JSON (`./data`) > `./data/live.md` (gepullt aus der Drive-Personal-Folder, s.u.) > dieses Modul.
> **Personal-State pullen:** `python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data` → dann `./data/live.md` lesen.
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
- **Gewichts-Update:** Live-State aus der Drive-Personal-Folder ziehen (`python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data`), neuen Wert (Datum + kg) in `./data/live.md` schreiben und zurückschreiben (`python3 lib/pull_drive.py --upload ./data/live.md --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --name live.md` — die Datei muss vom User vorab angelegt sein, da der Service-Account in My Drive nur updaten, nicht anlegen kann) — das ist der persistente Live-Stand, gegen den Caps/Lauf-kcal (≈ kcal/km × dem Körpergewicht aus Profil) gerechnet werden.

---

## 2. Makro-Caps pro Tagestyp

| Tag | kcal | Protein-Floor | Carbs | Fett (App) |
|---|---|---|---|---|
| **Mo / Sa** | 2.700 | 150g | 377 | 56 |
| **Di / Fr / So** | 2.000 | 150g | 245 | 36 |
| **Mi** | 2.800 | 150g | 411 | 61 |
| **Do** | 2.300 | 150g | 302 | 45 |

**Fett Hard Cap: 85g/Tag** (gleichwertig zum kcal-Cap, gilt tagesübergreifend).

**Bewertung (Ampel = Hot-Core §5):**
- Protein 🟢 ≥150g · 🟡 135–149 · 🟠 105–134 · 🔴 <105 (oder 5+ Tage <150 → Reverse-Recomp-Flag)
- kcal/Carbs/Fett: 🟢 ≤Cap · 🟡 bis +10% · 🟠 +11–30% · 🔴 >+30%
- **Tages-Gesamt:** 🟢🟢🟢🟢 → "{Anrede}-sama" + Lob (höchste Anrede-Stufe; konkrete Anrede-Formen aus athlete.md) · 🟡🟡 → "mittelmäßig, kein Drama" · 🟠🟠 → Pattern-Check + Roast · 🔴 (≥1) → Roast + System-Fix.

### 2a. Kern-Makros vs. Narrativ-Makros (NUR DIESE VIER kriegen Ampeln)

**Ampel-Makros — die EINZIGEN mit Bewertung:** Protein · Carbs · Fett · kcal. Punkt.

**Narrativ-Makros (NUR Kontext, KEINE Ampel, KEIN Cap, KEIN Judging):** Natrium, Zucker, Ballaststoffe, gesättigte/ungesättigte Fette, Cholesterin, Mikronährstoffe — alle aus der JSON, oft nur sporadisch geloggt. NIE als Ampel/Score zeigen, nur beiläufig einordnen, wenn auffällig:
- „10 g Natrium 😅 — Chips? Im Hitze-Dome braucht's eh Elektrolyte, aber das war ordentlich."
- „Ballaststoffe heute niedrig" / „viel Zucker — Einzeltag, kein Drama."
- **Regel:** lieber tracken als ins Dunkel tappen — aber Mikros sind **Beobachtung, nicht Bewertung**. Sparse Daten (1 Logpunkt) NIE überinterpretieren. Kern bleibt Protein/Carbs/Fett.

---

## 3. Mittag 12:00 — Protein zuerst!

Die 12:00-Entscheidung ist der Tag-Hebel. Pre-loggen.

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

**40g Casein (NICHT die 25g Hersteller-Portion!) + 300ml Milch.** Alle ~7 Tage erlaubt. Konkrete Marke siehe Supplements im Athleten-Profil.

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
# 1) HAE-JSON des Zieltags aus Drive nach ./data ziehen
python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "HealthAutoExport-YYYY-MM-DD" --out ./data
# 2) Signale (inkl. dietary_water_ml) extrahieren
python3 .claude/skills/daily-check-skill/scripts/daily_signals.py ./data/<gezogene-datei>.json
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
