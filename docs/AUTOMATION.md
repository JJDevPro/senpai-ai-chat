# AUTOMATION — Senpais geplantes Morgen-Briefing (Routine)

Einmalige Einrichtung, damit Senpai **proaktiv** jeden Morgen das `/briefing` fährt und
dir das Ergebnis aufs Handy schiebt — als **Claude-Code-on-the-web-Routine**. Danach läuft
es ohne dein Zutun: die Routine startet eine ephemere Cloud-VM, checkt den `senpai-ai-chat`-Repo
aus, führt `/briefing` aus (zieht HAE/Sheets aus Drive → Daily Check → `safety_gate` + `sentinel`)
und benachrichtigt dich, wenn sie fertig ist.

> **Wo:** Das ist ein **Web-UI-Schritt** in der **Claude-iOS-App / Claude Code on the web**
> (die `senpai-ai-chat`-Umgebung) — nicht im Repo, nicht in einer Datei. Du klickst die
> Routine im UI zusammen; dieses Dokument ist nur die Vorlage.

---

## 1. Die eine Routine, die du brauchst (10:00 täglich)

| Feld | Wert |
|---|---|
| **Cron** | `0 10 * * *`  → **jeden Tag 10:00** |
| **Environment** | `senpai-ai-chat` (der private Repo mit den Skills + `lib/pull_drive.py`) |
| **Prompt** | `/briefing` |

**Warum 10:00?** Die HAE-/HealthAutoExport-Dateien landen erst nach dem morgendlichen
**iPhone-Drive-Sync** in Drive. 10:00 gibt dem Sync sicher genug Vorlauf — die Routine zieht
dann frische Tagesdaten, nicht die von gestern. Früher = Risiko, auf veralteten Daten zu briefen
(`slice_hae_day` flaggt das zwar als `no_gestern_data`/`multi_day_range`, aber besser gar nicht erst).

**Prompt:** wörtlich nur

```
/briefing
```

`/briefing` (siehe `.claude/commands/briefing.md`) macht den Rest: State-Pull → Daily Check über
die `daily-check-skill` → `safety_gate` (autoritativ) + `sentinel` (Trip-Wires) → **führt mit den
Alerts, wenn `actionable=True`**, sonst normales Dashboard → Heute-Plan nach Wochentag.

---

## 2. Per-Wochentag: brauchst du mehrere Routinen?

**Inhalt pro Wochentag: NEIN — eine 10:00-Routine reicht.** Das `/briefing` leitet den Wochentag
selbst aus dem Claude-Kontext ab, und die `daily-check-skill` (§13/§14) passt Heute-Plan, Reminder
und das proaktive Wetterochs-Briefing automatisch an:

- **Mo** SoT-Wiegen + Run + Core/OK · **Di** Rest · **Mi** Long Run · **Do** 💀 Pure Gym ·
  **Fr** Rest · **Sa** Parkrun 09:00 + Partner · **So** Rest.

Eine einzige tägliche Routine deckt also alle sieben Tage inhaltlich ab.

**Mehrere Routinen brauchst du nur für unterschiedliche UHRZEITEN pro Tag** — z. B. wenn das
Briefing **vor** einem festen Termin liegen soll. Dann legst du **zusätzliche** Routinen mit
abweichendem Cron an (gleicher Prompt `/briefing`):

| Zweck | Cron | Bedeutung |
|---|---|---|
| Standard (Mo–So) | `0 10 * * *` | täglich 10:00 |
| **Samstag früher** (Parkrun 09:00 → Briefing davor) | `0 8 * * 6` | **Sa 08:00** |
| **Sonntag später** (Ausschlafen, KW-Abschluss/Payload) | `0 11 * * 0` | **So 11:00** |

> Cron-Wochentage: `0`/`7` = Sonntag, `6` = Samstag. Legst du die Sa-/So-Sonderzeiten an,
> **schränke die tägliche 10:00-Routine entsprechend ein** (z. B. `0 10 * * 1-5` = nur Mo–Fr),
> damit Sa/So nicht doppelt briefen.

---

## 3. Zustellung aufs Handy — kein ntfy nötig

