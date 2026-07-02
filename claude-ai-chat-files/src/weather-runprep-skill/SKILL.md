---
name: weather-runprep-skill
description: "Senpais Wetter- & Pre-Lauf-Engine. Trigger: wetter, lauf, regen, hitze, pace, schuhe, Trainingstage Mo/Mi/Do/Sa. Bright-Sky-Stundenwerte, Impact-Matrix, Hitze-Tax, GO/ADJUST/SHIFT."
---


# Weather-Runprep-Skill v1.3 — Senpai Wetter- & Pre-Lauf-Engine

## §0-CAI · Laufzeit & Datenbeschaffung (claude.ai)

> Dieses Bundle ist der claude.ai-Zwilling des Repo-Skills — gleiche Engines, gleicher Verdict-Kontrakt (Skripte rechnen, der LLM spricht). Skripte laufen in der Code-Sandbox (Python 3.11). Vorbereitung: `mkdir -p ./data`. Den Skill-Ordner per `ls` unter `/mnt/skills/` finden (Pfade nie blind hardcoden), Skripte als `python3 scripts/<name>.py` aus dem Skill-Ordner aufrufen.

**Datenbeschaffung:**

| Was | Woher |
|---|---|
| Bright-Sky-Stundenwerte | URL aus `assets/brightsky_url.txt` ({date} ersetzen) per CHAT-Web-Fetch holen → Antwort ungekürzt nach `./data/brightsky.json` → `python3 scripts/weather.py --from-json ./data/brightsky.json …` |
| Wetterochs (Narrativ/Gewitter/Fallback) | Chat-Web-Fetch RSS + Delphi-JSON (wie gehabt) |
| gear.md · coaching_cues.md · live.md | State-Read (Projekt-Wissen bzw. Drive-Connector frisch, siehe unten) → bei Skript-Bedarf Inhalt nach `./data/<name>` schreiben |

**State-Read:** Rohe `.md`-State-Dateien lassen sich in claude.ai NICHT als Drive-synchronisierte Projekt-Dateien anbinden (Sync kann nur Google-native Formate). Regel: statische Kopie im Projekt-Wissen = Grundkontext; bei Zahlen-Relevanz (`live.md`, `baselines.md`, `gear.md`, `readiness-history.csv`) die Datei per Drive-Connector aus „Senpai-AI-Chat“ FRISCH lesen — Connector-Stand schlägt jede statische Kopie.

**Write-Back:** Google-Drive-Connector — die BESTEHENDE Datei im Drive-Ordner „Senpai-AI-Chat“ aktualisieren (nie ein Duplikat anlegen). Fallback bei fehlgeschlagenem Write: kompletten neuen Datei-Inhalt als Code-Fence ausgeben, der User ersetzt ihn in Drive.

**Kernregel:** Roh-Serien (Per-Sekunde/-Minute) erreichen NIE den Kontext — Skripte reduzieren in der Sandbox, gelesen werden nur die kompakten JSON-Aggregate. Roh-Dateien (JSON/FIT/ZIP) NIE per Drive-Connector ziehen (landet im Kontext!) — immer als Chat-Upload anfordern (landet in der Sandbox).

**Wichtig:** Die Sandbox hat KEIN freies Netz — Bright Sky wird auf CHAT-Ebene gefetcht, das Skript parst nur die gespeicherte JSON (`--from-json`).

---


> Senpai lädt diese Datei bei Trainingstag/Lauf-/Wetter-Triggern.
> **Trainingstage = Mo / Mi / Sa / Do.** Mo/Mi/Sa = Lauf-Slots. **Do = Gym (KEINE Klimaanlage, siehe Ausrüstung im Profil) + Flex-Regel-Tag** → auch hier wetterrelevant (§4).
> **🎯 Kern-Prinzip: Wetter ist ENTSCHEIDUNGS-INPUT, kein Nachgang.** An einem Trainingstag wird die Vorhersage **VOR** der Rest-vs-Lauf-/Gym-Empfehlung gezogen — nicht erst, wenn der User „doch Lauf" sagt. Auch wenn Rest empfohlen wird: Wetter zuerst, dann Empfehlung (38°C stützt Rest; überraschend kühl kippt die Rechnung / triggert die Flex-Regel).
> **Wochentag + Uhrzeit = echte VM-Uhr** (scripts/clock.py, CLAUDE.md §3). Slot-Zeiten sind fest (Sa 09:00, Mo/Mi 20:00, Do-Gym ≤21:30); der Clock sagt, ob ein Slot JETZT ansteht → Pre-Lauf-Fenster feuert verlässlich.
> **Wetter-Source-Priorität:** User-Angabe (Apple-Weather-Screenshot/Temp) > **Bright Sky/DWD (scripts/weather.py, präzise Stundenwerte)** > Wetterochs (Narrativ/Gewitter/Fallback) > `[kein Wetter]`.

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

