<!-- SSoT-BANNER (Instructions v9.0.0, ergänzt 24.06.2026) -->
> 🧭 **Diese Datei ist die kanonische Quelle (SSoT) für:** Die-Eine-Regel, HR-Zonen, Runna-Session-Typen, Flexibilitätsregel (4 Kriterien) + Sicherheitsnetz, Gym-Minimum, Hitze-Korrektur (Rechenwert 3,5 s/km/°C ab 18°C, `lib/constants.py`), Schuh-Rotationsmatrix (intensitätsbasiert), Pace@Z2-Definition, Z2-Laufform-Targets.
>
> ⚠️ **Live-State-Hinweis:** Die "Heute"- und "Baseline"-Spalten in den KPI-Tabellen unten sind ein **datierter Snapshot (Ende Mai 2026)**. Aktuelle Werte (Gewicht, KFA, VO2, HRV, PRs, absolvierte Races) = **Live-State (`live.md` + `baselines.md` aus dem Drive-Personal-Ordner)**. Bei Konflikt gewinnt der Live-State. Die *Regeln, Zonen, Formeln und Targets* hier bleiben gültig.

---

# V3 PROTOKOLL — Heavy Hybrid Polarized
> **Status:** VORLÄUFIG v0.5 — 26.05.2026
> **Aktivierung:** JETZT. Ab Mi 27.05.2026, 20:00 am Lauf-Spot (GPS-Polygon aus Athleten-Profil).
> **Vorgänger:** V2 Heavy Hybrid Protocol (09.03.2026–14.06.2026)

---

## Protokoll-Geschichte

| Version | Kern-Änderung |
|---|---|
| **V1** | Laufen + Full-Body-Gym am selben Tag → ZNS-Crash, HRV-Einbruch |
| **V2** | Entzerrung: Mo/Sa = Double Impact (Laufen, dann Core/OK Gym, NIE Beine). Mi = Long Run solo. Do = Pure Gym Full Body "Donnerstag der Zerstörung" |
| **V3** | V2-Struktur unverändert. Neu: Z2-Steuerung nach HR statt Pace. Flex-Regel Lauf>Gym mit Sicherheitsnetz. |

**Warum V3?** Vier Quellen, ein Ergebnis: 23% echter Z2 in 12 Monaten. Runna-Paces landen beim aktuellen Körpergewicht (~aus Profil) in Z3/Z4. Runnas "nicht schneller als X" wurde als Ziel-Pace missverstanden statt als Deckel.

---

## Die Eine Regel

```
Runna sagt "Gesprächstempo" / "nicht schneller als X" / "Easy"
→ HR bleibt in Z2 (aktuell ≤147 bpm)
→ "Nicht schneller als 8:15" = 8:15 ist die DECKE, 9:30 ist korrekt
→ Pace ist Ergebnis — nie Ziel bei diesen Sessions

Runna gibt explizite Pace-Blöcke (Race-Sim, Tempo, Intervalle)
→ Runna-Pace gilt, HR = Diagnostik

Parkrun → Runna-Tagesplan Sa bestimmt Intensität
```

---

## HR-Zonen — dynamisch kalibriert

| Zone | bpm (aktuell) | Label |
|---|---|---|
| Z1 | <136 | Sehr leicht — Warm-up, Cool-down |
| **Z2** | **136–147** | **Gesprächstempo = ZIEL Easy/Long** |
| Z3 | 148–159 | Mäßig — nur strukturiert |
| Z4 | 160–171 | Hart — Tempo, Race-Sim |
| Z5 | ≥172 | Anaerob — Intervalle, Parkrun-Effort |

> **Zonen sind dynamisch.** Mit wachsender aerober Basis sinkt die Pace bei gleichem HR. Z2-Grenze (bpm) kann sich in 6–12 Monaten verschieben → Runna + Apple Watch dann aktualisieren. Fortschrittsmetrik ist Pace@Z2, nicht eine fixe bpm-Zahl.

> **Neue Baseline ab 27.05.2026.** Alle bisherigen HR-Daten hatten Konfundierung durch das alte Kompressionsshirt (+8 bpm Drift bei KM4 bestätigt; Modell siehe Ausrüstung im Profil / Drive). Heat-Tax historisch auf dieses alte Shirt kalibriert — wird mit neuen Läufen neu bewertet.

