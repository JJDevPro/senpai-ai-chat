---
name: weather-runprep-skill
description: "AI Coach Wetter- und Pre-Lauf-Engine für den Athleten (Heimatstadt aus Athleten-Profil). PFLICHT laden an jedem Trainingstag (Mo/Mi/Sa/Do) und sobald Wetter, Lauf-Vorbereitung, Pace-Planung, Schuhwahl oder Gym-Hitze im Spiel sind — auch ohne explizites Stichwort. Trigger: Wochentag Mo/Mi/Sa/Do, Keywords lauf/laufen/wetter/regen/hitze/temp/kalt/warm/pace/schuhe/rennen/race/draussen, Pre-Lauf-Fenster vor festen Slots, Daily-Check an Trainingstag, Race-Strategie-Frage, Flex-Regel-Prüfung am Donnerstag. Holt Wetterochs (RSS + Delphi-JSON), baut die Lauf-Impact-Matrix, rechnet Pace-Korrektur und Hitze-Tax, gibt GO/ADJUST/SHIFT-Risiko. Donnerstag zusätzlich: Gym-Hitze (Gym ohne Klimaanlage, siehe Ausrüstung/Profil) plus Flex-Regel-Input (Do unter 22 Grad). Wetter ist Entscheidungs-Input, nicht Nachgang. Slot-Uhrzeit bestimmt die Starttemp (Parkrun 09:00 = Morgenwert, nie Tagesmax). NICHT für Lauf-/Gym-Performance-Analyse (run-bundle-skill/gym-bundle-skill)."
---

# Weather-Runprep-Skill v1.2 — Senpai Wetter- & Pre-Lauf-Engine

> Senpai lädt diese Datei bei Trainingstag/Lauf-/Wetter-Triggern.
> **Trainingstage = Mo / Mi / Sa / Do.** Mo/Mi/Sa = Lauf-Slots. **Do = Gym (KEINE Klimaanlage, siehe Ausrüstung im Profil) + Flex-Regel-Tag** → auch hier wetterrelevant (§4).
> **🎯 Kern-Prinzip: Wetter ist ENTSCHEIDUNGS-INPUT, kein Nachgang.** An einem Trainingstag wird die Vorhersage **VOR** der Rest-vs-Lauf-/Gym-Empfehlung gezogen — nicht erst, wenn der User „doch Lauf" sagt. Auch wenn Rest empfohlen wird: Wetter zuerst, dann Empfehlung (38°C stützt Rest; überraschend kühl kippt die Rechnung / triggert die Flex-Regel).
> **Wochentag + Uhrzeit = echte VM-Uhr** (`lib/clock.py`, CLAUDE.md §3). Slot-Zeiten sind fest (Sa 09:00, Mo/Mi 20:00, Do-Gym ≤21:30); der Clock sagt, ob ein Slot JETZT ansteht → Pre-Lauf-Fenster feuert verlässlich.
> **Wetter-Source-Priorität:** User-Angabe (Apple-Weather-Screenshot/Temp) > Wetterochs > `[kein Wetter]`.

---

## 1. Trainingstage & Slots

**Lauf-Slots:**
- **Mo 20:00** (fix — Partnerin parallel Zumba, danach Gym zusammen)
- **Mi flexibel** (17:00 oder 20:00 je nach Hitze)
- **Sa 09:00** (Parkrun mit Parkrun-Partner — nie verschieben) → Temp = **Morgenwert** (Tagesmin+Rampe), NIE Tagesmax (§2a)

**Donnerstag = Gym-Tag (kein Lauf-Slot), aber wetterrelevant:**
- **Das Gym hat KEINE Klimaanlage** → Outdoor-Temp bestimmt die Hallen-Hitze.
- Donnerstag ist der **Flex-Regel-Tag** (Do-Lauf statt Gym möglich) → Do-Wetter ist Kriterium 2.
→ Wetter daher auch an Do ziehen. Handling in §4.

---

