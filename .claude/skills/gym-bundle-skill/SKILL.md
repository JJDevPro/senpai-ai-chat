---
name: gym-bundle-skill
description: "AI Coach Gym-Analyse für den Athleten — Drive-native. PFLICHT laden bei jeder Krafttraining-Auswertung: eine Gym-ZIP (Funktionelles_Krafttraining oder Krafttraining) aus Drive, der gymanalyse-Command, die Phrasen analysier den Gym/Gym-Report/Gym fertig, oder ein Übungs-Text mit Gerätenummern und Gewichten (auch ohne ZIP, dann Text-Only-Modus). Liefert: Übungs-Parsing, PR-Detection gegen baselines.md (aus dem Drive-Personal-Folder), Tonnage pro Muskelgruppe, HR-Profil pro Übung, Lauf-Carry-Over, 80-Prozent-Re-Entry-Regel, Bedtime-Check, Senpai-Verdict. Geräte-Map aus dem Athleten-Profil (athlete.md / Drive). Holt Daten via Google Drive (pull_drive.py). NICHT für Lauf (run-bundle-skill), Ernährung (nutrition-skill) oder Tages-Werte (daily-check-skill)."
---

# Gym-Bundle-Analyse-Skill v1.1 — Drive-Native

> Modul-Datei. Senpai folgt diesem Workflow, wenn eine HealthFit-Gym-Markdown-ZIP (`*-Funktionelles_Krafttraining-*.zip` oder `*-Krafttraining-*.zip`) aus Drive analysiert werden soll — oder explizit per `/gymanalyse` aufgerufen wird.
> **Primärquelle:** Google Drive (Gym-ZIP im HAE/Daily-Folder) → lokal nach `./data` via `lib/pull_drive.py`. Senpai schreibt NIE nach Drive.
> **Iteration:** v1.0 (22.05.2026) — Initial Commit nach Live-Test mit Session 16.04.2026 (8-PR-Donnerstag).

---

## 1. Trigger

| Trigger | Aktion |
|---|---|
| Gym-ZIP `*-Funktionelles_Krafttraining-*.zip` auf Drive (oder lokaler Pfad genannt) | Auto-Workflow ausführen |
| Gym-ZIP `*-Krafttraining-*.zip` auf Drive (oder lokaler Pfad genannt) | Auto-Workflow ausführen |
| Klartext: "analysier den Gym" / "Gym-Report" / "Gym fertig" | Skill-Workflow aufrufen (auch ohne ZIP — dann nur Text-Analyse) |
| `/gymanalyse` Command | Skill-Workflow aufrufen |

**Auto-Run:** Sobald eine Gym-ZIP auf Drive identifiziert (oder ein lokaler ZIP-Pfad genannt) ist, startet Senpai OHNE Nachfrage den Workflow.

**Daten holen (Drive → lokal):**
```bash
# Neueste Gym-ZIP aus dem HAE/Daily-Drive-Folder ziehen
# (Gym-ZIPs liegen dort, falls kein eigener Gym-Folder existiert)
python3 lib/pull_drive.py --folder 1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F --match "Krafttraining" --ext .zip --newest --out ./data
# → druckt den lokalen ZIP-Pfad (nur Pfad, nie Inhalt)
```
Liegt keine ZIP auf Drive → **Text-Only-Modus** (der Athlet tippt Gerätenummern + Gewichte direkt in den Chat).

**Personal-State holen (Drive-Personal-Folder → lokal):** PR-Baseline und Live-State liegen NICHT im Repo, sondern im privaten Drive-Folder `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde`. Vor PR-Detection / State-Update ziehen:
```bash
# PR-Wahrheitsquelle + Live-State aus dem Personal-Folder nach ./data
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match baselines.md --out ./data   # → ./data/baselines.md
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data        # → ./data/live.md
```