Alle Systeme synchronisiert: Apple Watch ✅ | HealthFit ✅ | Runna ✅ (26.05) | Senpai ✅

---

## Runna Session-Typen

| Session-Typ | Erkennbar an | V3-Steuerung |
|---|---|---|
| **Easy Run** | "Easy", "Gesprächstempo", "nicht schneller als X" | **HR ≤Z2. Pace-Angabe = Decke.** |
| **Long Run (Endurance)** | "Im Gesprächstempo", kein Pace-Block | **HR ≤Z2. Pace ist Ergebnis.** |
| **Long Run (Progressiv)** | Gestaffelte Pace-Segmente, wird schneller | Pace pro Block. HR darf Z3 im letzten Block |
| **Long Run (Race-Sim)** | Explizite Pace-Blöcke mitten im Lauf | Runna-Pace gilt. HR = Diagnostik |
| **Tempo Run** | "Comfortably hard", eine zusammenhängende Effort-Einheit | Pace gilt. HR typisch Z3–Z4 = korrekt |
| **Threshold / Intervalle** | Wiederholungen mit Erholungspausen | Pace pro Rep gilt. HR-Recovery zwischen Reps tracken |
| **Recovery Run** | "Sehr leicht", sehr kurz | HR ≤Z1 (≤135) |

---

## Parkrun-Logik

| Runna Sa-Plan | Parkrun-Intensität |
|---|---|
| Tempo / Intervalle | Parkrun als Tempo-Session, voller Effort |
| Easy / Dauerlauf | Parkrun kontrolliert Z2–Z3, kein PB-Modus |
| Race-Sim | Parkrun als Race-Sim |
| Nichts / Rest | Trainingspartner-Faktor + Körperzustand entscheiden |

Runna-Sessions nach Möglichkeit auf Sa verschieben. Kein Zwang. Trainingspartner-Faktor und soziale Komponente haben Veto (Parkrun-Partner siehe athlete.md). Körper hat immer Veto. Nicht jeder Sa ist PB-Angriff.

---

## Wochenstruktur

| Tag | Session | Anmerkung |
|---|---|---|
| **Mo** | Runna-Session (HR-gesteuert) + Core/OK Gym | **Start fix 20:00** — gemeinsam mit Partnerin: sie ihr eigenes Training, du Laufen, dann Gym zusammen |
| **Di** | Total Rest | — |
| **Mi** | Runna Long Run (HR-gesteuert oder Race-Sim) | Lauf-Spot bevorzugt (GPS-Polygon aus Athleten-Profil) |
| **Do** | 💀 Pure Gym Full Body — Standard | **Gemeinsam mit Partnerin:** sie ihr eigenes Training, du "Donnerstag der Zerstörung" (4×10 Full Body). Override: siehe Flex-Regel unten |
| **Fr** | Total Rest | — |
| **Sa** | Parkrun 09:00 + Core/OK Gym | Trainingspartner-Faktor (Parkrun-Partner siehe athlete.md). Nie verschieben. |
| **So** | Total Rest | — |

---

## 🔁 Flexibilitätsregel: Laufen > Gym (mit Sicherheitsnetz)

**Prinzip:** Laufen ist Primärsportart. Eine verpasste Lauf-Session wegen Hitze kann am Do nachgeholt werden, wenn das Wetter es erlaubt UND das Sicherheitsnetz nicht reißt.

### Bedingungen für Do-Lauf statt Gym (ALLE 4 müssen erfüllt sein):

```
✅ 1. Mi-Lauf war wegen Hitze nicht absolvierbar oder stark kompromittiert
      (SHIFT-Signal: >26°C Starttemperatur ODER Abbruch im Lauf)

✅ 2. Do-Wetter ≤22°C Starttemperatur (GO oder mildes ADJUST)

✅ 3. Gym wurde diese Woche NOCH NICHT gecancelt
      (Mo-Gym zählt nicht — das ist Core/OK, nicht Full Body)

✅ 4. Letzte vollständige Full-Body-Gym-Session maximal 7 Tage zurück
```

**Wenn alle 4 ✅ → Do-Lauf erlaubt. Do-Gym verschoben auf Fr oder Sa-Zusatz (ohne Trainingspartner/Parkrun zu kompromittieren).**

### Sicherheitsnetz — "Nur laufen macht schwach"-Schutz

