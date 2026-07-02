#!/usr/bin/env python3
"""export_claude_ai.py — deterministischer Generator des claude.ai-Twins.

Erzeugt `claude-ai-chat-files/` (Skill-Zips + Projekt-Anweisungen + Doku) aus
den SSoT-Quellen des Repos: `.claude/skills/*/SKILL.md` (mit cc-only/cai-only-
Markern), `lib/`, `modules/`, `CLAUDE.md` und den Templates/Regeln in
`lib/export_templates/` + `lib/export_rules.py`.

Transformation (3 Ebenen, siehe export_rules.py):
  Tier A  Marker:   <!-- cc-only:start/end --> raus · <!-- cai-only:start … --> rein
  Tier B  Rewrites: Skript-Pfade → bundle-relativ, Strava-MCP → Connector-Sprache
  Tier C  Generate: §0-CAI-Preamble, Kurz-Description (≤200), Footer-Stempel

Garantien:
  * Doppellauf → byte-identischer Output (feste Zip-Timestamps, sortierte Arcnames).
  * Jeder Drive-/VM-Rest im Transformat (FORBIDDEN_EXPORT_TOKENS) bricht den
    Export laut ab — neuer Drive-Zugriff ohne cai-Äquivalent KANN nicht exportieren.
  * Personal-Assets (Race-Strategie, GPX, Bright-Sky-URL) fließen NICHT in den
    content_hash → `--check --skip-personal` bleibt hermetisch/data-free.

CLI:
  python3 lib/export_claude_ai.py                    # Voll-Export nach claude-ai-chat-files/
  python3 lib/export_claude_ai.py --check            # Drift-Check gegen MANIFEST.json (exit 1 bei Drift)
  python3 lib/export_claude_ai.py --refresh-personal # Personal-Assets aus ./data neu einfrieren
  python3 lib/export_claude_ai.py --skip-personal    # Build ohne Personal-Assets (Tests/CI)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_rules as R  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "lib" / "export_templates"
DEFAULT_OUT = REPO / "claude-ai-chat-files"
TWIN_VERSION = "v10.1.0-CAI"
# Feste Zip-Metadaten → byte-identische Doppelläufe (Determinismus-Vertrag).
_ZIP_DATE = (2026, 1, 1, 0, 0, 0)

CC_START, CC_END = "<!-- cc-only:start -->", "<!-- cc-only:end -->"
CAI_START, CAI_END = "<!-- cai-only:start", "cai-only:end -->"


# ---------------------------------------------------------------------------
# Tier A — Marker
# ---------------------------------------------------------------------------
def transform_markers(text: str, origin: str) -> str:
    out: list[str] = []
    mode = None  # None | "cc" | "cai"
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s == CC_START:
            if mode:
                raise SystemExit(f"{origin}:{n}: verschachtelter Marker ({mode} offen)")
            mode = "cc"
        elif s == CC_END:
            if mode != "cc":
                raise SystemExit(f"{origin}:{n}: cc-only:end ohne offenen Block")
            mode = None
        elif s == CAI_START:
            if mode:
                raise SystemExit(f"{origin}:{n}: verschachtelter Marker ({mode} offen)")
            mode = "cai"
        elif s == CAI_END:
            if mode != "cai":
                raise SystemExit(f"{origin}:{n}: cai-only:end ohne offenen Block")
            mode = None
        elif mode == "cc":
            continue  # Repo-only-Zeile fällt weg
        else:
            out.append(line)  # normal ODER cai-Inhalt (roh emittiert)
    if mode:
        raise SystemExit(f"{origin}: Marker-Block '{mode}' nicht geschlossen")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Tier B — Rewrites + Forbidden-Gate
# ---------------------------------------------------------------------------
def apply_rewrites(text: str, rules) -> str:
    for pat, repl in rules:
        text = re.sub(pat, repl, text)
    return text


def assert_clean(text: str, origin: str) -> None:
    hits = [f"{origin}:{n}: {tok!r} → {line.strip()[:100]}"
            for n, tok, line in R.forbidden_hits(text)]
    if hits:
        raise SystemExit(
            "Export ABGEBROCHEN — Drive-/VM-Reste im Transformat (Marker fehlt "
            "oder Rewrite-Regel nötig):\n" + "\n".join(hits[:25])
        )


# ---------------------------------------------------------------------------
# SKILL.md-Assembly
# ---------------------------------------------------------------------------
def split_frontmatter(text: str, origin: str) -> tuple[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SystemExit(f"{origin}: kein YAML-Frontmatter gefunden")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:]) + "\n"
    raise SystemExit(f"{origin}: Frontmatter nicht geschlossen")


def build_skill_md(name: str) -> str:
    cfg = R.SKILLS[name]
    src = REPO / ".claude" / "skills" / name / "SKILL.md"
    fm, body = split_frontmatter(src.read_text(encoding="utf-8"), str(src))
    m = re.search(r"^name:\s*(\S+)", fm, re.M)
    if not m or m.group(1) != name:
        raise SystemExit(f"{src}: Frontmatter-name != {name}")

    body = transform_markers(body, str(src))
    body = apply_rewrites(body, R.rewrites_for(name))

    # Preamble nach der ersten H1 einschieben (Titel bleibt oben)
    pre = cfg["preamble"].rstrip() + "\n"
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines[i + 1:i + 1] = ["", pre, "---", ""]
            break
    else:
        lines[0:0] = [pre, "---", ""]
    body = "\n".join(lines).rstrip() + "\n"

    desc = cfg["description"]
    assert '"' not in desc, f"{name}: description enthält doppelte Anführungszeichen"
    text = f'---\nname: {name}\ndescription: "{desc}"\n---\n\n{body}'
    assert_clean(text, f"export:{name}/SKILL.md")
    return text


def skill_version(name: str) -> str:
    src = (REPO / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    # Version aus der H1-Titelzeile (die Frontmatter-Description erwähnt oft
    # ANDERE Versionen, z. B. "Walking-Filter v3.5") — Fallback: erster Treffer.
    h1 = re.search(r"^# .*?\bv(\d+\.\d+(?:\.\d+)?)\b", src, re.M)
    if h1:
        return f"v{h1.group(1)}"
    m = re.search(r"\bv(\d+\.\d+(?:\.\d+)?)\b", src[:4000])
    return f"v{m.group(1)}" if m else "v?"


def source_commit(paths: list[str]) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h", "--"] + paths,
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out or "uncommitted"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Personal-Assets (PII-Enklave — nur unter claude-ai-chat-files/src/*/assets/)
# ---------------------------------------------------------------------------
def gen_brightsky_url(refresh: bool) -> None:
    """data/brightsky_url.txt aus athlete.md erzeugen (senpai-export-Block oder
    Koordinaten-Anker). Existierende Datei bleibt ohne --refresh-personal stehen."""
    target = REPO / "data" / "brightsky_url.txt"
    if target.exists() and not refresh:
        return
    athlete = REPO / "data" / "athlete.md"
    if not athlete.exists():
        return  # Resolution fällt auf committete Kopie zurück
    text = athlete.read_text(encoding="utf-8")
    lat = lon = None
    yml = re.search(r"```senpai-export\s*(.*?)```", text, re.S)
    if yml:
        mlat = re.search(r"^\s*lat:\s*([0-9.]+)", yml.group(1), re.M)
        mlon = re.search(r"^\s*lon:\s*([0-9.]+)", yml.group(1), re.M)
        lat, lon = mlat and mlat.group(1), mlon and mlon.group(1)
    if not (lat and lon):
        m = re.search(r"Koordinaten\s*~?([0-9]{1,2}\.[0-9]+)\s*/\s*([0-9]{1,3}\.[0-9]+)", text)
        if m:
            lat, lon = m.group(1), m.group(2)
    if not (lat and lon):
        return
    target.parent.mkdir(exist_ok=True)
    target.write_text(
        f"https://api.brightsky.dev/weather?lat={lat}&lon={lon}&date={{date}}&tz=Europe/Berlin\n"
        "# {date} durch den Zieltag YYYY-MM-DD ersetzen. Quelle: athlete.md "
        "(senpai-export-Block bzw. Koordinaten-Anker); Regeneration: "
        "export_claude_ai.py --refresh-personal\n",
        encoding="utf-8",
    )


def resolve_personal(src_rel: str, arc: str, name: str, out_dir: Path,
                     refresh: bool, skip: bool) -> bytes | None:
    data_path = REPO / src_rel
    committed = out_dir / "src" / name / arc
    if refresh:
        if not data_path.exists():
            raise SystemExit(
                f"{name}: Personal-Asset {src_rel} fehlt — vorher aus Drive nach ./data "
                f"ziehen (siehe README) oder ohne --refresh-personal exportieren."
            )
        return data_path.read_bytes()
    if committed.exists():
        return committed.read_bytes()
    if data_path.exists():
        return data_path.read_bytes()
    if skip:
        return None
    raise SystemExit(
        f"{name}: Personal-Asset {arc} weder committet noch in ./data — "
        f"--refresh-personal nach Drive-Pull nutzen oder --skip-personal."
    )


# ---------------------------------------------------------------------------
# Projekt-Anweisungen (aus CLAUDE.md + Templates)
# ---------------------------------------------------------------------------
# Rewrites NUR für die aus CLAUDE.md extrahierten Sektionen. required=True →
# Regel MUSS feuern (schützt vor stiller CLAUDE.md-Umformulierung).
INSTR_REWRITES = (
    (r"`lib/constants\.py`", "die Schwellen-Registry des Repos", True),
    (r"lib/constants\.py", "die Schwellen-Registry des Repos", False),
    (r"`?tests/test_threshold_consistency\.py`?", "die Repo-Testsuite", True),
    (r"`?modules/V3_Protocol\.md`?", "`references/V3_Protocol.md` (run-bundle-Bundle)", True),
    (r"aus `lib/weather\.py`-Slot-Wert", "aus dem Bright-Sky-Slot-Wert (`scripts/weather.py`)", True),
    (r"`?lib/weather\.py`?", "`scripts/weather.py` im weather-Bundle", True),
    (r"`?lib/clock\.py`?", "die Sandbox-Uhr", False),
    (r"via `--upload` zurück", "per Drive-Connector-Update zurück", True),
    (r"\*\*Persönliche Daten in den Repo / in `CLAUDE\.md` schreiben\*\*[^\n]*",
     "**Persönliche Roh-Daten in die Projekt-Anweisungen schreiben** — Identität "
     "bleibt in `athlete.md` (Drive-synchronisierte Projekt-Datei)", True),
    (r"fehlende Daten erst via `pull_drive\.py` ziehen",
     "fehlende Daten erst per Upload-Anforderung/Connector beschaffen", True),
    (r"Ist `athlete\.md` \(noch\) nicht gezogen", "Fehlt `athlete.md` im Kontext", False),
    (r"Pull nachholen", "Projekt-Datei-Sync prüfen", False),
)


def _claude_md_sections(text: str) -> dict[int, str]:
    """CLAUDE.md in nummerierte ##-Sektionen zerlegen (ohne ----Separatoren)."""
    parts: dict[int, list[str]] = {}
    current: int | None = None
    for line in text.splitlines():
        m = re.match(r"^## (\d+)\.", line)
        if m:
            current = int(m.group(1))
            parts[current] = [line]
        elif line.strip() == "---":
            current = None
        elif current is not None:
            parts[current].append(line)
    return {k: "\n".join(v).rstrip() for k, v in parts.items()}