## 2. Wetter-Quellen (Dual-Source: Bright Sky/DWD präzise + Wetterochs Narrativ)

**PRIMÄR — präzise Stundenwerte: Bright Sky / DWD** (Chat fetcht, Skript rechnet — identische deterministische Slot-/Asphalt-Ausgabe):
1. Bright-Sky-URL aus `assets/brightsky_url.txt` nehmen, darin `{date}` durch den Zieltag `YYYY-MM-DD` ersetzen.
2. Die URL per **Chat-Web-Fetch** abrufen — das kann der Chat nativ. NICHT aus dem Sandbox-Skript fetchen.
3. Die JSON-Antwort **UNGEKÜRZT** in `./data/brightsky.json` speichern (vorher `mkdir -p ./data`).
4. Dann EXAKT:
```bash
python3 scripts/weather.py --from-json ./data/brightsky.json --lat <lat> --lon <lon> --date <YYYY-MM-DD> --slot-start HH:MM --slot-end HH:MM
```
- **lat/lon stehen in derselben `assets/brightsky_url.txt`** (NIE raten/hardcoden). tz-Default Europe/Berlin (Slot-Zeiten sind dann lokal).
- Liefert kompakt: `slot_window` (eine Zeile je Stunde über das Lauf-Fenster: `temperature`, `precipitation`, `precipitation_probability`, `wind_speed`/`wind_gust_speed` [km/h], `dew_point`, `cloud_cover`, `condition` **+ `asphalt_surface_c_est` / `asphalt_excess_c_est`**), `day_summary` (min/max/mean, max_precip_prob, **day_sunshine_min, mean_cloud_cover, asphalt_residual_c_est**), `warnings`. **NIE das rohe 24-h-Array** (§0).
- **Einheiten:** °C · mm · % · km/h. **`asphalt_*_est` = Heuristik aus solar/sunshine/cloud (KEIN Messwert)** — so labeln (sonniger Tag → mehr gespeicherte Hitze; Regen kühlt den Belag → ~Lufttemp).

**NARRATIV + Gewitter/Glatteis + Fallback: Wetterochs** (WebFetch, BEIDE Endpoints):
- **RSS-Prosa (heute + 6 Tage):** `https://www.wetterochs.de/wetter/current/WettermailRssInHtml.html`
- **Delphi-JSON (ab morgen, 9 Tage):** `https://www.wetterochs.de/wetter/delphi/gen/WetterRegnitz.json`
- Wetterochs-JSON ist nur **tages-granular** (Min/Max) → NICHT für exakte Slot-Zahlen. Nutzen: Prosa-Kontext, Gewitter/Glatteis-Warnung, Fallback wenn Bright Sky fehlt.

> **Fallback:** Schlägt der Chat-Web-Fetch der Bright-Sky-URL fehl oder meldet das JSON `error`/`warnings` → auf Wetterochs (§2a-Heuristik) zurückfallen. Beide fail → `[kein Wetter]`, nach Apple-Weather-Screenshot fragen, wenn trainingsrelevant.

### 2a. ⏰ Slot-Uhrzeit → Starttemp (Fallback-Heuristik, wenn Bright Sky fehlt)
**Wenn scripts/weather.py (Bright Sky) läuft, ist die Slot-Starttemp DIREKT der `slot_window`-Stundenwert** — diese Heuristik dann NICHT nötig. Nur als **Fallback** (Bright Sky nicht erreichbar, nur Wetterochs Min/Max vorhanden): Die relevante Temp hängt an der **Slot-Uhrzeit**, NICHT am Tagesmax (der fällt nachmittags ~15–17 Uhr) — so ableiten:

| Slot | Sommer-Starttemp ≈ | Quelle/Regel |
|---|---|---|
| **Sa-Parkrun 09:00** | **Tagesmin + 1–4 °C** (Morgen-Rampe) | NIE Tagesmax. Früh-Slot liegt **nahe am Tagesmin**. |
| Mo 20:00 / Mi 20:00 (Abend) | **Tagesmax − 3–6 °C** + Asphalt-Effekt (§3) | Abkühlung nach Max, aber warmer Asphalt |
| Mi 17:00 (Nachmittag) | **nahe Tagesmax** | heißester Slot |
| Do-Gym (späterer Nachmittag) | nahe Tagesmax (Hallen-Hitze §4a) | Gym ohne AC |

