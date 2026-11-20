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
from .lab import Lab, LabError, check_id
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


# ---------- LLM-backed proposer (Phase 4b) ----------
#
# Same approval gate as deterministic proposals — the model only writes
# patch content; nothing is applied without `lab ai approve` + `apply`.


def _llm_proposals(lab: Lab, ref: str, findings) -> list[dict]:
    """Ask the lab's model for rewrite patches. Returns raw patch dicts.
    Requires a real model or a `cmd:` driver — never called with mock."""
    from .llm import LLMClient
    vdir = _variant_dir(lab, ref)
    entry = _entry(vdir)
    if not entry:
        raise LabError(f"no SKILL.md in {vdir}")
    findings_txt = "\n".join(
        f"- [{f.severity}] {f.check}: {f.message}" for f in findings) \
        or "(no analyzer findings)"
    prompt = (
        "You are a skill-quality architect. Improve this agent skill file "
        "based on the analyzer findings. Return ONLY a JSON array — each "
        "element: {\"summary\": \"one line\", \"file\": \"SKILL.md\", "
        "\"content\": \"<full rewritten file>\"}. Keep frontmatter "
        "valid. Do not invent capabilities, evidence or scores.\n\n"
        f"FINDINGS:\n{findings_txt}\n\nFILE ({entry.name}):\n"
        + entry.read_text())
    model = lab.cfg.get("model", "mock")
    cli = LLMClient(model=model, temperature=0.2)
    reply = cli.complete([{"role": "user", "content": prompt}])
    import json as _json
    txt = (reply.content or "").strip()
    txt = re.sub(r"^```(json)?|```$", "", txt, flags=re.M).strip()
    try:
        items = _json.loads(txt)
    except _json.JSONDecodeError:
        raise LabError("model returned non-JSON proposals — "
                       "inspect with a real model or use deterministic "
                       "suggest")
    if not isinstance(items, list):
        raise LabError("model proposals must be a JSON array")
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("summary") and it.get("content"):
            out.append({"type": "rewrite", "summary": str(it["summary"]),
                        "file": it.get("file") or entry.name,
                        "content": str(it["content"])})
    return out


def suggest(lab: Lab, ref: str, use_llm: bool = False) -> list[Proposal]:
    """Generate pending proposals from analyzer findings on a variant.
    With use_llm, proposals are rewrites drafted by the lab's model —
    same approval gate either way."""
    sid, vid = parse_skill_ref(ref)
    vdir = _variant_dir(lab, ref)
    findings = analyze_skill(lab, sid).get(vid or "", [])
    if use_llm:
        if lab.cfg.get("model", "mock").startswith("mock"):
            raise LabError("--llm needs a real model or `cmd:` driver in "
                           "lab.yaml (model is mock)")
        patches = _llm_proposals(lab, ref, findings)
        out = []
        for patch in patches:
            _record_base(vdir, patch)
            p = Proposal(
                id=_next_id(lab), skill=sid, variant=vid or "",
                finding=f"llm-review ({lab.cfg.get('model')})",
                patch=patch, status="pending",
                created=date.today().isoformat())
            p.diff_preview = preview(lab, p)
            dump_yaml(p.model_dump(mode="json"),
                      proposals_dir(lab) / f"{p.id}.yaml")
            out.append(p)
        return out
    out = []
    for f in findings:
        patch = _patches_for(f, vdir)
        if not patch:
            continue
        _record_base(vdir, patch)
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
    p = proposals_dir(lab) / f"{check_id('proposal', pid)}.yaml"
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


def _patched_files(vdir: Path, patch: dict) -> list[dict] | None:
    """Pure computation of a patch's file changes.

    Returns [{file, old, new}] — `old` is None for files the patch
    creates. NEVER touches the filesystem: preview, apply and hashing
    all read from this single source of truth."""
    src = (vdir / patch["file"]).resolve()
    if not src.is_relative_to(vdir.resolve()):
        return None
    old = src.read_text() if src.is_file() else None
    changes: list[dict] = []
    if patch["type"] == "unlink":
        if old is None:
            return None
        new = old.replace(f"`{patch['target']}`", patch["target"])
        new = re.sub(r"\[([^\]]*)\]\(" + re.escape(patch["target"]) + r"\)",
                     r"\1", new)
        changes.append({"file": patch["file"], "old": old, "new": new})
    elif patch["type"] == "description-trigger":
        if old is None:
            return None
        lines = old.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("description:"):
                desc = ln.split(":", 1)[1].strip().lstrip(">-").strip()
                if desc and not desc.lower().startswith("use when"):
                    lines[i] = ("description: >-\n"
                                f"  Use when {desc[0].lower() + desc[1:]}")
                break
        new = "\n".join(lines) + ("\n" if old.endswith("\n") else "")
        changes.append({"file": patch["file"], "old": old, "new": new})
    elif patch["type"] == "extract-resources":
        if old is None:
            return None
        heads = [m.start() for m in re.finditer(r"\n## ", old)]
        if len(heads) < 2:
            return None
        core, tail = old[:heads[-1]], old[heads[-1]:]
        new = core + "\nFurther detail: `resources/detail.md`\n"
        res_rel = "resources/detail.md"
        res_old = ((vdir / res_rel).read_text()
                   if (vdir / res_rel).is_file() else None)
        changes.append({"file": patch["file"], "old": old, "new": new})
        changes.append({"file": res_rel, "old": res_old,
                        "new": "# Detail\n" + tail})
    elif patch["type"] == "rewrite":
        if not patch.get("content"):
            return None
        changes.append({"file": patch["file"], "old": old,
                        "new": patch["content"]})
    else:
        return None
    return changes or None


