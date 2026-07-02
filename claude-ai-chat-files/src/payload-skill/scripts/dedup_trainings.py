#!/usr/bin/env python3
"""
dedup_trainings.py — Trainings_v5 Dedup-Helper (Daily-Check-Skill v0.7+)

ZWECK
-----
`Trainings_v5` enthält durch einen mehrfach schreibenden Sync doppelte
Session-Zeilen (z.B. HM 4x, Di-Lauf 2x). Über solche Duplikate gerechnet,
explodiert die ATL (z.B. 122 statt 42) und verfälscht CTL/TSB komplett.
Dieser Helper dedupliziert DETERMINISTISCH **vor** der Banister-Rechnung und
gibt einen Report aus, den der Skill 1:1 als Sheet-Hygiene-Warnung zeigt.

DESIGN
------
- Format-tolerant: nimmt das, was `read_file_content` liefert (CSV/TSV/
  Markdown-Tabelle/Whitespace) ODER ein JSON-Tool-Result, das den Text in
  einem 'content'/'text'/'body'-Feld trägt.
- Konservativ: dedupliziert auf einen SESSION-KEY aus den vorhandenen
  identifizierenden Spalten (Datum + Typ + TRIMP + Distanz). Findet keine
  solchen Spalten → Fallback = exakte Voll-Zeilen-Duplikate (sicherster Modus,
  merged NIE zwei echte verschiedene Sessions).
- Behält IMMER die erste Vorkommnis jeder Session, zählt die entfernten.
- Verändert NICHTS am Sheet (read-only): liefert nur die bereinigte Zeilenmenge
  + Report. Quelle wird separat vom Athleten aufgeräumt.

CLI
---
    python dedup_trainings.py <datei>        # Datei = read_file_content-Output
    cat result.json | python dedup_trainings.py -   # stdin

Programmatisch:
    from dedup_trainings import dedup
    clean_rows, report = dedup(raw_text)
"""

import sys, re, json, csv, io, hashlib
from collections import Counter

# Spalten-Namen (lowercase-Substrings), die als Identifikatoren taugen.
DATE_HINTS = ("datum", "date", "tag", "day")
TYPE_HINTS = ("typ", "type", "session", "aktivit", "activity", "sport", "workout")
TRIMP_HINTS = ("trimp", "load", "belastung")
DIST_HINTS = ("dist", "km", "strecke")


def _unwrap(raw: str) -> str:
    """Falls der Input ein JSON-Tool-Result ist, hol das Text-Feld raus."""
    s = raw.strip()
    if not s:
        return ""
    if s[0] in "{[":
        try:
            obj = json.loads(s)
        except Exception:
            return raw
        # Tiefer Griff nach dem ersten string-wertigen content/text/body/result
        def find_text(o):
            if isinstance(o, str):
                return o if ("\n" in o or "," in o or "\t" in o or "|" in o) else None
            if isinstance(o, dict):
                for k in ("content", "text", "body", "result", "data", "value"):
                    if k in o:
                        t = find_text(o[k])
                        if t:
                            return t
                for v in o.values():
                    t = find_text(v)
                    if t:
                        return t
            if isinstance(o, list):
                for v in o:
                    t = find_text(v)
                    if t:
                        return t
            return None
        return find_text(obj) or raw
    return raw


def _split_md_table(lines):
    """Markdown-Pipe-Tabelle → Liste[Liste[str]] (Trenn-Zeile entfernt)."""
    rows = []
    for ln in lines:
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        # Trennzeile (---|---) überspringen
        if cells and all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
            continue
        rows.append(cells)
    return rows