> **Parkrun-Regel (PFLICHT):** Die Sa-09:00-Temp wird aus dem **Morgenwert** (Tagesmin + kleine Rampe) geschätzt — überschlägig `Tagesmin + 0,3 × (Max − Min)`. **Den Tagesmax NIEMALS als Parkrun-Temp nennen — auch nicht im Fließtext, Verdict oder Reminder.** Beispiel: Sa Min 23 °C / Max 36 °C → Parkrun ~**25–27 °C**, NICHT „36–39 °C". Bei Unsicherheit fragen („Was sagt deine Wetter-App für 09:00?").

---

## 3. 🌦️ Lauf-Impact-Matrix (PFLICHT bei Wetter-Input)

| Tag | Startzeit | 🌤️ Wetter | 🌡️ Temp (Slot) | 🛣️ Asphalt (Schätzung) | 💨 Wind | 🌧️ Regen | Pace-Korr | Risiko |
|---|---|---|---|---|---|---|---|---|

Eine Zeile pro relevantem Trainingstag. **Temp (Slot) + Asphalt kommen direkt aus scripts/weather.py** (`slot_window`), NICHT aus dem Tagesmax.

**🕒 Stunden-Fenster (PFLICHT bei Lauf >1 h oder spürbarem Bedingungs-Drift):** zusätzlich eine Zeile je überlappter Stunde aus `slot_window` — zeigt, wie Temp/Regen/Wind sich WÄHREND des Laufs ändern (claude.ai konnte nur den Startwert):

| 🕒 Stunde | 🌡️ Luft | 🛣️ Asphalt (Schätz.) | 🌧️ Regen / P(%) | 💨 Wind km/h | Risiko |
|---|---|---|---|---|---|
| 20:00 | 23,6 °C | ~24,6 °C | 0,9 mm / 37 % | 11 (Böen 22) | 🟡 |
| 21:00 | … | … | … | … | … |

**Pace-Korrekturen (Z2) — EINE Temperatur-Formel (Rechenwert die Schwellen-Registry des Repos):**
| Bedingung | Korrektur |
|---|---|
| >18°C | **fix +3,5 sek/km pro °C über 18°C** (V3-Rechenwert; Kalibrier-Band 3–4 nur Doku). Beispiele: 22°C → +14 s/km · 26°C → +28 s/km. Ab 23°C zusätzlich: HR-Cap strikter, Wasser ↑ |
| starker Wind | +5–10 s/km |
| Regen + Wind | +10–15 s/km |
| <15°C | Cold-Doping (leicht unterkühlt starten) |

**Asphalt-Effekt (datengetrieben):** scripts/weather.py schätzt den Belag-Aufschlag aus solar/sunshine/cloud_cover (`asphalt_excess_c_est`) — **sonniger Tag = mehr gespeicherte Hitze in den Abend, bewölkt/Regen = ~0** (Regen kühlt den Belag nass). Die `asphalt_surface_c_est` für die Belastungskalkulation nutzen, **klar als Schätzung labeln**. **Fallback** ohne Bright Sky: pauschal +3–5 °C nach einem 28 °C+-Tag.

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