Die **native Routine-Completion-Notification** von Claude Code on the web liefert das Ergebnis
direkt in die Claude-iOS-App: Routine läuft → Senpais Report ist die letzte Nachricht des Runs →
du bekommst die Fertig-Benachrichtigung und tippst dich in den vollen Report. **Kein ntfy, kein
Webhook, kein eigener Push-Kanal** — die Plattform übernimmt das. (Der frühere Pi-/ntfy-Umweg aus
dem Schwester-Repo entfällt hier komplett.)

---

## 4. Einrichten (UI, einmalig)

1. In der **Claude-iOS-App / Claude Code on the web** die **`senpai-ai-chat`-Umgebung** öffnen.
2. **Routine / Schedule** neu anlegen → Environment `senpai-ai-chat`, Cron `0 10 * * *`,
   Prompt `/briefing`.
3. Optional die Sa-/So-Sonderzeiten (§2) als **eigene** Routinen ergänzen und die tägliche auf
   `0 10 * * 1-5` einschränken.
4. Benachrichtigungen für die App erlauben → die Routine-Completion-Notification kommt aufs Handy.

Fertig. Ab dann begrüßt Senpai dich morgens von selbst — und meldet sich **scharf**, sobald ein
Trip-Wire feuert, statt brav zu warten, bis du fragst.

---

## 5. Bezug zum Code

| Teil | Wo |
|---|---|
| Briefing-Ablauf (Prompt-Template) | `.claude/commands/briefing.md` (`/briefing`) |
| Daily-Check-Workflow + Ampeln + Output | `.claude/skills/daily-check-skill/SKILL.md` |
| Autoritatives Safety-Gate (§6) | `.claude/skills/daily-check-skill/scripts/safety_gate.py` |
| Proaktive Trip-Wires (§5/§6) | `.claude/skills/daily-check-skill/scripts/sentinel.py` |
| Drive-Pull/-Push (Truth + State) | `lib/pull_drive.py` |

Alles deterministisch: nur **Aggregate + Verdict** erreichen den Modell-Kontext, nie Roh-Serien
(CLAUDE.md §0).

---

## 6. NEU (Claude-Code-VM): In-Repo-Cron via `/automation` — VORBEREITET, **INAKTIV**

Die Claude-Code-VM hat **echtes Scheduling** — kein UI-Klick nötig. Der `/automation`-Command
(`.claude/commands/automation.md`) armt/disarmt die Routinen direkt via `CronCreate`/`CronDelete`
und ersetzt den manuellen UI-Schritt aus §4 durch einen versionierten, reproduzierbaren Schalter.

> ⚠️ **Status: NICHT GEARMT.** Diese Automatik wird bewusst **inaktiv** ausgeliefert — erst ein paar
> Tage testen, ob das VM-System claude.ai-Chat vollwertig ersetzt, **dann selbst armen** (`/automation arm`).
> Bis dahin feuert nichts; das HUD zeigt „Automation: inaktiv".

**Geplanter Schedule (erst beim Armen angelegt):**

| Job | Cron (Europe/Berlin) | Prompt |
|---|---|---|
| Morgen-Briefing | `0 10 * * *` (tgl. 10:00) | `/briefing` |
| KW-Abschluss | `0 20 * * 0` (So 20:00) | `/payload` |
| KW-Start-Sync | `0 7 * * 1` (Mo 07:00) | `/sync` (inkl. Memory-Konsolidierung) |

- **HAE-Frische statt fixer-10:00-Rate:** `/briefing` macht jetzt einen **Frische-Vorcheck** (Datum-Alter,
  daily-check §3e) — bei stale Daten kurz warten/retrien statt blind auf eine „sichere" Uhrzeit zu
  vertrauen. Die 10:00 bleibt nur ein konservativer Default-Start.
- **Snapshot + Backlog laufen mit (kein eigener Cron):** `/briefing` regeneriert via daily-check den
  `trend_snapshot.md`-Woche+Monat-Rollup und schreibt/surft `backlog.md`; `/payload` versiegelt sonntags
  die Woche im Snapshot + räumt den Backlog; `/sync` reviewt offene Items. Ist das Briefing gearmt, wird
  der Trend-Snapshot + das Coaching-Backlog ohne expliziten Prompt gepflegt (CLAUDE.md §7/§11).
- **Disarm/Status:** `/automation disarm` löscht die Jobs; `/automation status` listet sie (`CronList`).
- Die **manuelle UI-Routine (§1–§4) bleibt** als Alternative gültig.
