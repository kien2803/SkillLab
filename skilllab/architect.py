"""AI Architect proposals: gated, diff-first skill changes.

Every assistant suggestion is a `proposals/<id>.yaml` record carrying an
explicit patch + computed diff preview. Nothing touches a skill file
until `apply` on an `approved` proposal — and apply keeps the original
content inside the proposal record for rollback.

The engine is deterministic today (rule-driven patches derived from
analyzer findings); LLM-backed proposers plug into the same
proposal→approve→apply mechanism without changing the safety model.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .analyzer import analyze_skill
from .lab import Lab, LabError
from .models import Proposal, dump_yaml, load_yaml, parse_skill_ref

ACTIONABLE = {"dead-links", "token-budget", "progressive-disclosure",
              "description-quality"}


def proposals_dir(lab: Lab) -> Path:
    return lab.d("proposals")


def _next_id(lab: Lab) -> str:
    d = proposals_dir(lab)
    n = 1
    if d.is_dir():
        for p in d.glob("prop-*.yaml"):
            m = re.match(r"prop-(\d+)", p.stem)
            if m:
                n = max(n, int(m.group(1)) + 1)
    return f"prop-{n:03d}"


def _variant_dir(lab: Lab, ref: str) -> Path:
    sid, vid = parse_skill_ref(ref)
    return lab.variant_dir(sid, vid)


# ---------- patch builders (deterministic proposers) ----------


def _patches_for(f, vdir: Path) -> dict | None:
    """Map an analyzer finding to a concrete patch, or None."""
    if f.check == "description-quality":
        return {"type": "description-trigger",
                "summary": "rewrite description to open with an explicit "
                           "'Use when …' trigger clause",
                "file": "SKILL.md"}
    if f.check == "dead-links":
        m = re.search(r"'([^']+)'", f.message)
        if not m:
            return None
        return {"type": "unlink",
                "summary": f"drop the dead reference `{m.group(1)}` "
                           "(file is not bundled)",
                "file": f.file, "target": m.group(1)}
    if f.check in ("token-budget", "progressive-disclosure"):
        return {"type": "extract-resources",
                "summary": "move detail sections below the core content "
                           "into `resources/detail.md` and link to it",
                "file": "SKILL.md"}
    return None


def suggest(lab: Lab, ref: str) -> list[Proposal]:
    """Generate pending proposals from analyzer findings on a variant."""
    sid, vid = parse_skill_ref(ref)
    vdir = _variant_dir(lab, ref)
    findings = analyze_skill(lab, sid).get(vid or "", [])
    out = []
    for f in findings:
        patch = _patches_for(f, vdir)
        if not patch:
            continue
        p = Proposal(
            id=_next_id(lab), skill=sid, variant=vid or "",
            finding=f"{f.check}: {f.message}", patch=patch,
            status="pending", created=date.today().isoformat())
        p.diff_preview = preview(lab, p)
        dump_yaml(p.model_dump(mode="json"),
                  proposals_dir(lab) / f"{p.id}.yaml")
        out.append(p)
    return out


def list_proposals(lab: Lab) -> list[Proposal]:
    d = proposals_dir(lab)
    out = []
    if d.is_dir():
        for p in sorted(d.glob("prop-*.yaml")):
            out.append(Proposal(**load_yaml(p)))
    return out


def get(lab: Lab, pid: str) -> tuple[Proposal, Path]:
    p = proposals_dir(lab) / f"{pid}.yaml"
    if not p.is_file():
        raise LabError(f"proposal '{pid}' not found")
    return Proposal(**load_yaml(p)), p


# ---------- diff preview + apply ----------


def _entry(vdir: Path) -> Path | None:
    for n in ("SKILL.md", "skill.md"):
        p = vdir / n
        if p.is_file():
            return p
    return None


def _patched_content(vdir: Path, patch: dict) -> tuple[str, str] | None:
    """Return (old_text, new_text) for the patch's target file."""
    src = vdir / patch["file"]
    if not src.is_file():
        return None
    old = src.read_text()
    if patch["type"] == "unlink":
        new = old.replace(f"`{patch['target']}`", patch["target"])
        new = re.sub(r"\[([^\]]*)\]\(" + re.escape(patch["target"]) + r"\)",
                     r"\1", new)
    elif patch["type"] == "description-trigger":
        lines = old.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("description:"):
                desc = ln.split(":", 1)[1].strip().lstrip(">-").strip()
                if not desc.lower().startswith("use when"):
                    lines[i] = ("description: >-\n"
                                f"  Use when {desc[0].lower() + desc[1:]}")
                break
        new = "\n".join(lines) + ("\n" if old.endswith("\n") else "")
    elif patch["type"] == "extract-resources":
        heads = [m.start() for m in
                 re.finditer(r"\n## ", old)]
        if len(heads) < 2:
            return None
        core, tail = old[:heads[-1]], old[heads[-1]:]
        new = core + ("\nFurther detail: `resources/detail.md`\n")
        (vdir / "resources").mkdir(exist_ok=True)
        (vdir / "resources" / "detail.md").write_text(
            "# Detail\n" + tail)
        return old, new
    else:
        return None
    return old, new


def preview(lab: Lab, p: Proposal) -> str:
    vdir = _variant_dir(lab, f"{p.skill}@{p.variant}")
    res = _patched_content(vdir, p.patch)
    if not res:
        return "(no textual diff — new file or unsupported patch)"
    old, new = res
    import difflib
    return "".join(difflib.unified_diff(
        old.splitlines(True), new.splitlines(True),
        fromfile=f"a/{p.patch['file']}", tofile=f"b/{p.patch['file']}"))


def set_status(lab: Lab, pid: str, status: str) -> None:
    p, path = get(lab, pid)
    if status == "applied":
        raise LabError("use `lab ai apply` to apply a proposal")
    p.status = status
    dump_yaml(p.model_dump(mode="json"), path)


def apply(lab: Lab, pid: str) -> Path:
    """Apply an approved proposal. Keeps the original file content in
    the record for audit/rollback. Never applies unapproved work."""
    p, path = get(lab, pid)
    if p.status != "approved":
        raise LabError(f"proposal '{pid}' is '{p.status}' — approve "
                       "first (`lab ai approve`)")
    vdir = _variant_dir(lab, f"{p.skill}@{p.variant}")
    res = _patched_content(vdir, p.patch)
    if not res:
        raise LabError("patch produced no change")
    old, new = res
    p.original_content = old
    (vdir / p.patch["file"]).write_text(new)
    p.status = "applied"
    p.applied_at = date.today().isoformat()
    dump_yaml(p.model_dump(mode="json"), path)
    return vdir / p.patch["file"]
