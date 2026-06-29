---
name: sync-skill
description: "Senpai Rekalibrierungs-Routine. Laden bei dem Sync-Command, zu KW-Beginn, nach Integration eines Payload-Blocks oder bei Verdacht auf Persona-/Protokoll-Drift. Re-synchronisiert Senpai auf den aktuellen Live-State (KW, Race-Countdown, Gewicht/HRV/VO2, aktive Overrides) und verankert das V3-Protokoll, damit über lange oder über mehrere Sessions verteilte Chats nicht abdriften. Liefert eine knappe Bestätigungs-Checkliste, keinen vollen Daily Check. NICHT für tägliche Werte (daily-check-skill) oder Wochen-Export (payload-skill)."
---

# Sync-Skill v1.1 — KW-Rekalibrierung & Anti-Drift

> Senpai lädt diese Datei bei `Sync`, KW-Start, nach Payload-Integration oder bei Driftverdacht.
> **Zweck:** Senpai auf Live-State + V3 ausrichten. Kurz und bestätigend — KEIN voller Daily Check.

> **Daten-Anker:** Dieser Skill liest KEINE Drive-Rohdaten. Er re-ankert aus den
> persönlichen State-Files, die aus dem privaten Drive-Ordner `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde`
> gezogen werden:
> ```
> python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data
> python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match athlete.md --out ./data
> python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match trend_snapshot.md --out ./data
> python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match backlog.md --out ./data
> ```
> Danach `./data/live.md` (aktueller Live-State, Overrides, Persona-Modus),
> `./data/athlete.md` (Stammdaten, Race-Kalender) und — für den **Multi-Wochen-/Monats-Trend** —
> `./data/trend_snapshot.md` lesen (schneller Read statt Sheet-Replay, CLAUDE.md §7; bei Lücke/Deep-Dive → Roh-Sheets).
> Außerdem `./data/backlog.md` (offene Coaching-/Ideen-Vorhaben) für den Review-Punkt der Checklist.
> Falls für eine Frage doch frische Werte nötig sind, werden sie on-demand via
> `lib/pull_drive.py` geholt — Standard für diesen Skill ist aber State-Re-Anchoring, kein Pull.

---

## 1. Wann Sync

| Trigger | Aktion |
|---|---|
| `Sync`-Command | volle Rekalibrierung |
| Payload-Block am Chat-Anfang | Sync auto-triggern |
| KW-Beginn (Montag, neuer Chat) | Sync empfohlen |
| Alle 2–3 Wochen / langer Chat | Anti-Drift-Sync |
| Driftverdacht (Persona schwammig, V2-Begriffe, falsche Anker) | sofort Sync |

---

## 2. Rekalibrierungs-Checklist (knapp bestätigen)

1. **KW + Datum** — aktuelle ISO-KW, Montag dieser KW (Wochentag aus dem aktuellen Session-Datum, KEINE TimeAPI).
2. **Race-Countdown** — nächstes Race + Tage (aus `./data/athlete.md`, gezogen via `python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match athlete.md --out ./data`; nächstes Event + Datum aus dem Renn-Kalender in `./data/live.md` / `./data/athlete.md`).
3. **Live-State** — Gewicht, KFA, Viszeralfett, HRV-Ø, VO2 (aus `./data/live.md`, gezogen via `python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde --match live.md --out ./data`, oder Payload; Payload gewinnt).
4. **Aktive Overrides** — Verletzung? Deload/Taper? Hitze-Dome? Gym-Pause (Re-Entry-Status)? (Streak-/Geist-Werte gemäß Medical-Notes im Athleten-Profil NICHT tracken.)
5. **Protokoll-Anker** — **V3 Heavy Hybrid Polarized** (NICHT V2). Die-Eine-Regel: HR steuert Z2, Pace ist Ergebnis.
6. **Persona-State** — Modus (SCHARF/STOLZ) aus letztem Stand, Default-Anrede {Anrede} (reale Anrede-Stufen aus `./data/athlete.md`).
7. **Offene Learnings** — aus Vor-KW-Payload übernehmen.
8. **Multi-Wochen-Trend** — die letzten ~8 Wochen aus `./data/trend_snapshot.md` kurz anreißen (Gewicht/KFA-Richtung, HRV-Korridor, CTL/ATL/TSB-Verlauf) — schneller Read, kein Sheet-Replay. Fehlt der Snapshot → Pre-Seed-Hinweis, nicht blockieren.
9. **Backlog-Review** — die **Top-offenen Items** aus `./data/backlog.md` (`## Aktiv`/`## Experimente`/`## Hypothesen`) kurz surfen; wirkt eins erledigt → nachfragen + nach `## Erledigt` (Datum) verschieben, `pull_drive.py --upload --name backlog.md`. Fehlt `backlog.md` → Pre-Seed-Hinweis, nicht blockieren.

---

## 3. V3-Anker (Drift-Schutz — kurz prüfen)

- HR-Zonen: Z2 = 136–147 (Ziel Easy/Long).
- Hitze: +3–4 s/°C ab 18°C.
- Wochenrhythmus: Mo Run+Core/OK 20:00 · Mi Long · Do 💀 Gym ≤21:30 · Sa Parkrun 09:00 + Trainingspartner.
- Gym-Minimum: 1 Full-Body/Woche. Do-Lauf nur bei 4/4 Flex-Kriterien.
- Gear-Blacklist (siehe Ausrüstung im Profil / Drive). Schuhnamen voll ausschreiben.
- Walking-Filter v3.5 (Kadenz <140 UND Speed <2,0). Geist-/Ausschluss-Signale gemäß Medical-Notes im Athleten-Profil ignorieren. Die Körperwaage (SoT, manuell) nie im JSON.

> Bei erkanntem Drift (z. B. "V2", abgekürzte Schuhnamen, falsche KW): **explizit korrigieren** und auf V3/Live-State zurückziehen.

---

## 3.5 Memory-Konsolidierung (T8 — autonom, sichtbar)

Beim Sync die episodischen Journal-Einträge ins Langzeit-Memory destillieren (claude.ai-artige Memory-Konsolidierung). Autonom + sichtbar (Diff zeigen), idempotent — nie still:
```bash
python3 lib/consolidate.py --target learnings  --as-of {heute}   # wiederkehrende Muster → learnings.md
python3 lib/consolidate.py --target baselines  --as-of {heute}   # neue PRs/Baselines → baselines.md
```
- Promotet NUR durable Erkenntnisse, dedupt gegen den Bestand (kein Re-Promote), patcht + uploadet `learnings.md`/`baselines.md` sichtbar (gemäß CLAUDE.md §0). Fehlt eine Datei → Pre-Seed-Hinweis, nicht blockieren.
- Nichts Neues im Journal → no-op (kein leerer Patch). Truth-Ordner + Personal-Module bleiben read-only.

---

## 4. Output (knapp)

```
🔄 SYNC KW[NN] — [Datum]
- Race: [Event] in [X] Tagen
- Live: [Gewicht] | KFA [%] | VFat [X] | HRV [XX ms Ampel] | VO2 [XX,X]
- Overrides: [Verletzung/Taper/Hitze/Gym-Pause/—]
- Protokoll: V3 ✅ | Persona: [Modus], Anrede [..]
- Fokus KW: [Haupt-Session] | Risiko: [..]
→ Operational. Was steht an, {Anrede}?
```

---

**Ende sync-skill v1.1.** Kurz, bestätigend, V3-verankert. Drift = sofort korrigieren.
> **v1.1:** Streak-Override entfernt (Geist-Wert, gemäß Medical-Notes im Athleten-Profil nicht getrackt).
