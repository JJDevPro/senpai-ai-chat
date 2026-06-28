#!/usr/bin/env python3
"""
safety_gate.py — deterministisches V3-Sicherheits-Gate (daily-check + run-verdict)

WARUM dieses Skript existiert:
  CLAUDE.md §6 (SICHERHEITS-OVERRIDES) sind Prosa, die das Modell befolgen SOLL.
  Prosa ist nicht garantiert. Dieses Skript macht die kritischen Overrides zu einem
  HARTEN Gate, das IMMER feuert — der Verdict-Layer (Daily/Run) MUSS das Ergebnis
  respektieren. `training_allowed=false` ist nicht verhandelbar, egal was die Persona
  oder der LLM-Narrativ sagen wollen.

GATES (1:1 zu CLAUDE.md §6 + §5 HRV-Tabelle):

  1. HRV 🔴🔴  (CLAUDE.md §6: "Training STREICHEN, kein Verhandeln" / §5: <40 + Schlaf <6h)
       hrv_night.avg < 40  UND  heute_sleep.total_h < 6
       → level=CRITICAL, training_allowed=false. Höchste Priorität, übersteuert alles.

  2. HRV 🔴 sustained  (CLAUDE.md §5: "<50 (2+ Tage) → Deload-Woche")
       hrv_night.avg < 50. Einzeltag ist nur ein Flag; der 2-Tage-Kontext wird über
       --prev-hrv bestätigt. Bestätigt (prev_hrv < 50) → level=WARN + Intensitäts-Cap.
       Ohne Bestätigung → level=WATCH (nur Hinweis, Training erlaubt).

  3. VERLETZUNG  (CLAUDE.md §6: "Roast AUS, Medical Override")
       --injury → roast_allowed=false. training_allowed bleibt offen (Heilungs-
       Assessment entscheidet, siehe Schuhe_Ausruestung.md) → training_allowed=None.

  4. OPT-OUT  (CLAUDE.md §6: '"Stop"/"Neutral"/"Serious" → Persona aus')
       --opt-out → roast_allowed=false, neutraler Ton. Kein Trainings-Eingriff.

  5. AFib / kardiale Rhythmus-Marker  (CLAUDE.md §6 Sensor-/Medical-Override)
       BEWUSST NICHT gegated. AFib-Burden ist für diesen Athleten KEIN Trainings-
       Signal (nutzer-spezifische Ignore-Regel lebt in athlete.md). Dieses Skript
       liest oder bewertet AFib-Felder nie.

Mentale Krise (CLAUDE.md §6) ist nicht maschinell aus dem HAE-JSON ableitbar und
bleibt bewusst Prosa/Chat-Erkennung — kein Feld hier, um keine Diagnose zu erfinden.

CLI:  safety_gate.py <daily_json> [--injury] [--opt-out] [--prev-hrv N]
      <daily_json> = stdout von slice_hae_day.py (hat hrv_night.avg, heute_sleep.total_h)
      "-" liest von stdin.

Output (kompaktes JSON, NIE Roh-Arrays — §0):
  {gate, level, reasons[], training_allowed, roast_allowed}
    level            ∈ {CRITICAL, WARN, WATCH, OK}
    training_allowed ∈ {true, false, null}   null = Assessment nötig (Verletzung)
    roast_allowed    ∈ {true, false}
"""
import argparse
import json
import sys

HRV_CRITICAL = 40   # §5: 🔴🔴 unter diesem Wert (kombiniert mit Schlaf)
HRV_RED = 50        # §5: 🔴 unter diesem Wert (Deload bei 2+ Tagen)
SLEEP_CRITICAL_H = 6  # §5: Schlaf <6h als zweite Bedingung für 🔴🔴