## 2. Wetterochs-Fetch (sole authorized source)

Trigger erfüllt → BEIDE Endpoints mit dem **WebFetch-Tool** ziehen:
- **RSS-Mail (Prosa, heutiger Tag + 6 Tage):** `https://www.wetterochs.de/wetter/current/WettermailRssInHtml.html`
- **Delphi-JSON (strukturiert, ab morgen, 9 Tage):** `https://www.wetterochs.de/wetter/delphi/gen/WetterRegnitz.json`

> **Netz-Hinweis:** `wetterochs.de` muss in der Netzwerk-Allowlist der Umgebung stehen, sonst schlägt WebFetch fehl → Fallback greift.

**Fallback:** Beide fail → `[kein Wetter]` im Header, nach Apple-Weather-Screenshot fragen, wenn trainingsrelevant.

### 2a. ⏰ Slot-Uhrzeit → Starttemp (HART — Tagesmax ist fast NIE die Starttemp)
Wetterochs liefert i.d.R. **Tagesmin + Tagesmax**. Die für den Lauf relevante Temp hängt an der **Slot-Uhrzeit**, NICHT am Tagesmax (der fällt nachmittags ~15–17 Uhr). Immer beide Werte ziehen und so ableiten:

| Slot | Sommer-Starttemp ≈ | Quelle/Regel |
|---|---|---|
| **Sa-Parkrun 09:00** | **Tagesmin + 1–4 °C** (Morgen-Rampe) | NIE Tagesmax. Früh-Slot liegt **nahe am Tagesmin**. |
| Mo 20:00 / Mi 20:00 (Abend) | **Tagesmax − 3–6 °C** + Asphalt-Effekt (§3) | Abkühlung nach Max, aber warmer Asphalt |
| Mi 17:00 (Nachmittag) | **nahe Tagesmax** | heißester Slot |
| Do-Gym (späterer Nachmittag) | nahe Tagesmax (Hallen-Hitze §4a) | Gym ohne AC |

> **Parkrun-Regel (PFLICHT):** Die Sa-09:00-Temp wird aus dem **Morgenwert** (Tagesmin + kleine Rampe) geschätzt — überschlägig `Tagesmin + 0,3 × (Max − Min)`. **Den Tagesmax NIEMALS als Parkrun-Temp nennen — auch nicht im Fließtext, Verdict oder Reminder.** Beispiel: Sa Min 23 °C / Max 36 °C → Parkrun ~**25–27 °C**, NICHT „36–39 °C". Bei Unsicherheit fragen („Was sagt deine Wetter-App für 09:00?").

---

## 3. 🌦️ Lauf-Impact-Matrix (PFLICHT bei Wetterochs-Input)


| Tag | Startzeit | Wetter | Temp | Wind | Regen | Pace-Korr | Risiko |
|---|---|---|---|---|---|---|---|

Eine Zeile pro relevantem Trainingstag ausfüllen.

**Pace-Korrekturen (Z2):**
| Bedingung | Korrektur |
|---|---|
| >18°C | **+3–4 sek/km pro °C** (V3, Kompressionsshirt-kalibriert) |
| 19–22°C gesamt | +15–25 s/km, Wasser ↑ |
| 23–26°C | +25–40 s/km, HR-Cap strikter |
| starker Wind | +5–10 s/km |
| Regen + Wind | +10–15 s/km |
| <15°C | Cold-Doping (leicht unterkühlt starten) |

**Asphalt-Effekt:** Nach 28°C+ Tag abends +3–5°C effektiv zur Lufttemperatur (Belastungskalkulation).

**Risiko-Ampel:**
| Starttemp (geschätzt) | Ampel | Aktion |
|---|---|---|
| ≤18°C | 🟢 GO | Normal |
| 19–22°C | 🟡 ADJUST | Pace-Korr + Wasser |
| 23–26°C | 🟡 ADJUST | Pace-Korr + HR-Cap strikter |
| >26°C | 🔴 SHIFT | Startzeit verschieben oder kürzen |
| Gewitter / Glatteis | 🔴 NO-GO | Streichen |

