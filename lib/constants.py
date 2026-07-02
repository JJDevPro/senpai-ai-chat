"""Kanonische Konstanten-Registry (SSoT) — Senpai v10.

JEDE Schwelle/Ampel-Grenze, die in mehr als einer Datei vorkommt, hat hier ihr
einziges Zuhause. Skripte definieren ihre lokalen Konstanten weiterhin selbst
(sie bleiben standalone aufrufbar), aber `tests/test_threshold_consistency.py`
erzwingt, dass Skript-Konstanten UND Doku-Prosa mit DIESER Datei uebereinstimmen.
Eine Schwelle aendern = HIER aendern, dann Skripte+Doku nachziehen, sonst ist
die Suite rot.

Herkunft der Werte: CLAUDE.md §4/§5, modules/V3_Protocol.md, nutrition-skill §2,
daily-check-skill §7/§8, run-bundle-skill §11. Entscheidungen 2026-07-02
(Q&A-Runden 1-3): TRIMP-Ampel = daily-check-Variante; Hitze-Tax fix 3,5;
Fett = Tagestyp-Cap + 85-g-Gate; Bedtime zweistufig; SoT-Wiegetag Montag.

DATA-FREE: enthaelt ausschliesslich generische Methode — keine Personendaten.
"""

# ── HR-Zonen (CLAUDE.md §4, V3_Protocol) ─────────────────────────────────────
# Z1 <136 · Z2 136–147 (ZIEL Easy/Long) · Z3 148–159 · Z4 160–171 · Z5 ≥172
HR_Z2_LOW = 136
HR_Z2_CAP = 147          # Die-Eine-Regel: Easy/Long-Decke
HR_Z3_MAX = 159
HR_Z4_MAX = 171          # Z5 = ab HR_Z4_MAX + 1
HR_Z1_RECOVERY_CAP = 135  # Recovery Run ≤Z1

# ── HRV (Safety-kritisch, CLAUDE.md §5/§6) ───────────────────────────────────
HRV_GREEN = 60            # 🟢 ≥60
HRV_RED = 50              # 🔴 <50 (2+ Tage → Deload); 🟡-Anzeigeband = 50–59
HRV_CRITICAL = 40         # 🔴🔴 <40 + Schlaf <6h → Training STREICHEN
SLEEP_CRITICAL_H = 6

# ── VO2max-Ampel (persoenlich-relativ, CLAUDE.md §5) ─────────────────────────
VO2_GREEN = 35.0          # 🟢 ≥35,0
VO2_YELLOW_LOW = 33.0     # 🟡 33,0–34,9 · 🔴 <33,0

# ── Atemstoerungen /h (CLAUDE.md §5; geteilt sentinel/body_battery) ──────────
BREATHING_GREEN = 10      # 🟢 ≤10
BREATHING_YELLOW = 12     # 🟡 >10–12
BREATHING_ORANGE = 15     # 🟠 >12–15 · 🔴 >15

# ── TRIMP-Ampel Einzelsession (kanonisch = daily-check-Variante) ─────────────
TRIMP_GREEN_MAX = 100     # 🟢 <100
TRIMP_YELLOW_MAX = 150    # 🟡 100–150
TRIMP_ORANGE_MAX = 180    # 🟠 150–180 · 🔴 >180

# ── TSB-Ampel (banister.tsb_ampel) ───────────────────────────────────────────
TSB_GREEN_MIN = 5         # 🟢 >5
TSB_YELLOW_MIN = -10      # 🟡 ≥−10
TSB_ORANGE_MIN = -30      # 🟠 ≥−30 · 🔴 <−30

# ── Hitze-Tax (V3, Entscheidung 2026-07-02: EIN Rechenwert ueberall) ─────────
HEAT_TAX_S_PER_C = 3.5    # s/km je °C ueber Baseline (Kalibrier-Band 3–4 dokumentiert)
HEAT_BASELINE_C = 18.0

# ── Walking-Filter v3.5 (Kadenz-primaer) ─────────────────────────────────────
WALK_CAD = 140            # Kadenz×2 < 140 spm UND
WALK_SPD = 2.0            # Speed < 2,0 m/s → Gehpause

# ── Z2-Laufform-Targets (V3_Protocol, CLAUDE.md §4) ──────────────────────────
CADENCE_Z2_TARGET = 166   # spm, Z2-Ziel
CADENCE_FLOOR = 160       # nie darunter (Gelenkschutz)
GCT_Z2_MAX_MS = 280
STRIDE_Z2_MIN_MM = 710
VO_Z2_RANGE_MM = (85, 92)
VR_TARGET_PCT = 11.0      # aktives Ziel: <11 %
VR_WARN_PCT = 12.0        # >12 % = Bouncing-Warnsignal

# ── Bedtime (zweistufig, Entscheidung 2026-07-02) ────────────────────────────
# 🟢 ≤00:00 (zaehlt voll) · 🟡 00:00–00:30 (zaehlt halb) · ❌ >00:30
BEDTIME_FULL_CUTOFF_MIN = 0     # Minuten nach Mitternacht
BEDTIME_HALF_CUTOFF_MIN = 30
BEDTIME_HALF_WEIGHT = 0.5

# ── Makros (nutrition-skill §2; Ampel-Referenz = Tagestyp-Cap) ───────────────
PROTEIN_FLOOR_G = 150     # 🟢 ≥150 · 🟡 135–149 · 🟠 105–134 · 🔴 <105
PROTEIN_YELLOW_MIN = 135
PROTEIN_ORANGE_MIN = 105
CAP_YELLOW_PCT = 10       # kcal/Carbs/Fett: 🟢 ≤Cap · 🟡 ≤+10 % · 🟠 +11–30 % · 🔴 >+30 %
CAP_ORANGE_PCT = 30
FAT_HARD_CAP_G = 85       # absolutes 🔴-Gate ZUSAETZLICH zum Tagestyp-Cap
REVERSE_RECOMP_DAYS = 5   # Einzeltag <Floor ≠ Reverse-Recomp (erst 5+ Tage in Folge)
# Tagestyp-Caps: (kcal, carbs_g, fett_g) — Protein-Floor gilt jeden Tag
DAY_CAPS = {
    "Mo": (2700, 377, 56), "Sa": (2700, 377, 56),
    "Di": (2000, 245, 36), "Fr": (2000, 245, 36), "So": (2000, 245, 36),
    "Mi": (2800, 411, 61),
    "Do": (2300, 302, 45),
}

# ── Schlaf-Ampeln (daily-check §8; daily_signals Effizienz) ──────────────────
SLEEP_TOTAL_GREEN_H = 7.0
SLEEP_TOTAL_YELLOW_H = 6.0
DEEP_GREEN_PCT = 15
DEEP_YELLOW_PCT = 10
REM_GREEN_PCT = 20
REM_YELLOW_PCT = 15
EFFICIENCY_GREEN = 90
EFFICIENCY_YELLOW = 85
EFFICIENCY_ORANGE = 75

# ── SoT-Protokoll (Entscheidung 2026-07-02) ──────────────────────────────────
# Koerperwaage-SoT: MONTAG, nuechtern nach dem Aufstehen (Richtwert ≤09:00,
# KEIN hartes Gate). Sonntag-Payload referenziert den letzten Mo-Wert.
SOT_WEEKDAY = "Mo"

# ── ACWR / Running Tolerance (running_tolerance.py) ──────────────────────────
ACWR_LOW = 0.8
RAMP_MAX = 1.3
