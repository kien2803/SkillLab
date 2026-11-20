"""Skill Blueprints: structured intermediate representation between
research and SKILL.md.

A blueprint lives inside a research project and describes *how* a new
capability should work before any skill file is generated:

    research/projects/<pid>/blueprints/<bp-id>/
      blueprint.yaml        # current state (Blueprint model)
      revisions/r<NNN>.yaml # snapshot of every saved revision

Design rules:
  - every mutation bumps `rev` and snapshots the previous state, so
    `blueprint diff` can compare any two revisions;
  - status transitions beyond `designing` are gated on validation —
    errors (missing required sections, contradictions) block promotion;
  - blueprints link to research findings; generated skill variants are
    recorded for traceability (filled by the studio in Phase 3).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .lab import Lab, LabError
from .models import (Blueprint, load_yaml, dump_yaml)
from .research import project_dir, list_findings

# The 23 blueprint sections, in spec order.
# kind: "list" = list[str], "text" = free text.
# req=True blocks `ready_for_generation` when empty.
FIELDS: list[tuple[str, str, bool, str]] = [
    ("name", "text", True, "Skill name (kebab-case)"),
    ("description", "text", True, "Frontmatter-style trigger description"),
    ("research_motivation", "text", False, "Why research says this is needed"),
    ("problem_statement", "text", True, "What problem it solves"),
    ("target_capability", "text", True, "The capability being added"),
    ("target_users", "list", False, "Who uses it"),
    ("use_cases", "list", False, "Concrete usage scenarios"),
    ("in_scope_tasks", "list", True, "Tasks the skill must handle"),
    ("out_of_scope_tasks", "list", False, "Tasks it must NOT trigger on"),
    ("trigger_conditions", "list", True, "When it should activate"),
    ("preconditions", "list", False, "What must hold before it runs"),
    ("required_context", "list", False, "Context/inputs it needs"),
    ("execution_workflow", "list", True, "Ordered steps"),
    ("decision_rules", "list", False, "Branching rules"),
    ("tool_requirements", "list", False, "Tools it calls"),
    ("resource_requirements", "list", False, "Bundled files/resources"),
    ("output_contract", "text", True, "Shape/format of output"),
    ("error_handling", "list", False, "Failure handling"),
    ("safety_constraints", "list", False, "What it must never do"),
    ("known_limitations", "list", False, "Acknowledged gaps"),
    ("verification_strategy", "text", False, "How correctness is checked"),
    ("evaluation_criteria", "list", True, "Rubric/eval criteria"),
    ("compatible_environments", "list", False, "Agent runtimes/harnesses"),
]

FIELD_KEYS = [k for k, _, _, _ in FIELDS]
_FIELD_META = {k: (kind, req, label) for k, kind, req, label in FIELDS}

# Statuses that require a clean validation report.
_GATED = {"ready_for_generation", "generated", "testing", "improving",
          "validated", "released"}


def blueprints_dir(lab: Lab, pid: str) -> Path:
    return project_dir(lab, pid) / "blueprints"


def blueprint_dir(lab: Lab, pid: str, bid: str) -> Path:
    d = blueprints_dir(lab, pid) / bid
    if not (d / "blueprint.yaml").is_file():
        raise LabError(f"Blueprint '{bid}' not found in project '{pid}'.")
    return d


def _empty_fields() -> dict:
    return {k: ([] if kind == "list" else "")
            for k, kind, req, label in FIELDS}


# ---------- create / load ----------


def new_blueprint(lab: Lab, pid: str, bid: str, title: str = "") -> Path:
    import re
    bid = re.sub(r"[^a-z0-9-]+", "-", bid.lower()).strip("-") or "bp"
    d = blueprints_dir(lab, pid) / bid
    if (d / "blueprint.yaml").exists():
        raise LabError(f"Blueprint '{bid}' already exists.")
    (d / "revisions").mkdir(parents=True)
    today = date.today().isoformat()
    bp = Blueprint(id=bid, title=title or bid, created=today,
                   updated=today)
    bp.fields = _empty_fields()
    _save(lab, pid, bp, snapshot=False)
    return d


def get_blueprint(lab: Lab, pid: str, bid: str) -> Blueprint:
    return Blueprint(**load_yaml(blueprint_dir(lab, pid, bid)
                                 / "blueprint.yaml"))


def list_blueprints(lab: Lab, pid: str) -> list[Blueprint]:
    out = []
    d = blueprints_dir(lab, pid)
    if d.is_dir():
        for sub in sorted(d.iterdir()):
            if (sub / "blueprint.yaml").is_file():
                out.append(Blueprint(**load_yaml(sub / "blueprint.yaml")))
    return out


def _save(lab: Lab, pid: str, bp: Blueprint, snapshot: bool = True) -> None:
    d = blueprints_dir(lab, pid) / bp.id
    if snapshot:
        # archive the previous revision before overwriting
        cur = d / "blueprint.yaml"
        if cur.is_file():
            old = Blueprint(**load_yaml(cur))
            revdir = d / "revisions"
            revdir.mkdir(exist_ok=True)
            dump_yaml(old.model_dump(mode="json"),
                      revdir / f"r{old.rev:03d}.yaml")
        bp.rev += 1
    bp.updated = date.today().isoformat()
    dump_yaml(bp.model_dump(mode="json"), d / "blueprint.yaml")


# ---------- editing ----------


def set_field(lab: Lab, pid: str, bid: str, key: str,
              value, append: bool = False) -> Blueprint:
    bp = get_blueprint(lab, pid, bid)
    if key not in _FIELD_META:
        raise LabError(f"unknown blueprint field '{key}' — "
                       f"valid: {', '.join(FIELD_KEYS)}")
    kind, _, _ = _FIELD_META[key]
    if kind == "list":
        items = value if isinstance(value, list) else [v.strip() for v in
                                                       str(value).split(",")
                                                       if v.strip()]
        if append:
            bp.fields[key] = list(bp.fields.get(key) or []) + items
        else:
            bp.fields[key] = items
    else:
        bp.fields[key] = str(value)
    _save(lab, pid, bp)
    return bp


def from_question(lab: Lab, pid: str, bid: str, qid: str) -> Blueprint:
    """Prefill motivation/problem from a research question."""
    from .models import ResearchQuestion
    qp = project_dir(lab, pid) / "questions" / f"{qid}.yaml"
    if not qp.is_file():
        raise LabError(f"question '{qid}' not found in project '{pid}'")
    q = ResearchQuestion(**load_yaml(qp))
    bp = get_blueprint(lab, pid, bid)
    if q.question and not bp.fields.get("problem_statement"):
        bp.fields["problem_statement"] = q.question
    motivation = q.objective or ""
    if q.hypothesis:
        motivation += ("\n" if motivation else "") + \
            f"Hypothesis: {q.hypothesis}"
    if motivation and not bp.fields.get("research_motivation"):
        bp.fields["research_motivation"] = motivation
    _save(lab, pid, bp)
    return bp


def link_finding(lab: Lab, pid: str, bid: str, fid: str) -> None:
    fids = {f.id for f in list_findings(lab, pid)}
    if fid not in fids:
        raise LabError(f"finding '{fid}' not found in project '{pid}'")
    bp = get_blueprint(lab, pid, bid)
    if fid not in bp.related_findings:
        bp.related_findings.append(fid)
        _save(lab, pid, bp)


# ---------- validation ----------


def validate(lab: Lab, pid: str, bid: str) -> list[dict]:
    """Completeness + contradiction checks. severity: error|warn."""
    bp = get_blueprint(lab, pid, bid)
    f = bp.fields
    issues = []

    for key, kind, req, label in FIELDS:
        val = f.get(key)
        empty = not val if isinstance(val, str) or val is None \
            else not len(val)
        if req and empty:
            issues.append({"severity": "error", "check": "required",
                           "field": key,
                           "message": f"{label} is required before "
                                      "generation"})

    ins = set(f.get("in_scope_tasks") or [])
    outs = set(f.get("out_of_scope_tasks") or [])
    overlap = ins & outs
    if overlap:
        issues.append({"severity": "error", "check": "contradiction",
                       "field": "out_of_scope_tasks",
                       "message": f"tasks in both in-scope and "
                                  f"out-of-scope: {sorted(overlap)}"})
    if ins and not (f.get("trigger_conditions")):
        issues.append({"severity": "warn", "check": "ambiguity",
                       "field": "trigger_conditions",
                       "message": "in-scope tasks defined but no trigger "
                                  "conditions — activation is ambiguous"})
    if f.get("execution_workflow") and not f.get("output_contract"):
        issues.append({"severity": "warn", "check": "contract",
                       "field": "output_contract",
                       "message": "workflow defined but output contract "
                                  "is empty"})
    if f.get("evaluation_criteria") and not f.get("verification_strategy"):
        issues.append({"severity": "warn", "check": "verification",
                       "field": "verification_strategy",
                       "message": "evaluation criteria exist but no "
                                  "verification strategy"})
    desc = f.get("description") or ""
    if desc and len(desc) < 40:
        issues.append({"severity": "warn", "check": "description",
                       "field": "description",
                       "message": "description under 40 chars — weak "
                                  "activation signal"})
    return issues


def set_status(lab: Lab, pid: str, bid: str, status: str) -> Blueprint:
    bp = get_blueprint(lab, pid, bid)
    if status in _GATED:
        errors = [i for i in validate(lab, pid, bid)
                  if i["severity"] == "error"]
        if errors:
            raise LabError(
                f"blueprint '{bid}' has {len(errors)} validation "
                f"error(s) — fix before '{status}': "
                + "; ".join(i["field"] for i in errors))
    bp.status = status
    _save(lab, pid, bp)
    return bp


# ---------- revisions ----------


def revisions(lab: Lab, pid: str, bid: str) -> list[Blueprint]:
    d = blueprint_dir(lab, pid, bid) / "revisions"
    out = []
    if d.is_dir():
        for p in sorted(d.glob("r*.yaml")):
            out.append(Blueprint(**load_yaml(p)))
    out.append(get_blueprint(lab, pid, bid))
    return out


def diff_revisions(lab: Lab, pid: str, bid: str, from_rev: int,
                   to_rev: int | None = None) -> list[dict]:
    revs = {b.rev: b for b in revisions(lab, pid, bid)}
    if from_rev not in revs:
        raise LabError(f"revision r{from_rev} not found")
    a = revs[from_rev]
    b = revs[to_rev] if to_rev else get_blueprint(lab, pid, bid)
    diffs = []
    for key in FIELD_KEYS + ["status"]:
        va = a.fields.get(key) if key != "status" else a.status
        vb = b.fields.get(key) if key != "status" else b.status
        if va != vb:
            diffs.append({"field": key, "from": va, "to": vb,
                          "from_rev": a.rev, "to_rev": b.rev})
    return diffs
