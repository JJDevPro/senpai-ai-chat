#!/usr/bin/env python3
"""pacing_card.py — race-day pacing card (markdown) for a target race.

WHY: turn a target race + (optional) Senpai race-readiness projection into a single,
honest, copy-pasteable pacing card: target finish band, per-km split table for an
EVEN and a NEGATIVE-SPLIT strategy, HR-zone guidance, start-discipline (KM1 not too
fast) and a heat note. Every number is labeled as a measured input or an assumption —
no VO2max magic.

INPUTS
  --race "B2Run"            event name (free text)
  --distance-km 6           race distance
  --readiness <path.json>   OPTIONAL: stats.py `race_readiness` JSON (reuses its
                            best/real/conservative band — single source of truth)
  --target-time MM:SS       OPTIONAL: explicit goal time (overrides readiness 'real')
  --temp-c 28               OPTIONAL: forecast temp for the heat note

PRIORITY for the target pace:  --target-time  >  readiness['projection']['real']  >
a transparent fallback (6 km ≈ 6:30/km is just a placeholder, clearly flagged).

API:   from pacing_card import build_card; card = build_card(...)
CLI:   python pacing_card.py --race "B2Run" --distance-km 6 --readiness rr.json
"""
from __future__ import annotations

import argparse
import json
import sys

# Start-discipline + negative-split swing as a fraction of average pace.
# KM1 is deliberately run SLOWER than average to bank discipline; the back half
# claws it back. swing = peak deviation at the two ends (sec/km), derived from avg.
_NEG_SWING_FRAC = 0.05      # ±5 % of avg pace across the race (linear ramp)
_FALLBACK_PACE_SEC = 390    # 6:30/km — placeholder only, loudly labeled


def parse_mmss(s: str) -> int:
    """'MM:SS' (or 'M:SS') → seconds."""
    parts = s.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"target-time must be MM:SS, got {s!r}")
    return int(parts[0]) * 60 + int(parts[1])


def fmt_mmss(total_sec: float) -> str:
    total = int(round(total_sec))
    return f"{total // 60}:{total % 60:02d}"


def _target_from_readiness(rr: dict, distance_km: float) -> tuple[int, dict]:
    """Pull the 'real' band finish (seconds) + the full band from a readiness JSON.

    Reuses stats.py race_readiness output verbatim:
      rr['projection'][name] = {pace_min_per_km, finish, finish_minutes, …}
    """
    proj = rr.get("projection", {})
    band = {}
    for name in ("best", "real", "conservative"):
        b = proj.get(name)
        if not b:
            continue
        if "finish_minutes" in b:
            total_sec = round(float(b["finish_minutes"]) * 60)
        else:
            total_sec = round(float(b["pace_min_per_km"]) * 60 * distance_km)
        band[name] = {"total_sec": total_sec,
                      "pace_sec": total_sec / distance_km,
                      "finish": fmt_mmss(total_sec)}
    real = band.get("real") or band.get("conservative") or next(iter(band.values()), None)
    if real is None:
        raise ValueError("readiness JSON has no usable projection band")
    return real["total_sec"], band


def _even_splits(total_sec: int, distance_km: float) -> list[dict]:
    avg = total_sec / distance_km
    return _segments(distance_km, lambda _frac: avg, total_sec)


def _neg_splits(total_sec: int, distance_km: float) -> list[dict]:
    """Negative-split paces: start (avg*(1+swing)) → finish (avg*(1-swing)), linear."""
    avg = total_sec / distance_km

    def pace_at(frac_mid: float) -> float:
        # frac_mid in [0,1]: position of segment midpoint along the race.
        return avg * (1 + _NEG_SWING_FRAC * (1 - 2 * frac_mid))

    return _segments(distance_km, pace_at, total_sec)


