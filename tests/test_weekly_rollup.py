"""weekly_rollup.py — skriptierte KW-Aggregation für den Payload (PR-6).

Pinnt: 4 Makro-Ampeln × Tage (Tagestyp-Caps + Protein-Floor + 85-g-Fett-Gate),
zweistufigen Bedtime-Score (00:00 voll / 00:30 halb), Schlaf-Ø, Δ vs Vor-KW aus
readiness-history und die Ehrlichkeit bei fehlenden Tagen (days_missing_hae).
DATA-FREE: synthetische HAE-Dateien + synthetische History. Test-KW: Mo
2026-06-22 … So 2026-06-28.
"""

import json

import weekly_rollup as WR


def _metric(name, units, points):
    return {"name": name, "units": units,
            "data": [{"date": d, "qty": q} for d, q in points]}


def _write_day(tmp_path, day, metrics):
    p = tmp_path / f"HealthAutoExport-{day}.json"
    p.write_text(json.dumps({"data": {"metrics": metrics}}), encoding="utf-8")
    return p


def _sleep_rec(start, end, total=7.0):
    return {"name": "sleep_analysis", "units": "hr",
            "data": [{"date": end, "sleepStart": start, "sleepEnd": end,
                      "totalSleep": total}]}


def _macro_day(day, protein, kcal, carbs, fat):
    return [
        _metric("protein", "g", [(f"{day} 12:00:00 +0200", protein)]),
        _metric("dietary_energy", "kcal", [(f"{day} 12:00:00 +0200", kcal)]),
        _metric("carbohydrates", "g", [(f"{day} 12:00:00 +0200", carbs)]),
        _metric("total_fat", "g", [(f"{day} 12:00:00 +0200", fat)]),
    ]


# ---------------------------------------------------------------- Bausteine
def test_week_days_iso_monday_to_sunday():
    days = WR._week_days("2026-06-28")            # Sonntag
    assert days[0].isoformat() == "2026-06-22" and days[-1].isoformat() == "2026-06-28"
    assert WR._week_days("2026-06-24") == days    # Mittwoch → gleiche KW


def test_bedtime_class_two_stage():
    assert WR._bedtime_class("2026-06-23 23:30:00 +0200") == "full"   # vor Mitternacht
    assert WR._bedtime_class("2026-06-24 00:00:00 +0200") == "full"
    assert WR._bedtime_class("2026-06-24 00:15:00 +0200") == "half"   # ≤00:30 zählt halb
    assert WR._bedtime_class("2026-06-24 00:45:00 +0200") == "miss"


def test_macro_ampeln_day_type_caps_and_hard_fat_gate(tmp_path):
    # Di (Cap 2000/245/36): sauber grün.
    _write_day(tmp_path, "2026-06-23", _macro_day("2026-06-23", 155, 1900, 200, 30))
    # Mi (Cap 2800/411/61): kcal +10 %-Band (🟡), Fett 90 g -> hartes 🔴-Gate (>85).
    _write_day(tmp_path, "2026-06-24", _macro_day("2026-06-24", 140, 3050, 300, 90))
    # Do (Cap 2300/302/45): Protein unter Orange-Floor (🔴), Rest grün.
    _write_day(tmp_path, "2026-06-25", _macro_day("2026-06-25", 100, 2200, 250, 40))
    days = WR._week_days("2026-06-28")
    merged, missing = WR._load_week(str(tmp_path), days)
    res = WR.macro_week(merged, days)
    assert res["n_logged"] == 3
    per = {d["day"]: d for d in res["per_day"] if d.get("logged")}
    assert per["2026-06-23"]["ampeln"] == {"protein": "🟢", "kcal": "🟢",
                                           "carbs": "🟢", "fat": "🟢"}
    assert per["2026-06-24"]["ampeln"]["kcal"] == "🟡"      # 3050 ≤ 2800*1.10
    assert per["2026-06-24"]["ampeln"]["fat"] == "🔴"       # 90 > 85 (Hard-Gate)
    assert per["2026-06-25"]["ampeln"]["protein"] == "🔴"   # 100 < 105
    assert res["all_green_days"] == 1
    assert res["counts"]["protein"]["🟢"] == 1 and res["counts"]["fat"]["🔴"] == 1
    # 4 fehlende Tage ehrlich gelistet (Gap-Check-Futter)
    assert len(missing) == 4 and "2026-06-28" in missing


