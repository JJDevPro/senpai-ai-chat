---
description: Senpais proaktive Routinen (Briefing/Payload/Sync) via echtem VM-Cron armen/disarmen/anzeigen. Standardmäßig INAKTIV — der User armt nach der Testphase.
argument-hint: "[status | arm | disarm]"
---

# /automation — proaktive Routinen scharf schalten (in deiner Hand)

Du bist **Senpai** (CLAUDE.md). Dieser Command verwaltet die geplanten Routinen über das **echte
VM-Cron** (`CronCreate` / `CronList` / `CronDelete`) — die VM-Alternative zum manuellen iOS-UI-Schritt
(`docs/AUTOMATION.md`). **Default-Zustand: INAKTIV.** Es wird NIE automatisch gearmt; nur auf
ausdrücklichen `arm`.

`$ARGUMENTS` = `status` (Default), `arm`, oder `disarm`.

## `status` (Default)
`CronList` ausführen → die aktiven Senpai-Jobs zeigen. Keine aktiv → melde:
„🟡 Automation **inaktiv**. Wenn du nach der Testphase bereit bist (ob das VM-System claude.ai-Chat
vollwertig ersetzt) → `/automation arm`."

## `arm` (nur auf ausdrücklichen Wunsch)
Lege via `CronCreate` an (Zeitzone **Europe/Berlin**) — **vorher kurz rückfragen**, ob alle drei
oder nur das Briefing gewünscht ist:

| Job | Cron | Prompt |
|---|---|---|
| Morgen-Briefing | `0 10 * * *` | `/briefing` |
| KW-Abschluss | `0 20 * * 0` (So) | `/payload` |
| KW-Start-Sync | `0 7 * * 1` (Mo) | `/sync` |

Danach `CronList` zur Bestätigung + Hinweis: „🟢 Automation scharf. Disarm jederzeit via `/automation disarm`."

## `disarm`
Die Senpai-Jobs via `CronList` finden und mit `CronDelete` löschen. Bestätigen: „⚪ Automation aus."

---

**Kurz:** Default = nur anzeigen. `arm`/`disarm` schalten echtes Cron. **Bis der User `arm` sagt,
feuert nichts** — die Entscheidung bleibt bewusst beim User (Testphase zuerst).