def _verdict_kontrakt(text: str) -> str:
    m = re.search(r"^### 📜 Verdict-Kontrakt.*?(?=^---$|^## )", text, re.S | re.M)
    if not m:
        raise SystemExit("CLAUDE.md: Verdict-Kontrakt-Subsektion nicht gefunden")
    return m.group(0).rstrip()


def build_instructions(commit: str) -> str:
    cmd = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    secs = _claude_md_sections(cmd)
    for need in (1, 2, 4, 5, 6, 8):
        if need not in secs:
            raise SystemExit(f"CLAUDE.md: Sektion §{need} nicht gefunden")

    extracted = "\n\n---\n\n".join(
        [_verdict_kontrakt(cmd), "@@S1@@", secs[1], secs[2], "@@S3@@", secs[4],
         secs[5], secs[6], "@@S7@@", secs[8]]
    )
    # @@-Anker trennen Extrakt-Blöcke, damit Rewrites nur Extrakte treffen
    for pat, repl, required in INSTR_REWRITES:
        new = re.sub(pat, repl, extracted)
        if required and new == extracted:
            raise SystemExit(
                f"Projekt-Anweisungen: Pflicht-Rewrite {pat!r} hat nicht gefeuert — "
                "CLAUDE.md-Wortlaut geändert? Regel in INSTR_REWRITES anpassen."
            )
        extracted = new

    verdict, rest = extracted.split("\n\n---\n\n@@S1@@\n\n---\n\n", 1)
    s12, s3rest = rest.split("\n\n---\n\n@@S3@@\n\n---\n\n", 1)
    s456, s7rest = s3rest.split("\n\n---\n\n@@S7@@\n\n---\n\n", 1)
    s8 = s7rest

    def tpl(fname: str) -> str:
        return (TEMPLATES / fname).read_text(encoding="utf-8").rstrip()

    head = (tpl("instructions_head.md")
            .replace("{{VERSION}}", TWIN_VERSION)
            .replace("{{COMMIT}}", commit)
            .replace("{{VERDICT_KONTRAKT}}", verdict))
    parts = [
        head, s12, tpl("instructions_s3.md"), s456, tpl("instructions_s7.md"),
        s8, tpl("instructions_s9.md"), tpl("instructions_s10.md"),
        tpl("instructions_s11.md"),
        f"---\n**Version:** {TWIN_VERSION} — claude.ai-Twin | generiert aus "
        f"`senpai-ai-chat@{commit}` | NICHT von Hand editieren.\n"
        "*\"Runna gibt Struktur. HR gibt Intensität. Pace ist Ergebnis.\" — und: "
        "nur Aggregate erreichen den Kontext, nie die Roh-Serie.*",
    ]
    out = "\n\n---\n\n".join(parts) + "\n"
    assert_clean(out, "export:project-instructions.md")
    return out


