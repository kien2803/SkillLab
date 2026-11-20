"""Skill Studio: turn a validated blueprint into a skill variant.

`FORMATS` is the format/export abstraction — emitters convert blueprint
fields into a concrete artifact for a target agent environment. New
formats register here without touching the registry or CLI.

Safety:
  - generation requires a blueprint that passes validation
    (`ready_for_generation` or later);
  - an existing variant is never overwritten silently — `--force`
    archives it under `archive/skills/<sid>/<vid>-<ts>/` first;
  - every generated file carries a provenance comment and the variant
    note records `blueprint <pid>/<bid>@r<rev>` for traceability.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from .blueprint import get_blueprint, validate, _save
from .lab import Lab, LabError
from .models import Blueprint, SkillMeta, Variant


# ---------- emitters (format abstraction) ----------

def _li(items) -> str:
    return "\n".join(f"- {i}" for i in items)


def _ol(items) -> str:
    return "\n".join(f"{n}. {i}" for n, i in enumerate(items, 1))


def _section(title: str, body: str) -> str:
    return f"\n## {title}\n\n{body}\n" if body.strip() else ""


def emit_skill_md(bp: Blueprint) -> str:
    f = bp.fields
    desc = f.get("description") or f.get("problem_statement") or ""
    # yaml-safe scalars: collapse whitespace/newlines so frontmatter
    # can't be broken by field content
    name = " ".join(str(f.get("name") or bp.id).split())
    desc = " ".join(str(desc).split())
    title = " ".join(str(bp.title or f.get("name") or bp.id).split())
    out = (f"---\nname: {name}\n"
           f"description: >-\n  {desc}\n---\n\n"
           f"# {title}\n\n")
    intro = f.get("target_capability") or f.get("problem_statement") or ""
    if intro:
        out += intro + "\n"
    when = _li((f.get("trigger_conditions") or [])
               + (f.get("use_cases") or []))
    out += _section("When to use", when)
    not_when = _li(f.get("out_of_scope_tasks") or [])
    out += _section("When NOT to use", not_when)
    if f.get("preconditions"):
        out += _section("Preconditions", _li(f["preconditions"]))
    out += _section("Workflow", _ol(f.get("execution_workflow") or []))
    rules = _li((f.get("decision_rules") or [])
                + (f.get("safety_constraints") or []))
    out += _section("Rules", rules)
    if f.get("tool_requirements"):
        out += _section("Tools", _li(f["tool_requirements"]))
    out += _section("Output", f.get("output_contract") or "")
    if f.get("error_handling"):
        out += _section("Error handling", _li(f["error_handling"]))
    if f.get("known_limitations"):
        out += _section("Limitations", _li(f["known_limitations"]))
    out += (f"\n<!-- generated from blueprint {bp.id} "
            f"r{bp.rev} — edit via `lab blueprint set` and regenerate, "
            "or treat this as a draft -->\n")
    return out


def emit_system_prompt(bp: Blueprint) -> str:
    """system-prompt target: same content as skill-md minus YAML
    frontmatter (for runtimes that take a plain system prompt)."""
    md = emit_skill_md(bp)
    if md.startswith("---"):
        md = md.split("---", 2)[2].lstrip("\n")
    return md


# Format registry: each target declares its output filename + emitter so
# a generated artifact never silently lands in the wrong file.
FORMATS: dict[str, dict] = {
    "skill-md": {"filename": "SKILL.md", "emit": emit_skill_md,
                 "frontmatter": True,
                 "note": "agent skill — SKILL.md entry file"},
    "system-prompt": {"filename": "system-prompt.md",
                      "emit": emit_system_prompt,
                      "frontmatter": False,
                      "note": "plain system prompt (no frontmatter)"},
    # new targets register here
}


# ---------- generation ----------


_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def generate_skill(lab: Lab, pid: str, bid: str, skill_id: str,
                   variant_id: str, fmt: str = "skill-md",
                   force: bool = False) -> Path:
    if fmt not in FORMATS:
        raise LabError(f"unknown format '{fmt}' — "
                       f"available: {', '.join(FORMATS)}")
    for name, val in (("skill", skill_id), ("variant", variant_id)):
        if not _ID_RE.fullmatch(val):
            raise LabError(f"invalid {name} id {val!r} "
                           "(allowed: [A-Za-z0-9._-], starts alnum)")
    bp = get_blueprint(lab, pid, bid)
    errors = [i for i in validate(lab, pid, bid)
              if i["severity"] == "error"]
    if errors:
        raise LabError(
            f"blueprint '{bid}' has validation errors — fix before "
            "generating: " + "; ".join(i["field"] for i in errors))

    sdir = lab.skills_dir / skill_id
    vpath = Path("variants") / variant_id
    vdir = sdir / vpath
    if not vdir.resolve().is_relative_to(sdir.resolve()):
        raise LabError(f"variant id {variant_id!r} escapes skill dir")

    if sdir.is_dir() and (sdir / "skill.yaml").is_file():
        meta = SkillMeta.load(sdir)
        if any(v.id == variant_id for v in meta.variants):
            if not force:
                raise LabError(
                    f"variant '{variant_id}' already exists on "
                    f"'{skill_id}' — pass --force to archive and "
                    "replace it")
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = lab.archive_dir / "skills" / skill_id / \
                f"{variant_id}-{ts}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(vdir), str(dest))
    else:
        meta = SkillMeta(id=skill_id, status="draft")
        sdir.mkdir(parents=True, exist_ok=True)

    vdir.mkdir(parents=True, exist_ok=True)
    spec = FORMATS[fmt]
    artifact = vdir / spec["filename"]
    artifact.write_text(spec["emit"](bp))
    # the entry file SKILL.md must exist for every variant; a non-skill-md
    # format still gets a minimal index so the variant stays loadable
    if spec["filename"] != "SKILL.md" and not (vdir / "SKILL.md").is_file():
        (vdir / "SKILL.md").write_text(
            f"---\nname: {skill_id}\n"
            f"description: generated {fmt} artifact — see "
            f"{spec['filename']}\n---\n\n"
            f"# {skill_id}\n\nGenerated artifact: `{spec['filename']}` "
            f"({spec['note']}).\n")

    if not any(v.id == variant_id for v in meta.variants):
        meta.variants.append(Variant(
            id=variant_id, path=str(vpath),
            note=f"blueprint {pid}/{bid}@r{bp.rev}"))
    else:
        for v in meta.variants:
            if v.id == variant_id:
                v.note = f"blueprint {pid}/{bid}@r{bp.rev}"
    meta.save(sdir)

    ref = f"{skill_id}@{variant_id}"
    if ref not in bp.generated_variants:
        bp.generated_variants.append(ref)
    order = ["draft", "designing", "ready_for_generation"]
    if bp.status in order:
        bp.status = "generated"
    _save(lab, pid, bp)
    return artifact


# ---------- studio tools: preview / validate / resources / sync -------

from .models import est_tokens, parse_frontmatter, parse_skill_ref


def skill_entry(vdir: Path) -> Path | None:
    for n in ("SKILL.md", "skill.md"):
        p = vdir / n
        if p.is_file():
            return p
    return None


def preview(lab: Lab, ref: str) -> dict:
    """Structure + token estimate for a variant (offline, no render)."""
    sid, vid = parse_skill_ref(ref)
    vdir = lab.variant_dir(sid, vid)
    entry = skill_entry(vdir)
    if not entry:
        raise LabError(f"no SKILL.md in {vdir}")
    text = entry.read_text()
    fm, body = parse_frontmatter(text)
    sections = [m.group(1).strip() for m in
                re.finditer(r"^#{1,3}\s+(.+)$", body, re.M)]
    resources = [str(p.relative_to(vdir)) for p in sorted(vdir.rglob("*"))
                 if p.is_file() and p != entry]
    return {
        "ref": ref, "entry": str(entry.relative_to(vdir)),
        "tokens": est_tokens(text), "fm": fm, "sections": sections,
        "resources": resources,
    }


def validate_skill(lab: Lab, ref: str) -> list[dict]:
    """Studio-level validation: analyzer findings + frontmatter schema."""
    from .analyzer import analyze_skill
    sid, vid = parse_skill_ref(ref)
    out = []
    info = preview(lab, ref)
    fm = info["fm"]
    for k in ("name", "description"):
        if not fm.get(k):
            out.append({"severity": "error", "check": "frontmatter",
                        "message": f"missing required '{k}' in "
                                   "frontmatter"})
    if fm.get("name") and fm["name"] != sid:
        out.append({"severity": "warn", "check": "frontmatter",
                    "message": f"frontmatter name '{fm['name']}' != "
                               f"registry id '{sid}'"})
    for f in analyze_skill(lab, sid).get(vid or "", []):
        out.append({"severity": f.severity, "check": f.check,
                    "message": f.message})
    return out


def add_resource(lab: Lab, ref: str, src_path: str) -> Path:
    """Copy a file into the variant's resources/ and report link status."""
    src = Path(src_path)
    if not src.is_file():
        raise LabError(f"resource '{src_path}' not found")
    sid, vid = parse_skill_ref(ref)
    vdir = lab.variant_dir(sid, vid)
    dest = vdir / "resources" / src.name
    dest.parent.mkdir(exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def artifact_diff(lab: Lab, pid: str, bid: str, ref: str) -> dict:
    """Compare the on-disk artifact against a fresh emit of the current
    blueprint revision — tells synced / manually-edited / blueprint-moved
    apart."""
    bp = get_blueprint(lab, pid, bid)
    sid, vid = parse_skill_ref(ref)
    vdir = lab.variant_dir(sid, vid)
    entry = skill_entry(vdir)
    if not entry:
        raise LabError(f"no artifact at {vdir}")
    fresh = emit_skill_md(bp)
    current = entry.read_text()
    import difflib
    # which revision generated this file? parse the provenance comment
    m = re.search(r"blueprint \S+ r(\d+)", current)
    gen_rev = int(m.group(1)) if m else None
    # ignore the provenance comment itself — generation bumps the
    # blueprint rev (status/generated_variants), so the file always
    # trails by one rev even when content is identical
    strip = lambda t: re.sub(r"<!-- generated from blueprint.*-->\n?",
                             "", t)
    status = "synced" if strip(current) == strip(fresh) else "drifted"
    diff = "".join(difflib.unified_diff(
        current.splitlines(True), fresh.splitlines(True),
        fromfile="on-disk", tofile=f"emit@r{bp.rev}")) \
        if status == "drifted" else ""
    return {"ref": ref, "status": status, "gen_rev": gen_rev,
            "bp_rev": bp.rev, "diff": diff}

