<!-- Dummy — echte Daten leben NUR in Drive. Diese Datei ist ein DATA-FREIES Template. -->
<!-- Vor dem Upload alle {{PLATZHALTER}} ersetzen und die Musterwerte überschreiben. -->

# Athlet-Profil (athlete.md) — STABILE IDENTITÄT

> Autoritativer Identitäts-Seed (CLAUDE.md §0/§7). Wird bei Session-Start via
> `pull_drive.py` nach `./data/athlete.md` gezogen. Personal-Data-frei im Repo —
> die echten Werte existieren ausschließlich in der privaten Drive-Datei.

## Identität
- **Name:** {{NAME}}  <!-- Dummy: Max Mustermann -->
- **Geburtsdatum:** {{GEBURTSDATUM}}  <!-- Dummy: 1990-01-01 -->
- **Größe:** {{GROESSE_CM}} cm  <!-- Dummy: 180 cm -->
- **Beruf:** {{BERUF}}  <!-- Dummy: Cloud Engineer -->
- **Wohnort:** {{STADT}}  <!-- Dummy: Musterstadt -->

## Anrede-Form → Name-Mapping (CLAUDE.md §2)
| Trigger | Anrede-Form |
|---|---|
| Default | {{VORNAME}}-kun  <!-- Dummy: Max-kun --> |
| Großer Win / 🟢🟢 | {{VORNAME}}-sama  <!-- Dummy: Max-sama --> |
| Gejammer / 🔴 | {{KOSENAME}}-chan  <!-- Dummy: Maxi-chan --> |
| Morgen-Roast-Fenster (05–10 Uhr) | {{ROAST_WORT_MORGEN}}  <!-- Dummy: Schlafmütze --> |

**Roast-Wörter (rotieren, max 1×/Antwort):** {{ROAST_WORT_1}}, {{ROAST_WORT_2}}, {{ROAST_WORT_3}}
<!-- Dummy: Faultier, Couch-Boss, Snack-Goblin -->

## Körper-SoT-Schwellen
- **Metabolische Gewichts-Schwelle:** {{GEWICHT_SCHWELLE_KG}} kg  <!-- Dummy: 80.0 kg -->
- **Gewichts-Annäherungs-Band:** {{ANNAEHERUNG_KG}} kg  <!-- Dummy: 2.0 kg -->
- **Ziel-KFA:** {{ZIEL_KFA_PCT}} %  <!-- Dummy: 12.0 % -->
<!-- Viszeralfett ist als KPI GESTRICHEN (CLAUDE.md §1, Entscheidung 2026-07-02) — kein Ziel, kein Feld. Bauchumfang (manuell) ist der ergänzende Proxy. -->

## Medical / Sensor-Notizen (Ignore-Regeln, CLAUDE.md §6)
- **Kardialer Rhythmus-Marker:** {{AFIB_REGEL}}  <!-- Dummy: AFib-Burden NICHT als Trainings-Signal werten -->
- **Atmungs-Störungs-Marker-Schwelle:** {{ATEM_SCHWELLE}} /h  <!-- Dummy: 10 /h -->
- **Allergie/Medikation:** {{ALLERGIE_TRIGGER}}  <!-- Dummy: Pollen-Saison Frühjahr -->

## Persönliches Equipment
- **Laufschuhe:** {{SCHUHE}}  <!-- Dummy: ASICS Novablast 5 -->
- **Equipment-Blacklist beim Laufen:** {{BLACKLIST}}  <!-- Dummy: Baumwoll-Socken (HR-Drift) -->

## Menschen
- **Partner:in:** {{PARTNER}}  <!-- Dummy: Erika Mustermann (Mo Zumba 20:00) -->
- **Trainingspartner:** {{TRAININGSPARTNER}}  <!-- Dummy: Sa-Parkrun-Anker -->

## Ziele
- **Primärziel:** {{ZIEL}}  <!-- Dummy: NFL-Runningback-Physique / Samurai-Cut -->
- **Nächstes Rennen:** {{RENNEN}}  <!-- Dummy: Muster-Halbmarathon, Datum offen -->

## Wochenrhythmus (CLAUDE.md §4)
- Mo Run+Core/OK 20:00 · Di Rest · Mi Long Run · Do Pure Gym Full Body ≤21:30
- Fr Rest · Sa Parkrun 09:00 + Trainingspartner · So Rest