# ---------------------------------------------------------------------------
# Bundle-Smoke-Test: jedes gebündelte Skript muss im Bundle-Layout importierbar
# sein (Sibling-Imports!). Bekannte Third-Party-Module dürfen lokal fehlen —
# in der claude.ai-Sandbox sind sie vorinstalliert bzw. pip-bar.
# ---------------------------------------------------------------------------
_ALLOWED_MISSING = {"fitparse", "numpy", "scipy", "statsmodels", "matplotlib", "pandas"}

_IMPORT_PROBE = """
import importlib.util, sys
sys.path.insert(0, "scripts")
name = sys.argv[1]
try:
    spec = importlib.util.spec_from_file_location(name[:-3], "scripts/" + name)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name[:-3]] = mod
    spec.loader.exec_module(mod)
except ModuleNotFoundError as e:
    if e.name.split(".")[0] in {allowed}:
        sys.exit(0)
    raise
"""


def smoke_test_bundle(skill_dir: Path, name: str) -> None:
    scripts = sorted((skill_dir / "scripts").glob("*.py")) if (skill_dir / "scripts").exists() else []
    probe = _IMPORT_PROBE.format(allowed=_ALLOWED_MISSING)
    for s in scripts:
        r = subprocess.run([sys.executable, "-c", probe, s.name],
                           cwd=skill_dir, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(
                f"Bundle-Smoke-Test FEHLGESCHLAGEN — {name}/scripts/{s.name} ist im "
                f"Bundle-Layout nicht importierbar:\n{r.stderr.strip()[-800:]}"
            )


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build(out_dir: Path, refresh: bool, skip_personal: bool) -> dict:
    gen_brightsky_url(refresh)
    artifacts: dict[str, dict] = {}

    for name in sorted(R.SKILLS):
        smd = build_skill_md(name)
        files: list[tuple[str, bytes, bool]] = []
        src_paths = [f".claude/skills/{name}/"]
        for src_rel, arc, personal in R.bundle_files(name):
            if personal:
                data = resolve_personal(src_rel, arc, name, out_dir, refresh, skip_personal)
                if data is None:
                    continue
            else:
                p = REPO / src_rel
                if not p.exists():
                    raise SystemExit(f"{name}: Bundle-Quelle fehlt: {src_rel}")
                data = p.read_bytes()
                src_paths.append(src_rel)
            files.append((arc, data, personal))

        h = hashlib.sha256(smd.encode("utf-8"))
        for arc, data, personal in sorted(files):
            if not personal:
                h.update(arc.encode() + b"\0" + data + b"\0")
        content_hash = h.hexdigest()
        personal_parts = [(a, d) for a, d, p in sorted(files) if p]
        personal_hash = (_sha(b"".join(a.encode() + b"\0" + d for a, d in personal_parts))
                         if personal_parts else None)

        commit = source_commit(src_paths)
        footer = (f"\n---\n> Export-Stand: {name} {skill_version(name)} · "
                  f"senpai-ai-chat@{commit} · content {content_hash[:12]} · generiert "
                  f"von export_claude_ai.py — NICHT von Hand editieren.\n")
        artifacts[name] = {
            "version": skill_version(name),
            "content_hash": content_hash,
            "personal_hash": personal_hash,
            "source_commit": commit,
            "skill_md": smd + footer,
            "files": files,
        }

    commit_all = source_commit(["CLAUDE.md", "lib/export_templates/", "lib/export_rules.py"])
    docs = {
        "project-instructions.md": build_instructions(commit_all),
        "project-files.md": (TEMPLATES / "project_files.md").read_text(encoding="utf-8"),
        "smoke-tests.md": (TEMPLATES / "smoke_tests.md").read_text(encoding="utf-8").replace(
            "{{BRIGHTSKY_URL_HEUTE}}",
            "die URL aus `assets/brightsky_url.txt` des weather-Bundles "
            "(`{date}` = heute, YYYY-MM-DD)"),
        "README.md": (TEMPLATES / "readme.md").read_text(encoding="utf-8"),
    }
    for fname, text in docs.items():
        # README.md ist Repo-facing (erklärt pull_drive/Exporter-Kommandos) und
        # bewusst vom claude.ai-Forbidden-Gate ausgenommen.
        if fname != "README.md":
            assert_clean(text, f"export:{fname}")
    return {"artifacts": artifacts, "docs": docs}


def _zip_bytes(name: str, art: dict) -> bytes:
    buf = io.BytesIO()
    entries = [(f"{name}/SKILL.md", art["skill_md"].encode("utf-8"))]
    entries += [(f"{name}/{arc}", data) for arc, data, _ in art["files"]]
    with zipfile.ZipFile(buf, "w") as z:
        for arcname, data in sorted(entries):
            zi = zipfile.ZipInfo(arcname, date_time=_ZIP_DATE)
            zi.external_attr = 0o644 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data, compresslevel=9)
    return buf.getvalue()


