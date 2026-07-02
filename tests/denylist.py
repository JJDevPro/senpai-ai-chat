"""Gesaltete Identitäts-Denylist (PR-7, Entscheidung #9: Privacy strikt).

Die verbotenen Identitäts-Tokens stehen NICHT mehr im Klartext im Repo —
nur ihre gesalteten SHA-256-Hashes. Ein Text gilt als Leak, wenn eines
seiner (lowercase-)Wörter auf einen Denylist-Hash matcht. So kann der
Scanner auch `tests/` selbst prüfen, ohne dass die Testdatei die Namen trägt.

Einen neuen Token aufnehmen:
    python3 -c "import hashlib; print(hashlib.sha256(('senpai-v10-denylist|'+'<token>').encode()).hexdigest())"
"""

import hashlib
import re

_SALT = "senpai-v10-denylist|"

# sha256(salt + token_lowercase) — Namen/E-Mail-Localpart/Bezugsperson/
# Heimatstadt/Heim-Strecke. Klartext existiert bewusst nirgends im Repo.
DENYLIST_HASHES = frozenset({
    "e8c413fbd5d0639cf7ec52c34a963eb6df9aa8dfab8b336ee90fe8f7e9c7202d",
    "16ecbd90c3f310c76416635ce4a027e6724bb56b71e05a2c4b39b3d36e6e87eb",
    "3bba8905a8c8289e0b4d8fbbe0bfa8f7175b5e760b5bda9143a03ea3a933e0aa",
    "0899c52d2fc3c42ea757f982dbb088db605f3ed53278d1f0584988fdf99181f3",
    "df4fe87239eeaa51ca0d116c7f810e3f0274e8bb70b1df5b7b63273edfa07e34",
    "d8180d68bfd4923a511adb944a1cc45577daed4b31cbf40bbfe99c7b7bd8a8b8",
    "228d36d567ef6e8642b27b36945413c8830743605dd636a2f7f87e08592e043b",
    "d0bd077cd6857aab69790d2d094b9d8c2704098f189448adc5df266bad001fe0",
})

_WORD = re.compile(r"[\wäöüßÄÖÜ]+", re.UNICODE)

# Heim-Koordinaten-Muster: ein 49.4x-Lat UND ein 11.0x/11.1x-Lon in derselben
# Zeile = Koordinaten-Leak der Heim-Gegend (einzeln zu viele False-Positives).
COORD_PAIR = re.compile(r"49\.4\d+.{0,80}11\.[01]\d+|11\.[01]\d+.{0,80}49\.4\d+")


def _h(word):
    return hashlib.sha256((_SALT + word).encode("utf-8")).hexdigest()


def denied_words(text):
    """Alle Wörter des Texts, deren Salted-Hash auf der Denylist steht."""
    seen, hits = set(), []
    for w in _WORD.findall(text or ""):
        lw = w.lower()
        if lw in seen:
            continue
        seen.add(lw)
        if _h(lw) in DENYLIST_HASHES:
            hits.append(w)
    return hits


def contains_denied(text):
    return bool(denied_words(text))
