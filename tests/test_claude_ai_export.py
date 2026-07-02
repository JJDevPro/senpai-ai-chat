"""Drift-Guard + Invarianten für den claude.ai-Twin-Export (v10.1.0).

Drei Jobs:
1. **Drift-Guard:** `export_claude_ai.py --check --skip-personal` muss clean sein —
   eine Skill-/Template-/CLAUDE.md-Änderung ohne Re-Export kann nicht mergen
   (pytest ist das Merge-Gate, der Repo hat bewusst keine CI).
2. **Enklaven-Pin:** die PII-Scanner-Ausnahme (`claude-ai-chat-files/`) ist exakt
   gepinnt und kann nie stillschweigend wachsen; der Exporter-Quellcode selbst
   (liegt AUSSERHALB der Enklave) bleibt PII-frei.
3. **Determinismus:** Doppellauf → byte-identische Zips (Zip-Metadaten fixiert).

Alles data-free: Build läuft mit --skip-personal (Personal-Assets fließen per
Design nicht in den content_hash), keine Drive-/Netz-Zugriffe.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "lib"))

import export_rules  # noqa: E402
from denylist import denied_words  # noqa: E402

EXPORTER = REPO / "lib" / "export_claude_ai.py"
OUT = REPO / "claude-ai-chat-files"


def _run(*args, **kw):
    return subprocess.run([sys.executable, str(EXPORTER), *args],
                          cwd=REPO, capture_output=True, text=True, **kw)


# ---------------------------------------------------------------------------
# 1) Drift-Guard
# ---------------------------------------------------------------------------
def test_export_check_clean():
    r = _run("--check", "--skip-personal")
    assert r.returncode == 0, (
        "Export-Drift — Quellen und claude-ai-chat-files/ sind auseinander.\n"
        "Fix: python3 lib/export_claude_ai.py laufen lassen und committen.\n"
        + r.stdout + r.stderr
    )


def test_committed_output_structure():
    mf = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert set(mf["artifacts"]) == set(export_rules.SKILLS)
    for name in export_rules.SKILLS:
        assert (OUT / "dist" / f"{name}.skill").exists(), name
        assert (OUT / "src" / name / "SKILL.md").exists(), name
    for doc in ("project-instructions.md", "project-files.md", "smoke-tests.md",
                "README.md"):
        assert (OUT / doc).exists(), doc
    # Alt-Layout (Root-Zips) darf nicht wieder auftauchen
    assert not list(OUT.glob("*.skill")), "stale Root-.skill-Zips im Enklaven-Root"


def test_exported_skill_md_forbidden_tokens():
    """Unabhängige Zweitprüfung (der Exporter gated selbst, aber committete
    Dateien könnten von Hand angefasst worden sein)."""
    hits = []
    for name in export_rules.SKILLS:
        text = (OUT / "src" / name / "SKILL.md").read_text(encoding="utf-8")
        hits += [f"{name}:{n}: {tok!r}" for n, tok, _ in export_rules.forbidden_hits(text)]
    assert not hits, "Drive-/VM-Reste im committeten Export: " + ", ".join(hits)


# ---------------------------------------------------------------------------
# 2) Enklaven-Pin + Exporter-Hygiene
# ---------------------------------------------------------------------------
def test_pii_exception_exactly_pinned():
    sys.path.insert(0, str(REPO / "tests"))
    import test_no_personal_data as scanner
    assert set(scanner.EXCLUDE_PREFIXES) == {"data/", ".git/", "claude-ai-chat-files/"}, (
        "PII-Scanner-Ausnahmen verändert — das ist eine bewusste Entscheidung, "
        "kein Nebeneffekt (docs/CLAUDE_AI_EXPORT.md)."
    )


def test_exporter_sources_pii_free():
    sources = [EXPORTER, REPO / "lib" / "export_rules.py",
               *sorted((REPO / "lib" / "export_templates").glob("*.md"))]
    hits = []
    for p in sources:
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for w in denied_words(line):
                hits.append(f"{p.name}:{n}: {w}")
    assert not hits, "PII im Exporter-Quellcode (liegt AUSSERHALB der Enklave): " + str(hits)


def test_personal_assets_only_under_assets():
    for name, cfg in export_rules.SKILLS.items():
        for entry in cfg["assets"]:
            src, arc, personal = entry
            assert arc.startswith("assets/"), (name, arc)
            if personal:
                assert src.startswith("data/"), (name, src)


def test_descriptions_are_claude_ai_legal():
    for name, cfg in export_rules.SKILLS.items():
        d = cfg["description"]
        assert len(d) <= 200, (name, len(d))
        assert '"' not in d, name


# ---------------------------------------------------------------------------
# 3) Determinismus (Doppellauf → identische Bytes)
# ---------------------------------------------------------------------------
def test_double_build_is_byte_identical(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for target in (a, b):
        r = _run("--skip-personal", "--out", str(target))
        assert r.returncode == 0, r.stdout + r.stderr
    for za in sorted((a / "dist").glob("*.skill")):
        zb = b / "dist" / za.name
        assert za.read_bytes() == zb.read_bytes(), f"nicht deterministisch: {za.name}"
    assert ((a / "MANIFEST.json").read_text(encoding="utf-8")
            == (b / "MANIFEST.json").read_text(encoding="utf-8"))