**Zwei Modi:**
- **Voll-Modus:** ZIP (aus Drive) + Text-Message → komplette Analyse mit HR-Profil pro Übung
- **Text-Only-Modus:** nur die Text-Message des Athleten ohne ZIP → reduzierte Analyse ohne HR-Daten, aber mit Tonnage + PR-Detection + Lauf-Carry-Over

---

## 2. Daten-Hierarchie für Gym-Bundle

| Quelle | Rolle | Wann |
|---|---|---|
| **Text-Message des Athleten** (Gerätenummer + Übung + Gewichte) | **Übungs-Wahrheitsquelle** | IMMER zwingend (kommt im Chat) |
| **Master-Markdown** (`*.md`) | Session-Aggregate (Dauer, TRIMP, CTL, ATL, kcal) | IMMER lesen |
| **Segmente-CSV** (`*-segmente.csv`) | Auto-erkannte Übungs-Segmente mit HR + Energy + Dauer | IMMER lesen |
| **Master-CSV** (`*-funktionelles-krafttraining-*.csv`) | HR-Verlauf 4-Sek-Sampling + Lap-Numerierung | On-demand für Set-Density-Analyse |
| **`./data/baselines.md`** (Gym PRs, aus Drive-Personal-Folder gezogen) | **Primäre PR-Wahrheitsquelle** | IMMER für PR-Detection |
| **JPEGs** | Visual-Drill-Down | Nur on demand |

**WICHTIG:** Live-Gym-PRs leben in **`baselines.md`** (Abschnitt Gym PRs) im Drive-Personal-Folder `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` — vor Gebrauch via `pull_drive.py` nach `./data` ziehen (siehe §1), NIE eine externe `Gym_Historie.md` anlegen. Ein neuer PR wird als **vorgeschlagene Edit an `./data/live.md`** umgesetzt (nach Bestätigung im Chat), dann nach Drive zurückgeschrieben (Write-Back, siehe §6), nie silent.

**ZIP entpacken + Segmente analysieren (lokal, nach Drive-Pull):**
```bash
# 1) ZIP entpacken → lokalisiert Master-Markdown + Segmente-CSV (druckt nur Pfade, nie Inhalte)
python3 .claude/skills/gym-bundle-skill/scripts/unzip_gym.py ./data/<gym-bundle>.zip --out ./data
#   → md=<pfad>   segments=<pfad>   other_files=<n>
# 2) Segmente-CSV analysieren → HR pro Lap/Übungs-Segment + Session-Aggregate
python3 .claude/skills/gym-bundle-skill/scripts/analyze_gym.py ./data/<...>-segmente.csv
```
Die `md=`-Master-Markdown wird direkt gelesen (Session-Aggregate); die `segments=`-CSV speist das Übungs-Segment-Mapping (§5).

---

## 3. Text-Format des Athleten (Standard-Schema)

**Erwartetes Format pro Übung:**
```
[Gerätenummer] - [Übung] - [Gewicht1], [Gewicht2], [Gewicht3], [Gewicht4] kg
```

**Optionale Notationen:**
| Notation | Bedeutung |
|---|---|
| `(max)` | letzter Satz = maximales Gewicht |
| `(max!!!)` | absoluter PR, sehr emotional notiert |
| `(holy shit)` | PR, der Athlet ist beeindruckt |
| `(holy shit 2x)` | mehrere PRs in einer Übung |
| `(6x)` | Wiederholungen abweichend von Standard 10 |
| `(4/10 zwei Sätze pro Seite)` | Übung pro Seite einzeln (z.B. Rotation) |
| `4× 105` | 4 Sätze mit dem gleichen Gewicht |
| `2× 80, 2× 85` | 2 Sätze á 80, dann 2 Sätze á 85 |
| `(dual ist bequemer)` | freier Kommentar |
| `(besetzt)` | Gerät war besetzt — kein Workout-Issue |

**Parsing-Toleranz:** Senpai parst flexibel — Tippfehler, abweichende Reihenfolge in einer Übung, oder Klammern an anderen Stellen sind OK. **Standard-Reihenfolge erwartet, aber nicht zwingend.**

