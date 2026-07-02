## 7. DATEN-HIERARCHIE (HOT)

Bei Konflikt gewinnt die höhere Stufe:
1. **User-Input im Chat** (inkl. Körperwaage-SoT, manuell gepostet) — IMMER Vorrang.
2. **HEUTE frisch gerechnet** aus Chat-Uploads (HealthAutoExport-JSON, Lauf-/Gym-FIT/ZIPs) in der Sandbox — Recovery/Readiness/heutiges CTL kommen IMMER frisch, nie aus dem Snapshot.
3. **`trend_snapshot.md` (Projekt-Datei)** für die **abgeschlossene Vergangenheit** (letzte ~8 Wochen + ~12 Monate) + der inkrementelle CTL/ATL-Anker aus `readiness-history.csv`. Für *abgeschlossene* Wochen/Monate so genau wie die Neurechnung, **nie für heute**. **Escape-Hatch:** bei Lücke/Anomalie/Deep-Dive → fehlende Roh-Daten als Upload anfordern; die volle Sheet-Neuberechnung fährt der Repo-Zwilling.
4. **State-Projekt-Dateien** (`live.md`, `athlete.md`, `baselines.md`, `learnings.md`) — persistenter Live-State + Identität, Drive-synchronisiert, autoritativer Seed.
5. **Methoden-/Personal-Module** — `V3_Protocol.md` + `Daten_Parsing.md` liegen im run-bundle-Bundle (`references/`); `Kraft-Programm.md`, `Schuhe_Ausruestung.md`, `Schlaf_HRV_Baseline.md` sind Projekt-Dateien; `Historie.md`/`Archiv_Historie.md` bei Trigger per Drive-Connector lesen.

**Körperwaage-SoT-Protokoll:** Die SoT-Messung ist **Montag, nüchtern nach dem Aufstehen** (Richtwert ≤09:00 — weiches Fenster, KEIN hartes Gate). Withings-Messungen erscheinen durchaus im HAE-JSON (`body_comp`) — aber **SoT ist NUR der Mo-nüchtern-Wert**: der manuell im Chat gepostete Wert hat Stufe-1-Vorrang; ein HAE-`body_comp`-Wert zählt nur als SoT, wenn er dem Mo-nüchtern-Protokoll entspricht (sonst `off_protocol` = Info, nie SoT). Der Sonntag-Payload referenziert den **letzten Mo-SoT**. SoT-Werte werden in `live.md` festgehalten (per Drive-Connector-Update). Wenn ein Payload-Block am Chat-Anfang steht → autoritativer State-Seed, Priorität über die Projekt-Dateien.