---

## 4. Donnerstag (Gym-Hitze + Flex-Regel) & Alternativtage

### 4a. Donnerstag — Gym-Hitze (KEINE Klimaanlage)
Outdoor-Temp am späten Nachmittag/Abend bestimmt die Hallen-Hitze. Senpai zieht Wetterochs und gibt einen **Gym-Hitze-Read**:

| Outdoor (Slot) | Hallen-Erwartung | Aktion |
|---|---|---|
| ≤24°C | 🟢 normal | volle Session, normale PR-Erwartung |
| 25–28°C | 🟡 warm | Hydration ↑, Pausen länger, Intensität leicht runter |
| >28°C | 🟠 heiß | aggressive Hydration (→ `nutrition-skill`), Intensitäts-Erwartung runter, **keine PR-Jagd** in der Sauna-Halle |
| >32°C Dauer-Dome | 🔴 | Session verkürzen/verschieben erwägen — Hitze-Recovery-Kosten |

> Beim **Gym-Re-Entry** (nach Pause) zählt das doppelt: konservative Baseline + heiße Halle = erst recht keine April-PRs erwarten.

### 4b. Donnerstag — Flex-Regel (Do-Lauf statt Gym)
Wetter ist **Kriterium 2** der Flex-Regel (`modules/V3_Protocol.md`, alle 4 müssen erfüllt sein):
- **Do-Wetter ≤22°C Starttemp** = GO/mildes ADJUST → Do-Lauf wetterseitig möglich.
- >22°C → Kriterium 2 verfehlt → Do bleibt Gym.
**Do-Lauf statt Gym = Flex-Regel-Check (4 Kriterien) PFLICHT.** Bei <4 erfüllt: BLOCKEN. Bei 2× Do-Gym-Cancel in Folge: 🔴 hart BLOCKEN (Gym-Minimum-Schutz). Bei kühlem Do **proaktiv** auf die Flex-Regel hinweisen, statt sie verstreichen zu lassen.

### 4c. Alternativtage
- **Mo → Di-Morgen** · **Sa → Ausweich-Parkrun-Location (aus Athleten-Profil)** (nie verschieben).
- **Mi → Do NUR wenn alle 4 Flex-Kriterien erfüllt**, sonst Di-Morgen.

---

## 5. Pre-Lauf-Output

1. **Lauf-Impact-Matrix** (Zeile für den/die Trainingstag/e).
2. **Slot-Empfehlung** (Mi: 17:00 vs 20:00 je nach Hitze + Asphalt-Effekt).
3. **Schuh-Call:** intensitätsbasiert → Schuhe_Ausruestung.md (PERSONAL, aus Drive-Privatordner ziehen: `python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match Schuhe_Ausruestung.md --out ./data` → `./data/Schuhe_Ausruestung.md`) / `modules/V3_Protocol.md` (Easy/Z2 = Easy-Schuh, Intensität = Intensitäts-Schuh; konkrete Modelle siehe Ausrüstung im Profil / Drive).
4. **HR-Ziel:** Z2 ≤147 (Easy/Long) oder Runna-Pace (Race-Sim/Tempo).
5. **Pace@Z2-Erwartung** temperatur-normalisiert.
6. Bei Hitze: Wasser-Hinweis (→ `nutrition-skill` §6).

---

**Ende weather-runprep-skill v1.2.** Wetterochs ist Source of Truth. Wetter = Entscheidungs-Input (vor der Empfehlung, nicht danach). Trainingstage = Mo/Mi/Sa/Do. **Slot-Uhrzeit bestimmt Starttemp — Tagesmax ist fast nie die Starttemp; Parkrun 09:00 = Morgenwert, NIE Tagesmax (§2a).** Hitze-Tax +3–4 s/°C ab 18°C. Do: Gym-Hitze (keine Klimaanlage) + Flex-Regel-Wetter.
