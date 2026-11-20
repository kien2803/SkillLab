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
    out = (f"---\nname: {f.get('name') or bp.id}\n"
           f"description: >-\n  {desc}\n---\n\n"
           f"# {bp.title or f.get('name') or bp.id}\n\n")
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


FORMATS = {
    "skill-md": emit_skill_md,
    # future targets (e.g. "claude-skill", "system-prompt") register here
}


# ---------- generation ----------


def generate_skill(lab: Lab, pid: str, bid: str, skill_id: str,
                   variant_id: str, fmt: str = "skill-md",
                   force: bool = False) -> Path:
    if fmt not in FORMATS:
        raise LabError(f"unknown format '{fmt}' — "
                       f"available: {', '.join(FORMATS)}")
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
    (vdir / "SKILL.md").write_text(FORMATS[fmt](bp))

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
    return vdir / "SKILL.md"