def _get(d, *path):
    """Sicherer verschachtelter Lookup; gibt None bei fehlendem Pfad/None-Knoten."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def evaluate_gate(daily, injury=False, opt_out=False, prev_hrv=None):
    """Reine Funktion: Daily-Slice-Dict → Gate-Dict. Keine I/O, leicht testbar.

    Reihenfolge = Priorität: HRV🔴🔴 (CRITICAL) übersteuert alles andere beim Level,
    Medical/Opt-out-Flags wirken additiv auf roast_allowed.
    """
    reasons = []
    level = "OK"
    training_allowed = True
    roast_allowed = True

    hrv_avg = _get(daily, "hrv_night", "avg")
    sleep_h = _get(daily, "heute_sleep", "total_h")

    # --- Gate 1: HRV 🔴🔴 (CLAUDE.md §6 / §5) — höchste Priorität ---
    if hrv_avg is not None and sleep_h is not None and hrv_avg < HRV_CRITICAL and sleep_h < SLEEP_CRITICAL_H:
        level = "CRITICAL"
        training_allowed = False
        reasons.append(
            f"HRV 🔴🔴: hrv_night.avg {hrv_avg} < {HRV_CRITICAL} ms UND Schlaf {sleep_h}h < {SLEEP_CRITICAL_H}h "
            f"→ Training STREICHEN, kein Verhandeln (§6)."
        )
    else:
        # --- Gate 2: HRV 🔴 sustained (CLAUDE.md §5) ---
        if hrv_avg is not None and hrv_avg < HRV_RED:
            confirmed = prev_hrv is not None and prev_hrv < HRV_RED
            if confirmed:
                level = "WARN"
                reasons.append(
                    f"HRV 🔴 (2 Tage bestätigt): heute {hrv_avg} ms, gestern {prev_hrv} ms < {HRV_RED} "
                    f"→ Deload/Intensitäts-Cap (§5)."
                )
            else:
                level = "WATCH"
                reasons.append(
                    f"HRV 🔴 (Einzeltag): hrv_night.avg {hrv_avg} ms < {HRV_RED} — braucht 2-Tage-Kontext "
                    f"(--prev-hrv) zur Bestätigung. Heute beobachten, nicht eskalieren (§5)."
                )

    # --- Gate 3: Verletzung (CLAUDE.md §6 Medical Override) ---
    if injury:
        roast_allowed = False
        # Verletzung übersteuert ein „erlaubt" nicht zu hartem Ja — Assessment entscheidet.
        # Ein bereits CRITICAL-Streichen (training_allowed=False) bleibt bestehen.
        if training_allowed is not False:
            training_allowed = None
        reasons.append(
            "VERLETZUNG: Medical Override — Roast AUS, keine Intensitäts-/Volumen-Forderung. "
            "Trainings-Entscheidung erst nach Heilungs-Assessment (§6, Schuhe_Ausruestung.md)."
        )

    # --- Gate 4: Opt-out (CLAUDE.md §6) ---
    if opt_out:
        roast_allowed = False
        reasons.append("OPT-OUT: Persona aus, neutraler/sachlicher Ton (§6).")

    if not reasons:
        reasons.append("Keine Sicherheits-Overrides ausgelöst — V3 läuft normal.")

    return {
        "gate": "v3_safety",
        "level": level,
        "reasons": reasons,
        "training_allowed": training_allowed,
        "roast_allowed": roast_allowed,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministisches V3-Sicherheits-Gate (CLAUDE.md §6).")
    ap.add_argument("daily_json", help="slice_hae_day-Ausgabe (Datei oder '-' für stdin).")
    ap.add_argument("--injury", action="store_true", help="Verletzung gemeldet → Medical Override.")
    ap.add_argument("--opt-out", action="store_true", help="Opt-out → Persona aus, neutraler Ton.")
    ap.add_argument("--prev-hrv", type=float, default=None,
                    help="hrv_night.avg des Vortags — bestätigt HRV🔴 als 2-Tage-Muster.")
    args = ap.parse_args(argv)

    raw = sys.stdin.read() if args.daily_json == "-" else open(args.daily_json, encoding="utf-8").read()
    daily = json.loads(raw)

    gate = evaluate_gate(daily, injury=args.injury, opt_out=args.opt_out, prev_hrv=args.prev_hrv)
    print(json.dumps(gate, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