def _parse(text: str):
    """Liefert (header:list|None, rows:list[list[str]])."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text:
        return None, []
    lines = [l for l in text.split("\n") if l.strip() != ""]

    # Markdown-Tabelle?
    pipe_lines = [l for l in lines if l.count("|") >= 2]
    if len(pipe_lines) >= 2 and len(pipe_lines) >= 0.6 * len(lines):
        rows = _split_md_table(lines)
        if rows:
            return rows[0], rows[1:]

    # CSV/TSV via Sniffer
    sample = "\n".join(lines[:20])
    delim = None
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except Exception:
        for cand in ("\t", ";", ","):
            if cand in lines[0]:
                delim = cand
                break
    if delim:
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        rows = [r for r in reader if any(c.strip() for c in r)]
        if rows:
            return rows[0], rows[1:]

    # Fallback: jede Zeile = eine "Spalte"
    return None, [[l] for l in lines]


def _col_index(header, hints):
    if not header:
        return None
    for i, h in enumerate(header):
        hl = (h or "").strip().lower()
        if any(hint in hl for hint in hints):
            return i
    return None


def _norm(cell: str) -> str:
    return re.sub(r"\s+", " ", (cell or "").strip().lower())


# Datums-Formate (Mirror von banister._DATE_FORMATS) — nur zum Noise-Test.
_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d.%m.%y",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M",
)


def _date_ok(cell) -> bool:
    """True, wenn die Zelle als Datum parsebar ist (gleiche Logik wie banister)."""
    import datetime as _dt
    s = str(cell or "").strip()
    if not s:
        return False
    head = s.split()[0].split("T")[0] if (" " in s or "T" in s) else s
    for cand in (s, head):
        for fmt in _DATE_FORMATS:
            try:
                _dt.datetime.strptime(cand, fmt)
                return True
            except ValueError:
                continue
    return False


def _num(cell, decimals):
    """Parst eine (ggf. deutsche) Dezimalzahl wie banister._to_float + Rundung.
    Liefert float (gerundet) oder None. So kollabieren 489,23 und 489 auf denselben Key."""
    if cell is None:
        return None
    try:
        v = float(str(cell).replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None
    return round(v, decimals)


def dedup(raw: str):
    """
    Dedupliziert Trainings-Zeilen.
    Rückgabe: (clean_rows, report_dict)
    """
    text = _unwrap(raw)
    header, rows = _parse(text)
    total = len(rows)

    # Key-Spalten bestimmen
    idx_date = _col_index(header, DATE_HINTS)
    idx_type = _col_index(header, TYPE_HINTS)
    idx_trimp = _col_index(header, TRIMP_HINTS)
    idx_dist = _col_index(header, DIST_HINTS)
    key_cols = [i for i in (idx_date, idx_type, idx_trimp, idx_dist) if i is not None]

    # (1) Header-Schema-Assertion: Datum + TRIMP MÜSSEN erkannt sein (Strecke optional).
    # Fehlen sie, ist das fast immer ein falscher Tab/Export → laute Warnung.
    schema_warning = None
    if header is None:
        schema_warning = (
            "Kein Header erkannt — Fallback auf exakte Voll-Zeilen-Dedup. "
            "Datum-/TRIMP-Spalten unbekannt, Noise/Session-Key nicht prüfbar."
        )
    else:
        missing = []
        if idx_date is None:
            missing.append("Datum")
        if idx_trimp is None:
            missing.append("TRIMP")
        if missing:
            schema_warning = (
                f"Header-Schema unvollständig: {'/'.join(missing)}-Spalte nicht erkannt "
                f"(falscher Tab/Export?). Erkannter Header: {header}"
            )

    # (3) Noise-Erkennung nur möglich, wenn Datum UND TRIMP als Spalten existieren.
    detect_noise = idx_date is not None and idx_trimp is not None

    def is_noise(r):
        """Strukturelles Rauschen: Zeile ohne parsebares (Datum UND TRIMP)."""
        d_ok = idx_date < len(r) and _date_ok(r[idx_date])
        t_ok = idx_trimp < len(r) and _num(r[idx_trimp], 0) is not None
        return not (d_ok and t_ok)

    def row_key(r):
        if not key_cols:
            # Fallback: exakte Voll-Zeile
            return hashlib.md5("\x1f".join(_norm(c) for c in r).encode()).hexdigest()
        # (2) Numerische Key-Felder normalisieren: TRIMP→0, Strecke→2 Dezimalen.
        parts = []
        for i in key_cols:
            cell = r[i] if i < len(r) else ""
            if i == idx_trimp:
                v = _num(cell, 0)
                parts.append(f"trimp={v:.0f}" if v is not None else _norm(cell))
            elif i == idx_dist:
                v = _num(cell, 2)
                parts.append(f"dist={v:.2f}" if v is not None else _norm(cell))
            else:
                parts.append(_norm(cell))
        return tuple(parts)

    seen = {}
    clean = []
    dup_counter = Counter()
    noise_rows = 0
    for r in rows:
        # (3) Noise VOR der Dup-Zählung aussortieren — nie als "Duplikat" zählen.
        if detect_noise and is_noise(r):
            noise_rows += 1
            continue
        k = row_key(r)
        if k in seen:
            dup_counter[k] += 1
            continue
        seen[k] = True
        clean.append(r)

    nutzdaten = total - noise_rows  # Zeilen mit verwertbarem Datum+TRIMP
    removed = nutzdaten - len(clean)  # ECHTE Session-Duplikate (ohne Noise)
    mode = "session-key (" + "+".join(
        n for n, i in [("Datum", idx_date), ("Typ", idx_type),
                       ("TRIMP", idx_trimp), ("Distanz", idx_dist)] if i is not None
    ) + ")" if key_cols else "exakte-Voll-Zeile (Fallback, keine Key-Spalten erkannt)"

    # Top-Duplikate für den Report (max 5)
    top = []
    for k, extra in dup_counter.most_common(5):
        if key_cols:
            label = " · ".join(p for p in k if p)
        else:
            label = "(identische Zeile)"
        top.append({"session": label, "kopien": extra + 1})

    report = {
        "zeilen_gesamt": total,
        "zeilen_nutzdaten": nutzdaten,
        "zeilen_eindeutig": len(clean),
        "duplikate_entfernt": removed,
        "noise_rows": noise_rows,
        "schema_warning": schema_warning,
        "dedup_modus": mode,
        "top_duplikate": top,
        "header": header,
    }
    return clean, report


def format_warning(report: dict) -> str:
    """Copy-paste-fertige Sheet-Hygiene-Warnung für den Skill-Output."""
    alarms = []
    if report.get("schema_warning"):
        alarms.append(
            f"🛑 **Schema-Alarm:** {report['schema_warning']} "
            "→ CTL/ATL/TSB evtl. NICHT vertrauenswürdig (Read-Layer prüfen)."
        )
    if report.get("noise_rows"):
        alarms.append(
            f"🔍 **Read-Layer:** {report['noise_rows']} Struktur-/Noise-Zeile(n) "
            f"(kein gültiges Datum+TRIMP) verworfen — NICHT als Duplikate gezählt "
            f"({report['zeilen_gesamt']} roh → {report.get('zeilen_nutzdaten', '?')} Nutzdaten)."
        )
    if report["duplikate_entfernt"] == 0:
        base = "🟢 Trainings_v5 sauber — keine Session-Duplikate (CTL/ATL/TSB unverfälscht)."
        return "\n".join(alarms + [base]) if alarms else base
    lines = alarms + [
        f"⚠️ **Sheet-Hygiene:** {report['duplikate_entfernt']} doppelte Zeile(n) in "
        f"`Trainings_v5` entfernt **vor** der CTL/ATL/TSB-Rechnung "
        f"({report['zeilen_gesamt']} → {report['zeilen_eindeutig']}). "
        f"Dedup-Modus: {report['dedup_modus']}.",
    ]
    for d in report["top_duplikate"]:
        lines.append(f"   - {d['session']}: {d['kopien']}× gebucht")
    lines.append(
        "   → Ohne Dedup hätte die ATL überhöht gerechnet. **Quelle aufräumen:** "
        "Doppelzeilen im Sheet löschen + prüfen, warum der Sync mehrfach schreibt."
    )
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    raw = sys.stdin.read() if src == "-" else open(src, encoding="utf-8", errors="replace").read()
    clean, report = dedup(raw)
    print("=== DEDUP-REPORT ===")
    print(json.dumps({k: v for k, v in report.items() if k != "header"},
                     ensure_ascii=False, indent=2))
    print("\n=== WARNUNG (für Skill-Output) ===")
    print(format_warning(report))
    print(f"\n=== {len(clean)} eindeutige Zeilen bereit für Banister-Rechnung ===")


if __name__ == "__main__":
    main()