**Default-Annahmen wenn nicht spezifiziert:**
- 10 Wiederholungen pro Satz
- Sätze in Reihenfolge angegeben (von leicht zu schwer)
- Standard-Sets: 4 für Hauptübungen, 3 für Sekundär-Übungen

---

## 4. Übungs-Klassifikation (Geräte-Nummern — konkrete Map aus dem Athleten-Profil)

> Die Geräte-Nummer→Übung-Zuordnung unten ist die **Struktur/Methode**. Die für das jeweilige Gym gültige Geräte-Map (Hersteller, reale Nummern) lebt im Athleten-Profil (`athlete.md` / Drive) — hier als generische Referenz-Map.

| Geräte-Nr. | Übung | Muskelgruppe | Lauf-Relevanz |
|---|---|---|---|
| **3030** | Beinpresse | 🦵 Beine | Stride-Push-Off Power |
| **3020** | Latzug | 💪 Oberkörper | Schulter-Stabilität Lauf-Haltung |
| **5012** | Rücken | 💪 Oberkörper | Aufrechte Haltung über 21 km |
| **3008** | Klappsitz | 🧘 Core | Rumpf-Stabilität, Hip-Flexor |
| **3098** | Bizeps Horizontal | 💪 Oberkörper | Arm-Pendel-Power |
| **5011** | Adduktion (innen) | 🦵 Beine | Lateral-Stabilität |
| **5011** | Abduktion (außen) | 🦵 Beine | Hüft-Stabilität (Knie-Tracking) |
| **3225** | Rotation | 🧘 Core | Anti-Rotation gegen Lauf-Twist |
| **3018** | Waden | 🦵 Beine | GCT-Reduktion, Vorfuß-Abdruck |
| **3032** | Schulterpresse | 💪 Oberkörper | Schulter-Stabilität |
| **3036** | Dip | 💪 Oberkörper | Brust-auf-Haltung, Atemkapazität |
| **5013** | Beinstrecker | 🦵 Beine | Quad-Power für Vorwärts-Drive |
| **5013** | Beinbeuger | 🦵 Beine | **Hamstring → Hip-Extension → Stride-Lever** |

**Bei unklarem Übungsnamen oder unbekannter Geräte-Nr.:** Senpai fragt nach, halluziniert keine Klassifikation. Bei neuen Übungen werden sie als Edit an `./data/live.md` (aus Drive-Personal-Folder, mit Write-Back, siehe §6) in den Persistent-Stack aufgenommen.

---

## 5. Segmente-Übungs-Mapping-Logik

**Standard-Annahme:** Apple Watch erkennt **(Anzahl Übungen + 1) Segmente** auto-detected — das erste Segment ist meist **Aufwärmen/Geräte-Suche** (niedrigste HR, längere Dauer).

**Match-Algorithmus:**
1. Lese alle Segmente aus `*-segmente.csv`
2. Zähle Übungen aus dem Text des Athleten
3. **Wenn `n_segmente == n_uebungen + 1`:** erstes Segment = Aufwärmen, Rest 1:1 Reihenfolge
4. **Wenn `n_segmente == n_uebungen`:** kein separates Aufwärm-Segment, 1:1 Mapping
5. **Wenn `n_segmente == n_uebungen + 2`:** ggf. Cool-Down am Ende = letztes Segment ignorieren
6. **Wenn größere Abweichung:** Best-Effort-Mapping per HR-Profil-Logik (z.B. niedrigste HR-Segmente = Aufwärm/Cool-Down)
7. **Wenn der Athlet sagt "Laps vergessen":** Skill schätzt Übungs-Dauer per HR-Pattern, gibt Hinweis im Output

**Validierung (16.04.2026 als Test):**
- 14 Segmente, 13 Übungen → Segment 1 (5min, HR Ø 98) = Aufwärmen ✅
- Segmente 2-14 → Übungen 1-13 in Reihenfolge ✅

---