| Situation | Regel |
|---|---|
| Do-Gym 1× gecancelt wegen Lauf | OK wenn alle 4 Kriterien erfüllt |
| Do-Gym 2× in Folge gecancelt | 🔴 BLOCKIERT — nächste Woche Do-Gym = Pflicht, kein Override |
| Gym-Sessions <1 Full-Body/Woche über 2+ Wochen | 🔴 Eskalation — Senpai bringt "nur Laufen macht schwach" Karte |
| Letzte Full-Body >10 Tage zurück | 🔴 BLOCKIERT — kein Lauf-Override bis Gym nachgeholt |

### Gym-Minimum (nicht verhandelbar)

- **1 Full-Body-Session pro Woche** — Do Standard, Fr/Sa als Ausweich
- **Mo Core/OK bleibt immer** — das zählt NICHT als Full-Body-Ersatz

> **Historischer Kontext (Historie im Athleten-Profil / Drive):** Messbarer LBM-Verlust in einem "nur Laufen"-Jahr (Größenordnung siehe Historie). Validiert über Mehrjahres-Datensatz. Diese Regel existiert nicht aus Prinzip — sie existiert weil die Daten es beweisen. Flexibilität ja. Schleifen zurück in alte Muster: nein.

### Beispiele

**Beispiel 1 — Mi 27.05 / Do 28.05 (V3-Start-Woche):**
```
Mi: 29°C um 20:00 → SHIFT-Signal (>26°C, aber absolviert)
Do: 20°C → GO ✅
Letzte Full-Body: >10 Tage zurück → 🔴 BLOCKIERT (Kriterium 4)
→ Do 28.05: Gym bleibt PFLICHT. Lauf-Override nicht möglich.
```

**Beispiel 2 — Normalfall Sommer:**
```
Mi: 28°C → Lauf auf 20:00 verschoben, aber absolviert (ADJUST)
Do: plötzlich 18°C → Lauf wäre schöner
→ Kriterium 1 NICHT erfüllt (Mi war absolviert) → Do bleibt Gym
```

**Beispiel 3 — Legitimer Override:**
```
Mi: 32°C, Lauf abgebrochen bei KM5 (SHIFT/Abbruch) → Kriterium 1 ✅
Do: 19°C → Kriterium 2 ✅
Diese Woche kein Gym gecancelt → Kriterium 3 ✅
Letzte Full-Body: Do letzte Woche (7 Tage zurück) → Kriterium 4 ✅
→ Do-Lauf erlaubt. Do-Gym auf Fr oder Sa verschoben.
```

---

## Hitze-Flexibilität und Wetter

**Wetter-Quellen (Priorität wie CLAUDE.md §3):**
1. **User-Angabe** (Apple-Weather-Screenshot / explizite Temp) — gewinnt immer.
2. **Bright Sky / DWD via `lib/weather.py`** — PRIMÄRE präzise Stundenwerte (Slot-Starttemp + Verlauf während des Laufs).
3. **Wetterochs** (RSS + Delphi-JSON) — Narrativ, Gewitter-/Glatteis-Kontext, Fallback (nur tages-granular).
- Bei Unsicherheit Starttemperatur → Senpai fragt: *"Was sagt deine Wetter-App für [Uhrzeit]?"*

**Wichtig: Tagesmax ≠ Starttemperatur.** Die Slot-Starttemp kommt aus dem `lib/weather.py`-Stundenwert; nur im Fallback (kein Bright Sky) aus Tagesmax + Uhrzeit geschätzt (`weather-runprep-skill` §2a). Bei Unsicherheit wird nachgefragt.

**Asphalt-Effekt:** Nach einem 28°C+ Tag gibt Asphalt abends Wärme ab. Bei Start 20:00 nach 30°C-Tag: effektiv +3–5°C zur Lufttemperatur für Belastungskalkulation.

| Starttemp (Slot-Wert) | Wetterampel | Pace-Anpassung Z2 |
|---|---|---|
| ≤18°C | 🟢 GO | Normal |
| 19–22°C | 🟡 ADJUST | Formel: +3,5 s/km je °C >18°C · Wasser ↑ |
| 23–26°C | 🟡 ADJUST | Formel: +3,5 s/km je °C >18°C · HR-Cap strikter |
| >26°C | 🔴 SHIFT | Startzeit verschieben oder kürzen |
| Gewitter | 🔴 NO-GO | Streichen |

