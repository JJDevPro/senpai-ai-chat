# Daten-Parsing-Protokoll

> Referenz-Modul (Instructions v9.0.0). Senpai liest diese Datei bei JSON-/CSV-Uploads oder Datenstruktur-Fragen.
> **Trigger:** HealthAutoExport-JSON, Lauf-/Kraft-CSV, FIT-Datei, Fragen zu Datenstruktur.
>
> ⚠️ **SSoT-Abgrenzung (reconciliiert 24.06.2026):**
> - **FIT-First für Läufe.** FIT-Dateien (HealthFit) sind primär für Form-Analyse (GCT/VO/Stride/Power). Geparst mit `fitparse` (`pip install fitparse --break-system-packages`). Kadenz im FIT = Halb-Kadenz → `(cadence + fractional_cadence) * 2`. `enhanced_speed` vor `speed`. Session-Level-Aggregate sind autoritativ über JSON-Stunden-Ø. GPX = nur GPS-Geometrie, nie für Analyse.
> - **Die operativen Parsing-Workflows leben in den Skills** (`run-bundle-skill`, `gym-bundle-skill`, `daily-check-skill`) — diese laden deterministisch beim Trigger. Diese Datei ist die portable Human-Readable-Referenz (auch für Gemini-Handoff).
> - **Walking-Filter aktualisiert auf v3.5** (Kadenz-primär, siehe §2). Der alte Speed-only-Filter ist deprecated.

---

## 1. JSON (HealthAutoExport)

### Struktur
```python
data['data']['metrics']  # Liste von Metrik-Objekten
```

Jedes Metrik-Objekt: `name`, `units`, `data[]` (Array von Zeitpunkten)

### Wichtige Felder
**Schlaf (sleep_analysis):**
- `totalSleep`, `deep`, `rem`, `core`, `awake`
- `sleepStart`, `sleepEnd` (Zeitfenster)

**HRV (heart_rate_variability):**
- Feld heißt oft `avg` statt `value` — beide prüfen!
- **Schlaf-HRV-Ø IMMER berechnen** zwischen sleepStart und sleepEnd (nicht Tages-Ø nehmen)

**Weitere Pflicht-Felder extrahieren:**
- `resting_heart_rate`
- `walking_heart_rate_average`
- `breathing_disturbances`
- `blood_oxygen_saturation`

### Breathing Disturbances — Actionable-Schwelle
- **>10/h = actionable** (Apple Watch auto-alert)
- **<10/h = unremarkable** → NIE als Alarm framen
- Der Athlet überschreitet diese Schwelle erfahrungsgemäß nur extrem selten (~20×/Jahr) — individuelle Baseline siehe Athleten-Profil / Medical-Notes (Drive)

### Running-Metriken
Laufmetriken sind **eigene benannte Metriken**, nicht in Workouts verschachtelt. Separat suchen.

---

## 2. Lauf-CSV (Apple Watch Export)

### Parsing
```python
df = pd.read_csv(path, sep=';', decimal=',')
df.columns = df.columns.str.strip()  # Whitespace in Headern entfernen!
```

### Umrechnungen
- **Kadenz:** Rohwert × 2 = spm (Apple gibt nur ein Bein aus)
- **Pace:** `1000 / (speed_m_s * 60)` = min/km

### 🚨 WALKING-FILTER v3.5 (PFLICHT — Kadenz-primär!)
**Gehpausen RAUSFILTERN vor jeder Kadenz-/GCT-/Pace-Bewertung:**
```python
# v3.5: Kadenz-primär (deprecated: Speed-only v3.3, GCT-Absenz v3.4)
running_only = df[(df['cadence'] * 2 >= 140) & (df['speed'] >= 2.0)]
# Reine Stopps separat: cadence==0 UND speed<0.5
```
- **Gehpause = Kadenz×2 <140 spm UND Speed <2,0 m/s** (beide Bedingungen gleichzeitig)
- **NIE Gehanteil aus GCT-Absenz ableiten** (Sensor-Dropout bei harter Intensität → False-Positives)
- **Walking-Pausen separat zählen und im Output ausweisen**
- Form-Benchmarks (Kadenz ≥166 spm, GCT ≤280 ms, VO 85–92 mm — SSoT `modules/V3_Protocol.md`/`lib/constants.py`) gelten NUR für Running-Only-Daten
- **Hoher Geh-Wert bei harter Session → plausibilisieren** (Kadenz-Verteilung + User-Erinnerung), nie ungeprüft melden

---

## 3. Kraft-CSV (Gym-Session)

### Spalten-Indices
| Index | Inhalt |
|---|---|
| 0 | Timestamp |
| 3 | Heart Rate |
| 4 | Lap-Nummer |
| 5 | Elapsed Time |

### Logik
- **Lap-Grenzen** = Wechsel im Lap-Nummern-Feld
- **Combo-Geräte** (z.B. Adduktion/Abduktion) = 1 Lap für 2 Übungen
- **Dateiname** enkodiert Session-Datum + Workout-Typ

### 🚨 NIEMALS Übungen aus Laps raten
Wenn die Zuordnung Lap → Übung nicht eindeutig ist → **den Athlet fragen**, nicht halluzinieren.

---

## 4. Output-Format (Analyse-Antworten)

Feste Reihenfolge für Lauf-/Gym-Analyse-Reports:

1. **Übersicht** (Gesamtdauer, Distanz, Ø HR, Splits)
2. **Segment-Tabelle** (nur Running-Only Kilometer, niemals mit Gehpausen)
3. **Walking-Zusammenfassung** (Anzahl Pausen, Gesamtdauer, Kontext)
4. **Highlights** (schnellster Split, höchste Kadenz, niedrigste HR-Drift)
5. **Schlaf/HRV-Kontext** (Vortag-Nacht, aktueller Tag)
6. **Roast** (Senpai-Modus-abhängig)
7. **Coaching** (1-2 konkrete Empfehlungen)
8. **Race-Projektion** (nur bei Long Runs — gegen Ziel/Cutoff des nächsten Events aus dem Renn-Kalender in `live.md`)

---

## 5. Daten-Hierarchie (erinnernd — Vollversion: CLAUDE.md §7)

1. **User-Input im Chat** (inkl. Körperwaage-Gewicht manuell, SoT) = Vorrang
2. **Frisch gezogene Truth-Daten** (HAE-JSON/FIT/Sheets via `pull_drive.py`) = Standard
3. **State-Dateien** (`live.md`, `baselines.md`, … aus dem Drive-Personal-Ordner) = persistenter Live-State
4. **Methoden-/Personal-Module** = statische Referenzen

**Körperwaage-SoT-Protokoll:** SoT = **Montag, nüchtern nach dem Aufstehen** (Richtwert ≤09:00, weiches Fenster — CLAUDE.md §7). Withings-Messungen KÖNNEN im HAE-JSON auftauchen (`body_comp`) — sie zählen nur als SoT, wenn sie dem Mo-nüchtern-Protokoll entsprechen; sonst `off_protocol` (Info, nie SoT). Manuell geposteter Chat-Wert gewinnt immer.