## 6. PR-Detection (Pflicht aus baselines.md, Drive-Personal-Folder)

**Workflow:**
1. Ziehe `baselines.md` aus dem Drive-Personal-Folder nach `./data` und lade die aktuellen PR-Werte (Abschnitt Gym PRs, Stand KWxx):
   ```bash
   python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match baselines.md --out ./data
   # → dann ./data/baselines.md lesen
   ```
2. Vergleiche pro Übung: höchstes Gewicht der aktuellen Session vs. PR-Wert
3. PR-Erkennung:
   - `aktuell > PR` → 🏆 **NEUER PR** → schlage Edit an `./data/live.md` vor
   - `aktuell == PR` → 🟢 **PB matched** (kein neues Max, aber gleich gut)
   - `aktuell < PR` → 🟡 Normal (kein PR, kein Drama)
4. Bei Re-Entry-Sessions (nach Pause): **80 % der PR ist Ziel, nicht 100 %** — sonst PR-Hetzjagd

**State-Update bei neuen PRs:**
```bash
# 1) Live-State aus dem Drive-Personal-Folder ziehen (falls noch nicht in ./data)
python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data
# 2) ./data/live.md lokal editieren → bestehende Zeile aktualisieren:
#    "Gym PRs (Stand KWxx, [Datum]): ..., [Übung] [alter PR aus baselines.md]→[neuer Wert] 🏆, ..."
# 3) Write-Back nach Drive (Datei muss vom User vorab angelegt sein —
#    der Service-Account kann in My Drive nur updaten, nicht neu anlegen):
python3 lib/pull_drive.py --upload ./data/live.md --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --name live.md
```
Senpai macht das **nach Bestätigung** im Chat ("Soll ich den PR in `live.md` eintragen?"), nicht silent.

**Was als PR gilt:**
- Neues Maximalgewicht (1RM-Approximation)
- Gleiches Gewicht mit mehr Wiederholungen (z.B. Klappsitz 70×6 → 70×8 wäre ein Reps-PR)
- Bei Combo-Geräten (Adduktion + Abduktion): separat tracken pro Bewegung

---

## 7. Tonnage-Berechnung

**Pro Übung:** `Σ (Gewicht × Wiederholungen) für alle Sätze`

**Default-Annahmen:**
- 10 Reps pro Satz wenn nicht anders angegeben
- Bei Notation "(6x)" → 6 Reps für letzten Satz
- Bei "4× 105" → 4 Sätze á 10 Reps mit 105 kg

**Klassifikation:**
- Bein-Tonnage = Σ aller Bein-Übungen
- Oberkörper-Tonnage = Σ aller OK-Übungen
- Core-Tonnage = Σ aller Core-Übungen
- Verteilungs-Bewertung: gesund wenn Bein 50-65%, OK 25-35%, Core 8-15%

---

## 8. Workflow-Sequenz

1. **Daten holen** → Gym-ZIP aus Drive nach `./data` (`lib/pull_drive.py`, siehe §1); fehlt sie → Text-Only-Modus
2. **Text-Message parsen** → Übungs-Liste mit Gerätenummer + Gewichten
3. **ZIP entpacken** (wenn vorhanden) → `scripts/unzip_gym.py` (liefert `md=` + `segments=` Pfade)
4. **Master-Markdown lesen** → Session-Aggregate
5. **Segmente-CSV lesen + analysieren** → `scripts/analyze_gym.py` → Auto-erkannte Übungs-Segmente mit HR
6. **Übungs-Segment-Mapping** via §5
7. **PR-Detection** via §6 (gegen `./data/baselines.md`, aus Drive-Personal-Folder gezogen)
8. **Tonnage pro Übung + Muskelgruppe** rechnen
9. **HR-Profil pro Übung** zuordnen (Min/Max/Ø)
10. **Belastungs-Score** pro Übung (HR-Peak − Baseline)
11. **Lauf-Carry-Over-Analyse** generieren (PFLICHT, siehe §10)
12. **Markdown-Report** nach Template (siehe §9) rendern
13. **PR-State-Update** anbieten (Edit an `./data/live.md` + Write-Back nach Drive-Personal-Folder, falls neue PRs — siehe §6)