1. **Lauf-Impact-Matrix** (+ Stunden-Fenster bei Lauf >1 h, §3).
2. **Slot-Empfehlung** (Mi: 17:00 vs 20:00 je nach Hitze + Asphalt).
3. **💧 Taupunkt:** [XX °C] ([Band aus scripts/weather.py `dew_point_band`: <0 sehr trocken · 0–10 trocken bis angenehm · 10–15 leicht feucht · 15–20 **schwül, unangenehm** · >20 sehr schwül, drückend]) — sagt, wie schwül es wird; hoher Taupunkt → Verdunstungskühlung sinkt, HR läuft heiß → unteren Z2-Rand starten.
4. **🌅 Sonnenuntergang:** [HH:MM] (aus `sun.sunset`) — bei Abend-Slots: noch [X] min Tageslicht zum Start; **Stirnlampe** ja/nein (Dämmerung/Winter) + ggf. beleuchtete Strecke wählen.
5. **👕 Bekleidung** (Präferenzen aus `athlete.md`, temp+taupunkt+regen-bewusst): ~20–25 °C → kurze Hose + Kompressionsshirt; **Regen** → Cap (hält die Brille trocken) ODER Kontaktlinsen, Regenjacke bei milder Schwüle eher NEIN; **kalt/Winter → Schichten, aber NICHT überbekleiden** (Hitzestau-Fallstrick: lieber kühl starten — der Körper heizt beim Laufen stark auf).
6. **👟 Schuh-Call:** Easy >5 km → **ASICS Superblast 3** (+ ASICS Megablast als Alternative); Easy ≤5 km → **ASICS Novablast 5**; Tempo/Race → Intensitäts-Schuh. Detail/Pre-Hab → `Schuhe_Ausruestung.md` (Drive) / `modules/V3_Protocol.md`.
7. **HR-Ziel:** Z2 ≤147 (Easy/Long) oder Runna-Pace (Race-Sim/Tempo).
8. **Pace@Z2-Erwartung** temperatur-normalisiert.
9. Bei Hitze/Schwüle: Wasser-/Elektrolyt-Hinweis (→ `nutrition-skill` §6).

### 5a. 🎯 Mental Cues (eigener Block — VOR dem Lauf, getrennt vom Wetter)
Die session-übergreifende Coaching-Schleife (run-bundle §12d schreibt sie): `coaching_cues.md` ist eine Drive-synchronisierte Projekt-Datei — Inhalt steht bereits im Kontext, kein Pull nötig. Direkt daraus
die **OPEN-Cues des heutigen Slot-Typs** (Mo/Mi=Easy/Long, Sa=Parkrun — §1/V3) als eigenen Block zeigen:
> 🎯 **Mental Cues — letzter [Typ]-Lauf:** [1–3 OPEN-Cues, je „Metrik war X 🟡, heute Ziel Y → Cue-Phrase"].
> Primär-Dauer-Cue: **Vertical Ratio <11 %** („Vorlage aus den Knöcheln, kein Trampolin") aktiv coachen.

Heute auf diese Cues achten; der nächste Run-Report (§12d Cue-Check) prüft, ob sie umgesetzt wurden.
Fehlt `coaching_cues.md` (noch nicht pre-seeded) → kein Block, kein Drama. KEIN Cue offen → 1 Zeile „🟢 keine offenen Cues".

### 5b. 🅿️ Sa-Parkrun-Anker (Heim-Strecke aus athlete.md) + Partner-Layer + Schuh-km (Strava §18)

An **Samstag** (Parkrun 09:00, Heim-Strecke — Ort/GPS-Anker in `athlete.md`) zusätzlich zum Wetter proaktiv ankern:
- **Schuh-km (`gear.md` / Strava `get_gear`):** kurzer Rotations-Check — passt der Schuh zum Slot, Verschleiß ok? (run-bundle §18).
- **Partner-Layer (`athlete.md`):** Parkrun-Partner + Crew sind FAST immer dabei (Ritual; Personen in `athlete.md`) → als Motivation framen. **Partner-Faktor (KM1-Drossel — Wert in `athlete.md`) NUR ansagen, wenn ihr zusammen lauft** (Partner-Plan Easy + Athleten-Tempo); sonst NICHT annehmen — **Präsenz ≠ zusammen gelaufen** (Strava bestätigt Co-Runner nicht).
- **Parkrun-Counter (`live.md`):** der nächste Lauf ist #[N+1] — als kleinen Anker nennen.
- **Temp = Morgenwert 09:00** (Tagesmin + Rampe, NIE Tagesmax — §2a).

---

**Ende weather-runprep-skill v1.3.** Source-Priorität: User-Angabe > **Bright Sky/DWD (präzise Slot-Zahlen)** > Wetterochs (Narrativ/Gewitter/Fallback). Wetter = Entscheidungs-Input (vor der Empfehlung, nicht danach). Trainingstage = Mo/Mi/Sa/Do. **Slot-Uhrzeit bestimmt Starttemp — Tagesmax ist fast nie die Starttemp; Parkrun 09:00 = Morgenwert, NIE Tagesmax (§2a).** Hitze-Tax fix 3,5 s/km/°C ab 18°C. Do: Gym-Hitze (keine Klimaanlage) + Flex-Regel-Wetter.

---
> Export-Stand: weather-runprep-skill v1.3 · senpai-ai-chat@ebb935d · content 92338dcd75d0 · generiert von export_claude_ai.py — NICHT von Hand editieren.