**Heat-Tax:** **Rechenwert fix +3,5 sek/km/°C über 18°C** (`lib/constants.py` — EIN Wert für ALLE Rechnungen: Pace@Z2-Normalisierung, Pre-Lauf-Erwartung, Race-Szenarien). Historischer Kontext: die alte +4–5-Kalibrierung galt dem alten Kompressionsshirt; das empirische Kalibrier-Band liegt bei 3–4 und wird aus Kompressionsshirt-Läufen weiter verfeinert — bis dahin rechnet **jede** Formel mit 3,5, nie mit einer frei gewählten Zahl aus dem Band. Senpai trackt die Kalibrierung bei jedem Run-Upload.

---

## Ausrüstung

### Aktive Kompressionsshirts (ab 27.05.2026)
- Aktive, freigegebene Kompressionsshirts (Modelle siehe Ausrüstung im Profil / Drive) ✅

### Blacklist — Laufen (permanent)
| Verboten | Grund | Status |
|---|---|---|
| 🔴 Konfundierendes Kompressionsshirt (siehe Ausrüstung im Profil / Drive) | HR-Drift +8 bpm bestätigt | Einmal verboten, für immer verboten |
| 🔴 Baumwollsocken | Blasenbildung bestätigt | — |
| 🔴 Ergometer als Lauf-Ersatz | Kein aerobes Äquivalent | Im Kopf eingebrannt |

### Schuh-Matrix V3

| Schuh | Einsatz | Bedingungen |
|---|---|---|
| **Z2-Primärschuh** (Modell siehe Ausrüstung im Profil / Drive) | Easy Z2, Long Z2, alle HR≤Z2 Sessions | Primärschuh V3-Volumen. Breiter Vorderfuß = komfortabler bei langen Z2 |
| **Tempo/Race-Schuh** (Modell siehe Profil / Drive) | Tempo, Race-Sim, Intervalle, Parkrun-Effort | Pflicht bei expliziter Pace-Session. Rotation: nicht 2× in Folge ohne Z2-Primärschuh dazwischen |
| **Kurzstrecken-Z2-Schuh** (Modell siehe Profil / Drive) | Easy/Z2 **≤5 km** (selten) | Freigegeben (Athleten-Feedback KW27): NUR Kurzstrecke ≤5 km; ab >5 km der Z2-Primärschuh (Modelle in `athlete.md` / `Schuhe_Ausruestung.md`) |

> **HM-Schuh (Race-Tag, siehe Renn-Kalender live.md):** Wahrscheinlich der Z2-Primärschuh. Entscheidung nach dem letzten Renntraining vor dem Race. Wenn die bekannte Druckstelle wieder auftritt (siehe Medical-Notes im Athleten-Profil) → Z2-Primärschuh für Race Day. Keine Überraschungen auf der Strecke.

> **Tempo/Race-Schuh-Rotation:** Nach Pause >1 Woche: erst 1 Einlauf-Session, dann normal rotieren. Druckstelle nach einem Reise-Restart = Einlauf-Artefakt, keine strukturelle Schwäche.

---

## V3-Fortschrittsmetrik: Pace@Z2

**Definition:** Durchschnittspace eines Z2-Laufs (HR ≤147 stabilisiert) über das Steady-Z2-Segment (Surge-frei), temperatur-normalisiert auf 18°C-Äquivalent.

**Tracking:** Nach jedem Z2-Lauf im Run-Report. Kein separater monatlicher Check-in — Senpai trackt automatisch per Upload.

**Temperatur-Normalisierung (provisorisch):** Roh-Pace − (Starttemp − 18°C) × 3,5 sek/km = normalisierter Wert. Wird mit echten Daten kalibriert.

| Session | Datum | Temp | Pace@Z2 roh | Normalisiert | Shirt |
|---|---|---|---|---|---|
| **Baseline #1** | **27.05.2026** | **TBD** | **TBD** | **TBD** | aktives Kompressionsshirt (siehe Profil) |

---

## Laufform in Z2 — wissenschaftlich kalibriert für den Athleten

**Das Wichtigste zuerst:** Bei Z2-Pace (~9:00–9:30/km) sind Kadenz, GCT und Stride naturgemäß anders als beim Parkrun-Effort. Das ist korrekt und erwartet. Kadenz sinkt mit Pace — das ist Physik, kein Fehler.

**Warum trotzdem hohe Kadenz bei Z2 für dich (bei dem Körpergewicht ~aus Profil):**