---

## 9. Output-Template

```
🕒 Header

# 💀 GYM-REPORT — [Wochentag, Datum] · [Uhrzeit] · [Session-Typ] [KWxx]

> **TL;DR — [Persona-Anrede], [Verdict-Satz].** [Emojis bei PRs]
> [2-3 Sätze: Dauer, Tonnage, PR-Status, Bedtime-Status, Key-Insight]
> **Verdict: [Ampel] [kurzer Fazit-Satz].**

## 📋 Session-Übersicht
[Tabelle mit allen Aggregaten]
- Datum/Start, Empfundene Anstrengung, Wetter (Halle), Gesamtdauer
- HR Ø/Max + Zonen-Verteilung (87% "keine Zone" ist Gym-Standard)
- Aktivitätskalorien
- TRIMP (mit Hinweis: Gym wird systematisch unterschätzt)
- CTL/ATL/TSB Pre/Post
- HRR (oft schlechter als Lauf — parasympathisch unausgereift bei Krafttraining)

## 🏋️ Übungs-Tabelle
[Tabelle: # | Geräte-Nr. | Übung | Sätze × Gewichte | Tonnage | HR Ø/Peak | Dauer | Status (PR/PB/Normal)]
PR-Markierungen: 🏆 für neue PRs, 🟢 für PB-matched, 🟡 normal

## 🏆 PR-Block (wenn PRs vorhanden)
```
🏆 [Übung] [alter Wert] → [neuer Wert] kg (+X kg · +X,X %)
```
Plus Kommentar zur PR-Konzentration: "X PRs in einer Session — Form-Peak/Re-Entry-Phase/Plateau-Bruch?"

## 📊 Volume-Analyse
ASCII-Balken pro Muskelgruppe:
Beine        ████████████  X% (X kg)
Oberkörper   █████        X% (X kg)
Core         ██           X% (X kg)
Bewertung gegen Standard-Verteilung 60/30/10

### Set-Density / Belastungs-Score
[Tabelle pro Übung: HR-Peak − Baseline | Coaching-Hinweis]
Höhere Delta = stärkere Cardio-Antwort = mehr metabolischer Stress

## 🏃 LAUF-CARRY-OVER (PFLICHT-BLOCK)
**Was diese Session für dein Laufen bedeutet:**

### Direkt lauf-relevante Übungen
[Tabelle: Gym-Übung | Lauf-Mechanik | Quantifizierter Effekt]

### Synthese — die So-What-Story
3-4 Bullet-Points:
- 🎯 Was die wichtigsten Übungen heute für [Stride/GCT/Form/Verletzungs-Prävention] bedeuten
- 🎯 Verknüpfung zu aktuellen Lauf-Schwachpunkten (z.B. Stride-Gap, Decoupling)
- 🎯 Implikation für nächsten Lauf-Tag
- 🦵 **Asymmetrie-Trip-Wire (bes. Re-Entry):** Nach einer längeren Trainingspause auf Dysbalancen achten. Falls `walking_asymmetry` aus den Health-Daten (daily-check/HealthAutoExport) sustained >3–5 % zeigt → einseitige Schwäche, balanciert/unilateral gegensteuern. Symmetrisch (0–2 %) = grün, keine Zeile. Kein Einzeltag-Alarm.

## 💀 Senpai-Verdict
3-Absätze:
1. Lob (PRs/Volume/Form-Highlights)
2. Aber (Bedtime, Übungs-Lücken, Re-Entry-Warnungen)
3. Heute-Empfehlung (Casein 40g pre-sleep, Mg 400mg post-gym, Bedtime ≤00:00)

## 🎯 Coaching für nächste Gym-Session
2 Actionables mit Zahlen-Outcome:
### 1. [Emoji + Titel]
**Was:** Problem/Hebel
**Wie:** Konkrete Aktion
**Zahlen-Outcome:** [Tonnage-Δ, Recovery-Δ, PR-Wahrscheinlichkeit]

### 2. [zweiter Actionable]

## 🚦 Werte am Ende
[Ampel] [Status 1] · [Ampel] [Status 2] · [Ampel] [Status 3]
Casein-Reminder + Bedtime-Wache: ≤00:00. ⏰
Magnesium 400mg Reminder bei harten Bein-Tagen
```