def manifest_dict(built: dict, zips: dict[str, bytes] | None) -> dict:
    arts = {}
    for name, a in built["artifacts"].items():
        arts[name] = {
            "version": a["version"],
            "content_hash": a["content_hash"],
            "personal_hash": a["personal_hash"],
            "source_commit": a["source_commit"],
            "zip": f"dist/{name}.skill",
            "zip_sha256": _sha(zips[name]) if zips else None,
            "reupload_hint": f"RE-UPLOAD dist/{name}.skill (claude.ai → Settings → Skills)",
        }
    docs = {fname: {"content_hash": _sha(text.encode("utf-8")),
                    "action_hint": "PASTE in claude.ai" if fname == "project-instructions.md"
                    else "Referenz/Checkliste"}
            for fname, text in built["docs"].items()}
    return {"schema": 1, "twin_version": TWIN_VERSION, "artifacts": arts, "docs": docs}


def write_out(out_dir: Path, built: dict) -> dict:
    zips = {name: _zip_bytes(name, a) for name, a in built["artifacts"].items()}
    for sub in ("src", "dist"):
        shutil.rmtree(out_dir / sub, ignore_errors=True)
    for legacy in out_dir.glob("*.skill"):  # Alt-Layout (Root-Zips) räumen
        legacy.unlink()
    for name, a in built["artifacts"].items():
        sdir = out_dir / "src" / name
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(a["skill_md"], encoding="utf-8")
        for arc, data, _ in a["files"]:
            p = sdir / arc
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        smoke_test_bundle(sdir, name)
        ddir = out_dir / "dist"
        ddir.mkdir(parents=True, exist_ok=True)
        (ddir / f"{name}.skill").write_bytes(zips[name])
    for fname, text in built["docs"].items():
        (out_dir / fname).write_text(text, encoding="utf-8")
    mf = manifest_dict(built, zips)
    (out_dir / "MANIFEST.json").write_text(
        json.dumps(mf, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return mf


def diff_report(old: dict | None, new: dict, skip_personal: bool) -> list[str]:
    lines: list[str] = []
    old_arts = (old or {}).get("artifacts", {})
    for name, a in sorted(new["artifacts"].items()):
        o = old_arts.get(name)
        if o is None:
            lines.append(f"NEU: dist/{name}.skill → hochladen")
        elif o.get("content_hash") != a["content_hash"]:
            lines.append(f"RE-UPLOAD: dist/{name}.skill "
                         f"({o.get('source_commit')}→{a['source_commit']})")
        elif not skip_personal and o.get("personal_hash") != a["personal_hash"]:
            lines.append(f"RE-UPLOAD: dist/{name}.skill (Personal-Assets geändert)")
    old_docs = (old or {}).get("docs", {})
    for fname, d in sorted(new["docs"].items()):
        if old_docs.get(fname, {}).get("content_hash") != d["content_hash"]:
            lines.append(f"PASTE/PRÜFEN: {fname}")
    return lines


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="claude.ai-Twin-Export (Repo = SSoT).")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--check", action="store_true",
                   help="nur Drift-Check gegen committetes MANIFEST.json (exit 1 bei Drift)")
    p.add_argument("--skip-personal", action="store_true",
                   help="ohne Personal-Assets bauen/prüfen (Tests, hermetisch)")
    p.add_argument("--refresh-personal", action="store_true",
                   help="Personal-Assets aus ./data neu einfrieren")
    args = p.parse_args(argv)
    out_dir = Path(args.out)

    built = build(out_dir if not args.check else DEFAULT_OUT,
                  args.refresh_personal, args.skip_personal)

    manifest_path = DEFAULT_OUT / "MANIFEST.json"
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None

    if args.check:
        new = manifest_dict(built, zips=None)
        drift = []
        for name, a in new["artifacts"].items():
            o = (old or {}).get("artifacts", {}).get(name)
            if not o or o.get("content_hash") != a["content_hash"]:
                drift.append(f"DRIFT: {name} (content_hash)")
            elif not args.skip_personal and o.get("personal_hash") != a["personal_hash"]:
                drift.append(f"DRIFT: {name} (personal_hash)")
        for fname, d in new["docs"].items():
            o = (old or {}).get("docs", {}).get(fname)
            if not o or o.get("content_hash") != d["content_hash"]:
                drift.append(f"DRIFT: {fname}")
        if drift:
            print("\n".join(drift))
            print("→ python3 lib/export_claude_ai.py laufen lassen und Ergebnis committen.")
            return 1
        print("Export-Check: kein Drift.")
        return 0

    mf = write_out(out_dir, built)
    report = diff_report(old, mf, args.skip_personal)
    print(f"Export OK → {out_dir} ({len(mf['artifacts'])} Skills, {len(mf['docs'])} Doku-Dateien)")
    print("\n".join(report) if report else "Keine Re-Upload-Aktionen (alles unverändert).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