Schwerere Läufer haben höhere Bodenreaktionskräfte pro Schritt. Erhöhte Kadenz bei gleicher Pace reduziert die Kraft pro Einzelschritt — das schützt Knie, Hüfte und Achillessehne. Das ist bei einem hohen Körpergewicht kein optionaler Tipp, das ist Gelenkschutz.

**Biomechanik-Zusammenhang (Pflicht-Verständnis):**
- Kadenz ↑ → Stride ↓ → GCT ↓ → Bodenreaktionskraft ↓ → Gelenkschutz ↑
- Kadenz ↓ → Stride ↑ → GCT ↑ → Bodenreaktionskraft ↑ → Gelenkverschleiß ↑

### Z2-spezifische Laufform-Ziele

| Metrik | Z2-Ist (9:15/km) | Z2-Ziel 13W | Z2-Warnsignal | Coaching-Cue |
|---|---|---|---|---|
| **Kadenz** | ~163–166 spm | ≥166 spm | <160 spm → Flag | "Kurze, schnelle Schritte — auch wenn es zu leicht wirkt" |
| **GCT** | ~285–300 ms | ≤280 ms | >315 ms → Flag | "Füße rollen ab, nicht stampfen" |
| **Stride** | ~680–710 mm | ≥710 mm | <640 mm → Flag | "Stride folgt Kadenz — nie Stride erzwingen" |
| **VO** | ~88–93 mm | 85–92 mm | >96 mm = Bouncing | "Vorwärts, nicht hoch" |
| **Vertical Ratio** | ~12–13% | **<11% (aktives Ziel, `learnings.md`)** | >12% → Bouncing | "Horizontale Energie, kein Trampolin" |

> **Coaching-Regel Z2:** Kadenz ist aktiv zu halten, auch wenn alles andere langsamer wird. Bei Anstiegen: Kadenz halten, Pace fällt — korrekt. Kadenz kollabieren lassen ist die gefährlichste Z2-Falle bei hohem Körpergewicht.

> **Parkrun vs. Z2-Vergleich:** Dass Kadenz beim Z2-Lauf niedriger ist als beim Parkrun (185 spm vs. ~165 spm) ist physikalisch normal und korrekt. Das ist kein Rückschritt — das ist pace-adäquate Biomechanik. Was konstant bleibt: Kadenz nie unter 160 spm.

---

## Vollständige V3-KPIs

### Lauf-Performance
| KPI | Heute | Ziel 13W | Ziel 26W |
|---|---|---|---|
| **Pace@Z2** (temp-norm.) | (Live-State: live.md/baselines.md) | ≤8:00/km | ≤7:30/km |
| Z2-Anteil (HealthFit) | (Live-State: live.md/baselines.md) | ≥50% | ≥70% |
| Decoupling Long Run | (Live-State: live.md/baselines.md) | ≤8% | ≤6% |
| VO2Max | (Live-State: live.md/baselines.md) | 39–40 | 40–42 |
| Parkrun (Effort) | (Live-State: live.md/baselines.md) | ~31:30 | ~30:30 |
| **Kadenz Z2** | (Live-State: live.md/baselines.md) | ≥166 spm | ≥170 spm |
| **GCT Z2** | (Live-State: live.md/baselines.md) | ≤280 ms | ≤268 ms |
| **Stride Z2** | (Live-State: live.md/baselines.md) | ≥710 mm | ≥730 mm |
| VO Z2 | (Live-State: live.md/baselines.md) | 85–92 mm | 85–90 mm |

### Body Recomp
| KPI | Heute (SoT, Live-State) | Ziel 13W | Ziel 26W |
|---|---|---|---|
| Gewicht | Körpergewicht-SoT (siehe live.md, Körperwaage manuell) | Ausgangsgewicht −~3,5 kg | Ausgangsgewicht −~7,5 kg |
| KFA | (Live-State: live.md/baselines.md) | ≤29% | ≤26% |
| LBM | (Live-State: live.md/baselines.md) | LBM-Ist +~2 kg | LBM-Ist +~4 kg |
| Bauchumfang (Proxy) | (Live-State / userMemories, manuell) | ↓ Trend | ↓ Trend |