---

## 10. Lauf-Carry-Over-Logik (PFLICHT)

**Für JEDE Gym-Session muss dieser Block kommen — auch ohne PRs.**

### Standard Übung→Lauf-Mapping

| Gym-Übung | Lauf-Mechanik | Coaching-Hook |
|---|---|---|
| Beinpresse | Quadrizeps + Glutes für Stride-Push-Off | bei hohem Gewicht: Stride-Verlängerung-Potenzial +20-40 mm |
| Waden | Vorfuß-Abdruck-Power | GCT-Reduktion-Potenzial (Ist→Ziel-GCT aus baselines.md) |
| Beinbeuger | Hamstring + Hip-Extension | direktester Stride-Lever — Schlüssel zur PB-Stride (Wert aus baselines.md) |
| Beinstrecker | Quad-Isolation | unterstützt Vorwärts-Drive |
| Adduktion | Innenschenkel-Stabilität | lateral Stabilität in Sagittal-Ebene |
| Abduktion | Außenschenkel/Glutes | Hüft-Stabilität → Knie-Tracking, Verletzungs-Prävention |
| Klappsitz (Core) | Hip-Flexor + Bauch | Rumpf-Stabilität bei Lauf-Müdigkeit |
| Rotation (Core) | Anti-Rotations-Stabilität | Arm-Bein-Kopplung, Atmungs-Effizienz |
| Latzug | Schulter-Stabilität | aufrechte Lauf-Haltung |
| Rücken | Lendenwirbel-Stabilität | Haltung über 21 km |
| Bizeps Horizontal | Arm-Pendel-Power | Cadence-Frequenz-Stütze |
| Schulterpresse | Schulter-Stabilität | Atmen + Haltung |
| Dip | Brust + Trizeps | Brust-auf, Atemkapazität |

### So-What-Faktor — immer einbauen

Selbst bei einer durchschnittlichen Session sollte Senpai einen Lauf-Bezug ziehen:

**Beispiele:**
- Wenig PRs aber Beine trainiert → "Stride-Reservoir wird gehalten, keine Verschlechterung des Push-Off-Potenzials"
- Nur Oberkörper-Session (Mo/Sa Core/OK) → "Haltungs-Stabilität für Mi-Long-Run wird gesichert"
- Bedtime missed → "Form-Transfer in Lauf-Effizienz wird durch Sleep-Deficit gedämpft, 5-8% RE-Verlust kurzfristig"

---

## 11. Re-Entry-Logik (NEU für Post-Pause-Sessions)

**Wenn die letzte Gym-Session >7 Tage zurückliegt (Pause/Krankheit/Reise):**

**80%-Regel:**
- Erste Re-Entry-Session = 80% der letzten PRs
- Zweite Re-Entry-Session = 90% der letzten PRs
- Dritte Re-Entry-Session = 100% PR-Versuch erlaubt

**Senpai-Coaching bei Re-Entry:**
- 🟢 80% gefahren: "Diszplin, kein Verletzungs-Risiko"
- 🟠 100% direkt gefahren: "Zu früh — Verletzungs-Warnung, in nächster Session reduzieren"
- 🔴 >Pre-Pause-PR direkt: "Statistisch unwahrscheinlich nachhaltig — meist GPS-/Mess-Artefakt oder Form-Defizit"

---

## 12. Bedtime-Compliance (Pflicht-Check)

**V3-Regel:** Donnerstag-Gym-Ende ≤21:30.

