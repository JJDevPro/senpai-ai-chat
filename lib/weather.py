#!/usr/bin/env python3
"""weather.py — präzise Stundenwerte (Bright Sky / DWD) für die Pre-Lauf-Engine.

Warum das existiert: Wetterochs ist exzellent fürs Narrativ, aber sein Delphi-JSON
liefert nur Tagesmin/-max — zu grob für die Slot-Starttemp und für die Bedingungen
WÄHREND eines Laufs (>1 h). Bright Sky (https://brightsky.dev) serviert die DWD-
Stundenwerte als JSON. Dieses Skript zieht sie deterministisch und REDUZIERT sie auf
ein kompaktes Slot-Fenster + Tages-Aggregat — nie das rohe 24-h-Array (CLAUDE.md §0).

Wetterochs bleibt die Narrativ-/Gewitter-/Fallback-Quelle (WebFetch im Skill);
hier kommen die harten Zahlen für die Lauf-Impact-Matrix.

PERSONAL-DATA-FREI: lat/lon werden als Args übergeben (aus `athlete.md` gespeist),
NICHT hier hardcodiert. tz-Default Europe/Berlin (wie lib/clock.py).

CLI:
  python3 lib/weather.py --lat 49.45 --lon 11.11 --date 2026-06-29 \
      --slot-start 20:00 --slot-end 22:00 [--tz Europe/Berlin]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE = "https://api.brightsky.dev/weather"
DEFAULT_TZ = os.environ.get("SENPAI_TZ", "Europe/Berlin")
# Felder, die wir je Stunde behalten (kompakt, lauf-relevant).
_HOURLY = ("temperature", "precipitation", "precipitation_probability",
           "wind_speed", "wind_gust_speed", "relative_humidity",
           "dew_point", "cloud_cover", "condition")


def _ssl_context() -> ssl.SSLContext:
    """SSL-Context, der die Agent-Proxy-CA respektiert, falls vorhanden."""
    ctx = ssl.create_default_context()
    for cand in (os.environ.get("SSL_CERT_FILE"), os.environ.get("REQUESTS_CA_BUNDLE"),
                 "/root/.ccr/ca-bundle.crt"):
        if cand and os.path.exists(cand):
            try:
                ctx.load_verify_locations(cand)
            except Exception:
                pass
    return ctx


def fetch(lat: float, lon: float, date: str, tz: str = DEFAULT_TZ) -> dict:
    """Bright-Sky-JSON für einen Tag ziehen (Proxy + CA aus der Umgebung)."""
    q = urllib.parse.urlencode({"lat": lat, "lon": lon, "date": date, "tz": tz})
    url = f"{BASE}?{q}"
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "senpai-ai-chat/weather"})
    with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def _num(x):
    return None if x is None else (round(float(x), 1) if isinstance(x, (int, float)) else x)


def _hhmm(ts: str) -> str | None:
    """ISO-Timestamp → 'HH:MM' (lokale Stunde, da tz schon serverseitig gesetzt)."""
    try:
        return datetime.fromisoformat(ts).strftime("%H:%M")
    except ValueError:
        return None


def _dew_band(dp) -> str | None:
    """Taupunkt-Band (Schwüle-Empfinden) — Skala aus dem Athleten-Profil."""
    if not isinstance(dp, (int, float)):
        return None
    if dp < 0:
        return "sehr trocken, angenehm"
    if dp < 10:
        return "trocken bis angenehm"
    if dp < 15:
        return "angenehm bis leicht feucht"
    if dp <= 20:
        return "schwül, unangenehm"
    return "sehr schwül, drückend"


def _sun_times(lat: float, lon: float, date_str: str, tz: str = DEFAULT_TZ) -> dict | None:
    """Sonnenauf-/-untergang (lokale HH:MM) via NOAA/Almanac-Formel — nur stdlib
    (astral/ephem sind nicht installiert). Wichtig für Nacht-Lauf/Stirnlampe."""
    try:
        y, m, d = (int(x) for x in date_str[:10].split("-"))
    except Exception:
        return None
    N = datetime(y, m, d).timetuple().tm_yday
    zenith = 90.833  # offizieller Sonnenstand inkl. Refraktion

    def _event(is_rise: bool):
        lng_hour = lon / 15.0
        t = N + ((6 if is_rise else 18) - lng_hour) / 24.0
        M = 0.9856 * t - 3.289
        L = (M + 1.916 * math.sin(math.radians(M))
             + 0.020 * math.sin(math.radians(2 * M)) + 282.634) % 360.0
        RA = math.degrees(math.atan(0.91764 * math.tan(math.radians(L)))) % 360.0
        RA += (math.floor(L / 90.0) * 90.0) - (math.floor(RA / 90.0) * 90.0)  # gleiche Quadrant wie L
        RA /= 15.0
        sin_dec = 0.39782 * math.sin(math.radians(L))
        cos_dec = math.cos(math.asin(sin_dec))
        cos_h = ((math.cos(math.radians(zenith)) - sin_dec * math.sin(math.radians(lat)))
                 / (cos_dec * math.cos(math.radians(lat))))
        if cos_h < -1 or cos_h > 1:
            return None  # Polartag/-nacht
        H = (360.0 - math.degrees(math.acos(cos_h))) if is_rise else math.degrees(math.acos(cos_h))
        H /= 15.0
        ut = (H + RA - 0.06571 * t - 6.622 - lng_hour) % 24.0
        dt = datetime(y, m, d, tzinfo=ZoneInfo("UTC")) + timedelta(hours=ut)
        return dt.astimezone(ZoneInfo(tz)).strftime("%H:%M")

    return {"sunrise": _event(True), "sunset": _event(False)}


def reduce(raw: dict, slot_start: str | None = None, slot_end: str | None = None,
           lat: float | None = None, lon: float | None = None,
           date: str | None = None, tz: str = DEFAULT_TZ) -> dict:
    """Roh-JSON → kompaktes Slot-Fenster + Tages-Aggregat. KEIN 24-h-Dump."""
    hours = raw.get("weather", []) or []
    temps = [h["temperature"] for h in hours if h.get("temperature") is not None]
    precs = [h["precipitation"] for h in hours if h.get("precipitation") is not None]
    probs = [h["precipitation_probability"] for h in hours
             if h.get("precipitation_probability") is not None]
    winds = [h["wind_speed"] for h in hours if h.get("wind_speed") is not None]

    # --- Asphalt-Schätzung (Heuristik, KEIN Messwert) -----------------------------
    # Belag speichert die Tages-Solarlast → bleibt abends wärmer als die Luft. Sonniger
    # Tag (viel sunshine, wenig cloud_cover) ⇒ höherer Aufschlag; bewölkt/Regen ⇒ ~0.
    # Datengetrieben aus Bright Sky solar/sunshine/cloud statt der pauschalen +3–5 °C.
    sun_min = [h["sunshine"] for h in hours if h.get("sunshine") is not None]
    clouds = [h["cloud_cover"] for h in hours if h.get("cloud_cover") is not None]
    day_sunshine_min = round(sum(sun_min)) if sun_min else None
    mean_cloud = round(sum(clouds) / len(clouds)) if clouds else None
    residual_c = min(5.0, round((day_sunshine_min or 0) / 120.0, 1))  # gespeicherte Tageshitze → Abend

    def _asphalt_excess(h):
        """+°C des Belags über Lufttemp: max(direkte Sonne jetzt, Tages-Residual).
        Aktiver Regen kühlt den Belag nass → Aufschlag fällt auf ~0."""
        solar = h.get("solar")
        now = round(min(20.0, solar * 16.0), 1) if isinstance(solar, (int, float)) else None
        cands = [x for x in (now, residual_c) if x is not None]
        ex = max(cands) if cands else None
        if ex is not None:
            rain = h.get("precipitation")
            if isinstance(rain, (int, float)) and rain > 0.2:
                ex = min(ex, 1.0)   # nasser Belag ≈ Lufttemp
        return ex

    def pack(h):
        t = _hhmm(h.get("timestamp", ""))
        entry = {"time": t, **{k: _num(h.get(k)) for k in _HOURLY}}
        air = h.get("temperature")
        ex = _asphalt_excess(h)
        if air is not None and ex is not None:
            entry["asphalt_excess_c_est"] = round(ex, 1)
            entry["asphalt_surface_c_est"] = round(float(air) + ex, 1)
        db = _dew_band(h.get("dew_point"))
        if db:
            entry["dew_point_band"] = db
        return entry

    # Slot-Fenster: Stunden in [floor(slot_start), slot_end]. Der Start wird auf
    # die VOLLE Stunde gefloort — ein 20:30-Start braucht die 20:00-Stunde als
    # Slot-Starttemp; der alte String-Vergleich verlor genau sie (Audit-CONFIRMED).
    window = []
    if slot_start and slot_end:
        floor_start = slot_start
        if len(slot_start) >= 4 and ":" in slot_start:
            floor_start = slot_start.split(":", 1)[0].zfill(2) + ":00"
        for h in hours:
            t = _hhmm(h.get("timestamp", ""))
            if t is not None and floor_start <= t <= slot_end:
                window.append(pack(h))

    day_summary = {
        "min_c": _num(min(temps)) if temps else None,
        "max_c": _num(max(temps)) if temps else None,
        "mean_c": _num(sum(temps) / len(temps)) if temps else None,
        "total_precip_mm": _num(sum(precs)) if precs else None,
        "max_precip_prob": _num(max(probs)) if probs else None,
        # Bright Sky liefert Wind in km/h — der alte Key "wind_max_ms" hat die
        # Einheit falsch etikettiert (Audit-CONFIRMED: Einheiten-Falle fürs LLM).
        "wind_max_kmh": _num(max(winds)) if winds else None,
        "day_sunshine_min": day_sunshine_min,
        "mean_cloud_cover": mean_cloud,
        "asphalt_residual_c_est": residual_c,
    }
    warnings = []
    if not hours:
        warnings.append("Bright Sky lieferte KEINE Stundenwerte für dieses Datum (Zukunft/zu fern?).")
    if (slot_start and slot_end) and not window:
        warnings.append(f"Keine Stunden im Slot {slot_start}-{slot_end} gefunden.")
    src = raw.get("sources", [])
    src_names = sorted({s.get("station_name") or s.get("dwd_station_id") or "?" for s in src})

    return {
        "source": "Bright Sky (DWD)",
        "stations": src_names,
        "slot": {"start": slot_start, "end": slot_end} if slot_start else None,
        "slot_window": window,
        "day_summary": day_summary,
        "sun": (_sun_times(lat, lon, date, tz) if (lat is not None and lon is not None and date) else None),
        "estimates_note": "asphalt_*_est = Heuristik aus solar/sunshine/cloud_cover, KEIN Messwert.",
        "warnings": warnings,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Bright Sky / DWD Stundenwerte → kompaktes Slot-Fenster.")
    p.add_argument("--lat", type=float, required=True, help="Breitengrad (aus athlete.md, nicht hardcoden)")
    p.add_argument("--lon", type=float, required=True, help="Längengrad (aus athlete.md)")
    p.add_argument("--date", required=True, help="Zieltag YYYY-MM-DD")
    p.add_argument("--slot-start", dest="slot_start", help="Lauf-Start HH:MM (lokal)")
    p.add_argument("--slot-end", dest="slot_end", help="Lauf-Ende HH:MM (lokal)")
    p.add_argument("--tz", default=DEFAULT_TZ, help=f"IANA-TZ (default {DEFAULT_TZ})")
    args = p.parse_args(argv)
    try:
        raw = fetch(args.lat, args.lon, args.date, args.tz)
    except Exception as e:  # Netz/TLS/Proxy → ehrlich melden, Skill fällt auf Wetterochs zurück
        print(json.dumps({"source": "Bright Sky (DWD)", "error": str(e),
                          "warnings": ["Fetch fehlgeschlagen → Wetterochs-Fallback nutzen."]},
                         ensure_ascii=False, indent=2))
        return 1
    out = reduce(raw, args.slot_start, args.slot_end,
                 lat=args.lat, lon=args.lon, date=args.date, tz=args.tz)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
