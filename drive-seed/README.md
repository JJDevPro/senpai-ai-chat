<!-- Dummy — echte Daten leben NUR in Drive. Dieses Verzeichnis enthält DATA-FREIE Templates. -->

# drive-seed/ — Seed-Kit für den privaten Drive-Ordner

**Zweck:** Der Service-Account hat **keine My-Drive-Quota** und kann daher Dateien
nur **aktualisieren (`files.update`), aber NICHT anlegen** (`create`). Senpai pflegt
den State also nur, wenn die Ziel-Dateien **bereits existieren** und **dir gehören**.
Dieses Verzeichnis liefert die fehlenden Platzhalter zum **einmaligen Vor-Seeden**:
lade jede Vorlage einmal selbst nach Drive (Drag-Drop), danach hält Senpai sie aktuell.

> **⛔ Service-Account-Constraint (update-only, no-create):** Lege jede dieser Dateien
> EINMAL selbst in Drive an (gleicher Dateiname). Fehlt eine Datei, bricht der
> jeweilige Skill mit einer PRE-SEED-Anweisung ab und legt sie NIE selbst an
> (siehe `lib/archive.py`).

> **⛔ Personal-Data-frei:** Alle Vorlagen hier enthalten nur `{{PLATZHALTER}}` und
> offensichtlich falsche Dummy-Werte (z. B. „Max Mustermann", 80.0 kg, „Musterstadt").
> Ersetze sie lokal/in Drive durch deine echten Werte. Die echten Daten leben
> **ausschließlich in Drive**, niemals im Repo.

> **Hinweis `data/`:** Der lokale Pull-Zielordner `data/` ist **gitignored**
> (siehe `.gitignore`) — gezogene Drive-Inhalte landen dort und werden nie committet.

## Mapping: Vorlage → Ziel-Ordner/Sheet → Upload

Alle IDs stammen aus `CLAUDE.md` (§0).

| Vorlage | Ziel-Ordner / Sheet | Drive-ID | Typ |
|---|---|---|---|
| `athlete.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | State |
| `live.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | State |
| `baselines.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | State |
| `learnings.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | State |
| `coaching_cues.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | State (Coaching-Schleife) |
| `senpai-journal.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | Journal |
| `readiness-history.csv` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | History |
| `Schlaf_HRV_Baseline.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | Personal-Modul |
| `Kraft-Programm.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | Personal-Modul |
| `Race_Strategie.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | Personal-Modul |
| `Schuhe_Ausruestung.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | Personal-Modul |
| `Historie.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | Personal-Modul |
| `Archiv_Historie.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | Personal-Modul |
| `Project_Index.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | Personal-Modul |
| `CHANGELOG.md` | Senpai-AI-Chat (privat) | `1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde` | Personal-Modul |

> Die read-only Truth-Ordner (HAE-JSON `1dnXIB0bAblSXmVKudhTq3SZw_Hc6MM6F`,
> `.fit` `1dpQUVeU3rjLFzA-xRANbC88RDV1JZwxf`, Trainings_v5- /
> Gesundheitsdaten_v5-Sheets) werden **nicht** geseedet — dort wird nie geschrieben.

## Upload-Schritte (einmalig)

1. **Werte ersetzen:** In jeder Vorlage alle `{{PLATZHALTER}}` und Dummy-Werte
   durch deine echten Daten ersetzen (lokale Kopie, NICHT im Repo committen).
2. **Hochladen:** Jede Datei per Drag-Drop in den Drive-Ordner **Senpai-AI-Chat**
   (`1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde`) legen — **gleicher Dateiname** wie hier.
3. **Verifizieren:** Session starten; der Session-Start-Pull
   (`python3 lib/pull_drive.py --folder 1OiTTKvxCn0fribZjvOBSXgCjRtzjHNde
   --match "athlete.md" --out ./data`) muss die Datei finden.
4. **Ab jetzt automatisch:** State-Dateien werden via
   `pull_drive.py --upload` (Drive `files.update`) zurückgeschrieben; das Journal
   wächst via `lib/archive.py`. Personal-Module bleiben read-only.

> Reihenfolge spielt keine Rolle — wichtig ist nur, dass **jede** benötigte Datei
> einmal existiert, bevor der zugehörige Skill/Write-Back läuft.
