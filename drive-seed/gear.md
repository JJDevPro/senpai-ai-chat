<!-- Dummy — echte Daten leben NUR in Drive. Dieses Template ist DATA-FREI. -->

# Senpai · Gear & Segment State (gear.md) — mutable, Strava-derived

> **Zweck:** Schuh-Kilometer + Segment-Baselines aus Strava (MCP `get_gear` /
> `get_activity_performance.segment_efforts`). Geschrieben vom `run-bundle-skill`
> (Tier 2, §18) nach jedem Lauf; gelesen in SCHRITT 0. Pull/Write-Back via
> `pull_drive.py` (Drive-Ordner `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde`).
>
> **⛔ Personal-Data-frei im Repo:** Dieses Seed enthält nur Dummy-Werte. Echte
> gear_ids/Modelle/km/Segmente leben ausschließlich im Drive-Exemplar. EINMAL selbst
> nach Drive laden (Service-Account ist update-only/no-create), danach pflegt Senpai es.
>
> **Abgrenzung:** `Schuhe_Ausruestung.md` = read-only Regel-Modul (Rotation/Blacklist/Pre-Hab,
> KEINE km). `gear.md` = mutable, maschinen-geschrieben (km + Segmente). Schuh-km NIE nach
> `Schuhe_Ausruestung.md` schreiben (§18.5 / Skill-Bruch).

---

## Schuh-Kilometer (Quelle: Strava `get_gear`, total_distance in Metern → /1000)

| gear_id | Modell (voll ausschreiben) | km | Stand (Strava-Sync) | Status |
|---------|----------------------------|------|---------------------|--------|
| g000001 | ASICS Mustermodell A | 0.0 | {{YYYY-MM-DD}} | aktiv |
| g000002 | ASICS Mustermodell B | 0.0 | {{YYYY-MM-DD}} | aktiv |

> Verschleiß-Flag bei ~600–800 km (bei hohem Körpergewicht eher früh). `retired:true` aus
> Strava → Status „retired". Modellnamen IMMER voll (NEVER-Liste, kein Abkürzen).

## Segment-Baselines (Quelle: Strava `segment_efforts`; PR ⇒ neue Baseline)

| segment_id | Name | Best (MM:SS) | Datum | Letzter Effort | Δ |
|------------|------|--------------|-------|----------------|-----|
| s000001 | {{Segment-Name}} | 0:00 | {{YYYY-MM-DD}} | 0:00 ({{YYYY-MM-DD}}) | — |

> Sa-Heim-Parkrun = Marquee-Segment-Vergleich (gleiche Strecke jede Woche →
> strecken-normalisierter Fitness/Pace@Z2-Trend). Segment nicht auf der Strecke → keine
> Δ-Zeile, nicht erfinden.