def _segments(distance_km: float, pace_fn, total_sec: int) -> list[dict]:
    """Build per-km segments (last one may be a partial km), pace from ``pace_fn``.

    Guarantees ``sum(split_sec) == total_sec`` exactly (integer) by absorbing all
    rounding into the final segment — so the table always adds up to the target.
    """
    n_full = int(distance_km)
    rem = round(distance_km - n_full, 3)
    lengths = [1.0] * n_full + ([rem] if rem > 1e-9 else [])
    if not lengths:                       # distance < 1 km
        lengths = [distance_km]
    # midpoint fraction of each segment for the pace ramp
    segs, cum_km = [], 0.0
    raw = []
    for ln in lengths:
        mid = (cum_km + ln / 2) / distance_km
        raw.append(pace_fn(mid) * ln)     # seconds for this segment
        cum_km += ln
    # scale to hit total exactly, then integer-round with last-segment absorption
    scale = total_sec / sum(raw)
    scaled = [r * scale for r in raw]
    out_sec = [int(round(x)) for x in scaled]
    out_sec[-1] += total_sec - sum(out_sec)   # force exact integer sum
    cum, start_km = 0, 0.0
    for ln, sec in zip(lengths, out_sec):
        cum += sec
        end_km = start_km + ln
        label = f"{int(end_km)}" if abs(ln - 1.0) < 1e-9 else f"{start_km:g}–{end_km:g}"
        segs.append({"km": label, "length_km": ln, "split_sec": sec,
                     "pace_sec": sec / ln, "cum_sec": cum})
        start_km = end_km
    return segs


def _hr_guidance(distance_km: float) -> list[tuple[str, str]]:
    """Effort/HR-zone guidance by race phase (assumption-labeled, % of race)."""
    return [
        ("KM 1 (Start-Disziplin)", "Z3 / unter Renn-HF — bewusst ~10–15 s/km LANGSAMER "
            "als Ziel. Adrenalin-Sprint = der #1 Pacing-Fehler."),
        ("Mittelteil", "Z4 — Ziel-Pace einrasten, gleichmäßig, Atmung kontrolliert "
            "(noch 2–3-Wort-Sätze möglich)."),
        ("Letzte ~1.5 km", "Z4→Z5 — kontrolliert öffnen, Negativ-Split einlösen. "
            "Redline erst auf den letzten ~600 m."),
    ]


def build_card(race: str, distance_km: float, readiness: dict | None = None,
               target_time: str | None = None, temp_c: float | None = None) -> dict:
    """Assemble the pacing card. Returns {markdown, even, neg, target_sec, band, …}."""
    band = None
    basis = None
    if target_time:
        total_sec = parse_mmss(target_time)
        basis = f"explizite Zielzeit {target_time}"
    elif readiness:
        total_sec, band = _target_from_readiness(readiness, distance_km)
        basis = "Senpai race_readiness ('real'-Band)"
    else:
        total_sec = round(_FALLBACK_PACE_SEC * distance_km)
        basis = f"FALLBACK-Platzhalter {fmt_mmss(_FALLBACK_PACE_SEC)}/km (KEINE Messung!)"

    even = _even_splits(total_sec, distance_km)
    neg = _neg_splits(total_sec, distance_km)
    md = _render_md(race, distance_km, total_sec, even, neg, band, basis, temp_c)
    return {"markdown": md, "target_sec": total_sec, "even": even, "neg": neg,
            "band": band, "basis": basis}