def _sha(text: str | None) -> str | None:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:16] \
        if text is not None else None


def _record_base(vdir: Path, patch: dict) -> None:
    """Snapshot sha256 of every file the patch touches so `apply` can
    reject the proposal when the target drifted since preview."""
    base = {}
    for ch in (_patched_files(vdir, patch) or []):
        p = (vdir / ch["file"]).resolve()
        base[ch["file"]] = _sha(
            p.read_text() if p.is_file() else None)
    patch["base"] = base


def preview(lab: Lab, p: Proposal) -> str:
    """Read-only diff of everything the patch would change."""
    vdir = _variant_dir(lab, f"{p.skill}@{p.variant}")
    changes = _patched_files(vdir, p.patch)
    if not changes:
        return "(no textual diff — new file or unsupported patch)"
    import difflib
    out = []
    for ch in changes:
        old = ch["old"] or ""
        out.append("".join(difflib.unified_diff(
            old.splitlines(True), ch["new"].splitlines(True),
            fromfile=f"a/{ch['file']}", tofile=f"b/{ch['file']}")))
    return "".join(out)


def set_status(lab: Lab, pid: str, status: str) -> None:
    p, path = get(lab, pid)
    if status == "applied":
        raise LabError("use `lab ai apply` to apply a proposal")
    p.status = status
    dump_yaml(p.model_dump(mode="json"), path)


def apply(lab: Lab, pid: str) -> list[Path]:
    """Write an approved proposal's file changes.

    Every target file's sha256 recorded at suggest-time must still
    match — a stale proposal is rejected instead of silently clobbering
    newer content. Original contents are kept in the record for
    `rollback`; files created by the patch are recorded too."""
    p, path = get(lab, pid)
    if p.status != "approved":
        raise LabError(f"proposal '{pid}' is '{p.status}' — approve "
                       "first (`lab ai approve`)")
    vdir = _variant_dir(lab, f"{p.skill}@{p.variant}")
    changes = _patched_files(vdir, p.patch)
    if not changes:
        raise LabError("patch produced no change")
    base = p.patch.get("base") or {}
    stale = []
    for ch in changes:
        dest = (vdir / ch["file"]).resolve()
        if not dest.is_relative_to(vdir.resolve()):
            raise LabError(f"patch file escapes variant dir: {ch['file']}")
        cur = _sha(dest.read_text() if dest.is_file() else None)
        if ch["file"] in base and cur != base[ch["file"]]:
            stale.append(ch["file"])
    if stale:
        raise LabError("proposal is stale — file(s) changed since it "
                       f"was generated: {', '.join(stale)}; reject and "
                       "re-run `lab ai suggest`")
    written = []
    for ch in changes:
        dest = (vdir / ch["file"]).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(ch["new"])
        written.append(dest)
    p.original_files = {ch["file"]: ch["old"] for ch in changes}
    p.original_content = changes[0]["old"] or ""
    p.status = "applied"
    p.rolled_back = False
    p.applied_at = date.today().isoformat()
    dump_yaml(p.model_dump(mode="json"), path)
    return written


def rollback(lab: Lab, pid: str) -> list[Path]:
    """Undo an applied proposal: restore originals, delete files it
    created. The proposal returns to `approved` with rolled_back set."""
    p, path = get(lab, pid)
    if p.status != "applied" or p.rolled_back:
        raise LabError(f"proposal '{pid}' has nothing to roll back")
    vdir = _variant_dir(lab, f"{p.skill}@{p.variant}")
    files = p.original_files or (
        {p.patch["file"]: p.original_content}
        if p.original_content else {})
    if not files:
        raise LabError("no original content recorded — cannot roll back")
    touched = []
    for rel, old in files.items():
        dest = (vdir / rel).resolve()
        if not dest.is_relative_to(vdir.resolve()):
            raise LabError(f"recorded file escapes variant dir: {rel}")
        if old is None:
            dest.unlink(missing_ok=True)   # file created by the patch
        else:
            dest.write_text(old)
        touched.append(dest)
    p.rolled_back = True
    p.status = "approved"
    dump_yaml(p.model_dump(mode="json"), path)
    return touched
