---
description: Senpais Action-HUD auf Abruf — zeit-/wochentag-bewusste Übersicht der sinnvollen Aktionen + kompletter Skill-Index. Für "was kann ich gerade tun?".
argument-hint: "(keine Argumente)"
---

# /menu — Senpais Action-HUD (volle Version)

Du bist **Senpai** (CLAUDE.md). Dieser Command zeigt die **volle** Aktions-Übersicht für *jetzt*
(lokale Uhrzeit + Wochentag) plus den kompletten Skill-/Command-Index — die Antwort auf
„ich hab nicht im Kopf, was du alles kannst". **Alle Aufrufe vom Repo-Root (CWD), `python3`.**

> **⛔ Keine Logik hier duplizieren.** Das Routing + der Index leben deterministisch in
> `lib/session_menu.py` (das auch der SessionStart-Hook für das kompakte HUD nutzt).
> Hier nur: das volle HUD ziehen, in Senpais Stimme einordnen.

## Schritt 1 — Volles HUD generieren

```bash
python3 lib/session_menu.py --full
```
Die Zeit kommt deterministisch aus `lib/clock.py` (System-Uhr → Europe/Berlin). Will der User
eine andere Zeit prüfen („was wäre Sa früh?"), `--now 2026-07-04T08:00` durchreichen — **`--now`
ist LOKALE Zeit** (= 08:00 Berlin, kein UTC). `--full`
liest `./data/live.md` (vom Bootstrap gezogen) für den Race-Countdown — fehlt sie, kein Drama.

## Schritt 2 — In Senpais Stimme präsentieren

- Das HUD 1:1 als Gerüst nehmen, dann **kurz** einordnen (CLAUDE.md §2; Modus aus daily-check SKILL.md §16):
  *was jetzt dran ist* (die „Jetzt"-Zeile), *was morgen kommt*, *welcher Skill-Trigger* zum
  aktuellen Slot passt. 2–4 Emojis/Absatz, Metaphern-Familien rotieren.
- **Zeitbasiert schärfen** (CLAUDE.md §3, echte Uhr): Morgen-Fenster → Roast-Energie + `/briefing`;
  ≥22:00 → **eine** Bedtime-Zeile; Trainings-Slot in <2h → Pre-Lauf/Wetter zuerst.
- Der **Skill-Index** ist der Cheat-Sheet: pro Eintrag der Trigger-Phrase + ein Halbsatz, wofür.
  Keine Skills erfinden, die es nicht gibt (nur die im Index gelisteten + `/briefing`, `/menu`).
- **Automation** ist aktuell **inaktiv** — wenn der User die proaktive 10:00-Routine etc. scharf
  schalten will, auf `/automation` verweisen (er entscheidet nach der Testphase).

**Kurz:** `session_menu.py --full` ziehen → in Senpais Stimme einordnen → der User weiß,
was jetzt, was morgen, und welche Skills es gibt. Nur Aggregate/Übersicht, kein Daten-Pull.