def _render_md(race, distance_km, total_sec, even, neg, band, basis, temp_c) -> str:
    avg = total_sec / distance_km
    L = []
    L.append(f"# 🏁 Pacing-Card — {race} ({distance_km:g} km)")
    L.append("")
    L.append(f"**Ziel-Finish:** `{fmt_mmss(total_sec)}`  ·  "
             f"**Ø-Pace:** `{fmt_mmss(avg)}/km`")
    L.append(f"<sub>Basis: {basis}</sub>")
    L.append("")
    if band:
        L.append("## Ziel-Band (race_readiness)")
        L.append("")
        L.append("| Szenario | Finish | Ø-Pace |")
        L.append("|---|---|---|")
        for name, lbl in (("best", "Best"), ("real", "Real"), ("conservative", "Konservativ")):
            b = band.get(name)
            if b:
                L.append(f"| {lbl} | `{b['finish']}` | `{fmt_mmss(b['pace_sec'])}/km` |")
        L.append("")
    L.append("## Split-Tabelle (Even vs. Negativ-Split)")
    L.append("")
    L.append("| KM | Even Pace | Even kum. | Neg-Split Pace | Neg kum. |")
    L.append("|---|---|---|---|---|")
    for e, n in zip(even, neg):
        L.append(f"| {e['km']} | `{fmt_mmss(e['pace_sec'])}` | `{fmt_mmss(e['cum_sec'])}` "
                 f"| `{fmt_mmss(n['pace_sec'])}` | `{fmt_mmss(n['cum_sec'])}` |")
    L.append(f"| **Σ** | | `{fmt_mmss(even[-1]['cum_sec'])}` | | "
             f"`{fmt_mmss(neg[-1]['cum_sec'])}` |")
    L.append("")
    L.append("**Empfehlung:** Negativ-Split — KM1 diszipliniert langsam, hintere Hälfte "
             "schneller. Sicherer gegen das Anfangs-Adrenalin, holt am Ende mehr raus.")
    L.append("")
    L.append("## HF-Zonen-Steuerung")
    L.append("")
    L.append("| Phase | Steuerung |")
    L.append("|---|---|")
    for phase, txt in _hr_guidance(distance_km):
        L.append(f"| {phase} | {txt} |")
    L.append("")
    L.append("## Start-Disziplin")
    L.append("")
    k1 = neg[0]
    L.append(f"- KM1 Ziel: `{fmt_mmss(k1['pace_sec'])}/km` — das ist BEWUSST "
             f"~{int(round(k1['pace_sec'] - avg))} s/km langsamer als Ø. "
             "Wer KM1 zu schnell läuft, bezahlt es ab KM4 doppelt.")
    L.append("- Die ersten 60 s im Pulk treiben lassen, nicht überholen wollen.")
    L.append("")
    L.append("## Hitze-Hinweis")
    L.append("")
    if temp_c is not None:
        if temp_c >= 25:
            L.append(f"- ⚠️ **{temp_c:g} °C** — Hitze-Penalty: Ziel-Pace realistisch "
                     "**+10–20 s/km** entschärfen, früh & oft trinken, Kopf kühlen. "
                     "Pace@HF schlägt Pace@Uhr bei Hitze.")
        elif temp_c >= 18:
            L.append(f"- **{temp_c:g} °C** — moderat warm: kleiner Penalty möglich "
                     "(+5–10 s/km), nach HF statt nach Uhr steuern.")
        else:
            L.append(f"- **{temp_c:g} °C** — angenehm, kein Hitze-Penalty erwartet.")
    else:
        L.append("- Keine Temperatur angegeben. Faustregel: ab ~25 °C nach HF statt "
                 "Pace steuern und das Finish-Band +10–20 s/km entschärfen.")
    L.append("")
    L.append("---")
    L.append("<sub>TRANSPARENTE Heuristik. Pace-Ramp = linearer ±5 %-Swing um die "
             "Ø-Pace; Splits summieren sich exakt zur Zielzeit. Kein VO2max-Modell — "
             "das Ziel-Band kommt aus den gelabelten Inputs oben.</sub>")
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(description="Race-day pacing card (markdown).")
    p.add_argument("--race", required=True, help="event name, e.g. 'B2Run'")
    p.add_argument("--distance-km", type=float, required=True, help="race distance in km")
    p.add_argument("--readiness", help="path to stats.py race_readiness JSON")
    p.add_argument("--target-time", help="explicit goal time MM:SS (overrides readiness)")
    p.add_argument("--temp-c", type=float, help="forecast temperature for the heat note")
    p.add_argument("--out", help="write markdown here instead of stdout")
    args = p.parse_args(argv)

    rr = None
    if args.readiness:
        rr = json.loads(open(args.readiness, encoding="utf-8").read())
    card = build_card(args.race, args.distance_km, readiness=rr,
                      target_time=args.target_time, temp_c=args.temp_c)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(card["markdown"])
        print(args.out, file=sys.stderr)
    else:
        print(card["markdown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