### Gesundheit & Recovery
| KPI | Heute | Ziel |
|---|---|---|
| HRV Ø Nacht | (Live-State: live.md/baselines.md) | ≥65 ms |
| Tiefschlaf | (Live-State: live.md/baselines.md) | ≥15% |
| Bedtime-Score (≤00:00 = 🟢 voll · 00:00–00:30 = 🟡 halb · >00:30 = ❌) | (Live-State: live.md/baselines.md) | ≥5/7 |
| Protein-Floor ≥150g | (Live-State: live.md/baselines.md) | ≥5/7 |

### Gym-Compliance (V3-Sicherheitsnetz)
| KPI | Standard | Warnung | Eskalation |
|---|---|---|---|
| Full-Body/Woche | ≥1 | =0 (1 Wo) | =0 (2+ Wo) |
| Letzte Full-Body | ≤7 Tage | 8–10 Tage | >10 Tage |
| Do-Override-Frequenz | ≤1×/Wo | 1× | 2× in Folge |

---

## Warum Z2 Recomp beschleunigt

```
Z3/Z4-dominant (V2):          Z2-dominant (V3):
Cortisol ↑ nach Lauf           Cortisol ↓
→ LBM Abbau                    → Erholung schneller
→ Gym-Fatigue                  → Do-Gym mit mehr Kraft
→ Hunger-Spike                 → Hunger stabiler
→ Tracking bricht              → Protein-Floor haltbar
→ Plateau beim Ausgangsgewicht → Echtes Defizit messbar
```

Z2 = primär Fettoxidation statt Glycolyse. Gym profitiert von niedrigerer Lauf-Fatigue. Das ist der Recomp-Flywheel.

---

## Motivations-Anker

Z2 bei 9:15/km fühlt sich nach Zeitverschwendung an. Es ist Infrastrukturaufbau.

| Woche | Was passiert | Sichtbar wann |
|---|---|---|
| 1–3 | Mitochondrien-Signalgebung. Enzymaktivierung. | Noch nicht |
| **3–5** | **Kritische Phase.** Pace@Z2 bewegt sich kaum. Gym-PRs kommen. | Do-Session |
| 6–8 | Erster Pace@Z2-Sprung: ~8:45/km möglich | Run-Upload |
| 8–10 | RHR kann weiter sinken. HRV tendiert ↑ | JSON-Daten |
| 10–13 | Parkrun-PB-Versuch mit mehr Reserve | Sa-Upload |
| 16–20 | Beim Pace des Trainingspartners: HR-Gap schmilzt | Mi-Vergleich |

**Anker-Satz:** *"9:15/km heute = 7:30/km in 6 Monaten bei gleichem HR. Der Trainingspartner ist der Beweis."*

---

## Rennkalender 2026–2027

> Konkrete Events + Daten leben im Renn-Kalender (live.md aus dem Athleten-Profil / Drive). Struktur und Phasen-Logik bleiben hier.

| Datum | Event | Phase | Ziel |
|---|---|---|---|
| **(aus Renn-Kalender, live.md)** | Halbmarathon | V2-Finale | Cutoff 3:00:00 |
| (aus Renn-Kalender, live.md) | Deload | Übergang | Kein Laufen, Gym 60% OK-only |
| ab Übergang | V3 voll | — | — |
| **(aus Renn-Kalender, live.md)** | 10km-Stadtlauf | V3-Ernte | ~1:10–1:13 |
| (aus Renn-Kalender, live.md) | Runna-Plan nach Lust | V3-Peak | TBD |

---

## Versions-Log

| Version | Datum | Änderung |
|---|---|---|
| v0.1 | 26.05.2026 | Erster Entwurf |
| v0.2 | 26.05.2026 | V1/V2-Geschichte, Parkrun, Schuh, Recomp-KPIs |
| v0.3 | 26.05.2026 | Pace@Z2, "nicht schneller als X" als Deckel, Hitze-Flexibilität, Kompressionsshirts |
| v0.4 | 26.05.2026 | Mo 20:00 + Partnerin-Kontext. HM-Schuh offen bis Renntraining. Z2-Laufform wissenschaftlich. Stride in KPIs. |
| **v0.5** | **26.05.2026** | Flexibilitätsregel Laufen > Gym mit 4-Kriterien-Check. "Nur Laufen macht schwach"-Schutzregel. Gym-Minimum 1 Full-Body/Woche nicht verhandelbar. Gym-Compliance-KPIs ergänzt. |

---

*"Runna gibt Struktur. HR gibt Intensität. Pace ist Ergebnis."*
*— Senpai × {Anrede} (Anrede aus athlete.md), 26.05.2026*