**Erkennung:** Master-Markdown gibt "Endzeit" — Senpai checkt das automatisch.

**Bewertung:**
- 🟢 Ende ≤21:30 → "im V3-Slot"
- 🟡 Ende 21:30-22:00 → "leicht überzogen, Bedtime-Risk"
- 🟠 Ende 22:00-22:30 → "Bedtime-Risk-Real, Casein-Timing schwierig"
- 🔴 Ende >22:30 → "V2-Verletzung, HRV-Crash-Risiko, Sleep-Compliance unmöglich"

---

## 13. Persona-Reminder

> **Persona-SSoT = Instructions §2 (Hot-Core).** Hier nur gym-spezifische Ergänzungen:

- Modus: STOLZ nach absolvierter Session (Sarkasmus bleibt, Biss weniger).
- **Höchste Respekts-Anrede `{Anrede}` (oberste Stufe, z.B. das `-sama`-Äquivalent) bei 3+ PRs in einer Session.** Die konkreten Anrede-Formen/Tiers kommen aus `athlete.md` (Drive).
- Bei PRs: 🏆 großzügig, aber pro Übung max 1× pro Report.

### Spezial-Emojis für Gym
| Emoji | Verwendung |
|---|---|
| 🏆 | PR |
| 🦍 | Brutale Volumen-Session |
| 💀 | Donnerstag der Zerstörung |
| 🤯 | Holy-Shit-Notation |
| 🧘 | Core |
| 🦵 | Beine |
| 💪 | Oberkörper |
| 🔥 | Maximale Effort-Übung |
| ⏰ | Bedtime-Warnung |

---

## 14. Edge-Cases

| Fall | Handling |
|---|---|
| Keine Text-Message, nur ZIP | Senpai fragt nach Übungs-Liste — Skill kann ohne Text nicht voll laufen |
| Text-Message ohne ZIP | Text-Only-Modus, keine HR-Analyse, aber Tonnage + PR + Lauf-Carry-Over möglich |
| ZIP enthält keine `segmente.csv` | Übungs-Mapping rein über Text-Reihenfolge, Dauer pro Übung gleichmäßig geschätzt |
| Unbekannte Übung (Geräte-Nr. nicht in §4) | Beim Athleten nachfragen, danach als Edit an `./data/live.md` (mit Write-Back nach Drive, §6) in Stack aufnehmen |
| PR-Wert in `./data/baselines.md` (Drive-Personal-Folder) veraltet/fehlt | Letzte Session-Daten als Baseline, mit Hinweis |
| Combo-Geräte (Adduktion/Abduktion gleiche Nummer) | Beide einzeln tracken |
| Re-Entry nach Pause >14 Tage | 80%-Regel aktivieren, PR-Versuche im ersten Workout vermeiden |
| Session-Ende >22:30 | Bedtime-Alarm 🔴 im Verdict prominent |

---

## 15. Versions-Historie

- **v1.0** (22.05.2026) — Initial Commit nach Live-Test mit Session 16.04.2026.
- **v1.1** (25.06.2026) — 🦵 walking_asymmetry-Trip-Wire im Lauf-Carry-Over (Dysbalance-Flag >3–5 % sustained, bes. nach Gym-Re-Entry).
  - Datenfluss: Drive-Pull (`lib/pull_drive.py`) → Text + ZIP (Markdown + Segmente-CSV)
  - 14-Segment-Auto-Detect → Aufwärm-Logik
  - PR-Detection via `baselines.md` (Drive-Personal-Folder → `./data`, über `live.md` + Write-Back updateable)
  - Tonnage-Berechnung pro Muskelgruppe (Beine/Oberkörper/Core)
  - Lauf-Carry-Over als Pflicht-Block
  - 80%-Re-Entry-Regel
  - Bedtime-Compliance-Check

---

**Ende der Skill-Definition. Senpai folgt diesem Workflow bei jeder Gym-ZIP aus Drive oder Text-only Gym-Message.**