def test_sleep_week_two_stage_score(tmp_path):
    _write_day(tmp_path, "2026-06-23", [
        _sleep_rec("2026-06-22 23:40:00 +0200", "2026-06-23 06:40:00 +0200", 7.0)])
    _write_day(tmp_path, "2026-06-24", [
        _sleep_rec("2026-06-24 00:20:00 +0200", "2026-06-24 06:20:00 +0200", 6.0)])
    _write_day(tmp_path, "2026-06-25", [
        _sleep_rec("2026-06-25 01:10:00 +0200", "2026-06-25 07:10:00 +0200", 6.0)])
    days = WR._week_days("2026-06-28")
    merged, _ = WR._load_week(str(tmp_path), days)
    res = WR.sleep_week(merged, days)
    assert res["n_nights"] == 3
    bt = res["bedtime"]
    assert bt["full_le_0000"] == 1 and bt["half_le_0030"] == 1 and bt["miss"] == 1
    assert bt["score"] == 1.5                                 # 1 + 0,5×1
    assert res["sleep_avg_h"] == 6.33


def test_history_delta_vs_prev_week(tmp_path):
    header = ("date,readiness_score,band,hrv_status,bb_start,bb_end,tsb,top_limiter,"
              "ctl,atl,hrv_ms,rhr,weight,kfa,vo2,week_km")
    rows = [header]
    for d, hrv in (("2026-06-16", 50), ("2026-06-17", 52),     # Vor-KW
                   ("2026-06-23", 60), ("2026-06-24", 62)):    # Ziel-KW
        rows.append(f"{d},70,moderate,balanced,,,,,,,{hrv},58,,,,")
    hist = tmp_path / "readiness-history.csv"
    hist.write_text("\n".join(rows) + "\n", encoding="utf-8")
    trend = WR.history_trend(str(hist), WR._week_days("2026-06-28"))
    assert trend["this_week"]["hrv_avg_ms"] == 61.0
    assert trend["prev_week"]["hrv_avg_ms"] == 51.0
    assert trend["delta"]["hrv_avg_ms"] == 10.0


def test_template_lines_render_counts_and_bedtime(tmp_path):
    _write_day(tmp_path, "2026-06-23", _macro_day("2026-06-23", 155, 1900, 200, 30)
               + [_sleep_rec("2026-06-22 23:40:00 +0200", "2026-06-23 06:40:00 +0200")])
    days = WR._week_days("2026-06-28")
    merged, _ = WR._load_week(str(tmp_path), days)
    macros = WR.macro_week(merged, days)
    sleep = WR.sleep_week(merged, days)
    trend = WR.history_trend(str(tmp_path / "missing.csv"), days)
    lines = WR.render_lines(macros, sleep, trend)
    assert any(l.startswith("- Protein 🟢1/") for l in lines)
    assert any("nur 1/7 Tage geloggt" in l for l in lines)     # Ehrlichkeits-Marker
    assert any("Bedtime-Score: 1/7" in l for l in lines)


def test_cli_end_to_end(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    _write_day(tmp_path, "2026-06-23", _macro_day("2026-06-23", 155, 1900, 200, 30))
    script = str(Path(__file__).resolve().parents[1] / ".claude" / "skills"
                 / "daily-check-skill" / "scripts" / "weekly_rollup.py")
    out = subprocess.run([sys.executable, script, "--as-of", "2026-06-28",
                          "--data-dir", str(tmp_path)],
                         capture_output=True, text=True, check=True)
    res = json.loads(out.stdout)
    assert res["ok"] is True and res["schema_version"] == "1.0"
    assert res["week"] == {"monday": "2026-06-22", "sunday": "2026-06-28", "iso_week": 26}
    assert len(res["days_missing_hae"]) == 6
    assert res["macros"]["n_logged"] == 1
