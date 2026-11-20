"""Research projects: top-level container for skill R&D work.

A project groups research questions, sources, notes, findings and
decisions around one research objective. Storage is file-based under
`research/projects/<id>/` — git-friendly, append-only like the rest of
the lab.

    research/projects/<id>/
      project.yaml      # ProjectMeta
      charter.md        # free-form overview (frontmatter + body)
      questions/q*.yaml # ResearchQuestion
      sources/s*.yaml   # ResearchSource
      findings/f*.yaml  # ResearchFinding
      decisions/d*.yaml # ResearchDecision
      notes/*.md        # research notebook entries (frontmatter + body)

Evidence rules (mirroring the insight gates):
  - a finding may only reach `supported` with at least one real
    evidence link (a project source, an experiment, or a run) and
    must not be `kind: unverified`;
  - projects are archived, not deleted, once they hold data —
    `delete` refuses anything beyond an empty draft.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml

from .lab import Lab, LabError, check_id
from .models import (ProjectMeta, ResearchDecision, ResearchFinding,
                     ResearchQuestion, ResearchSource, load_yaml,
                     dump_yaml, parse_frontmatter)

ENTITY_DIRS = ("questions", "sources", "findings", "decisions", "notes",
               "blueprints")

CHARTER = """---
id: {pid}
---
# {title}

## Objective

{objective}

## Problem statement

{problem}

## Scope and constraints

TODO: what is in scope, what is explicitly out.

## Hypotheses

TODO: falsifiable claims this project sets out to test.

## References

TODO: key sources — add structured entries via `lab source add`.
"""

NOTE_TEMPLATE = """---
id: {nid}
created: {today}
tags: []
links: []
---

TODO: observation, log entry, or technical decision context.
"""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-") or "item"


def projects_dir(lab: Lab) -> Path:
    return lab.d("research") / "projects"


def project_dir(lab: Lab, pid: str) -> Path:
    d = projects_dir(lab) / check_id("project", pid)
    if not (d / "project.yaml").is_file():
        raise LabError(f"Research project '{pid}' not found.")
    return d


def _next_id(d: Path, prefix: str) -> str:
    n = 1
    for p in d.glob(f"{prefix}*.yaml"):
        m = re.match(rf"{prefix}(\d+)", p.stem)
        if m:
            n = max(n, int(m.group(1)) + 1)
    return f"{prefix}{n:02d}"


# ---------- projects ----------


def new_project(lab: Lab, pid: str, title: str = "",
                objective: str = "", problem: str = "") -> Path:
    pid = _slug(pid)
    d = projects_dir(lab) / pid
    if (d / "project.yaml").exists():
        raise LabError(f"Research project '{pid}' already exists.")
    today = date.today().isoformat()
    meta = ProjectMeta(id=pid, title=title or pid, objective=objective,
                       problem=problem, created=today, updated=today)
    for sub in ENTITY_DIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    meta.save(d)
    (d / "charter.md").write_text(CHARTER.format(
        pid=pid, title=meta.title,
        objective=objective or "TODO",
        problem=problem or "TODO"))
    return d


def list_projects(lab: Lab) -> list[ProjectMeta]:
    out = []
    pdir = projects_dir(lab)
    if pdir.is_dir():
        for d in sorted(pdir.iterdir()):
            if (d / "project.yaml").is_file():
                out.append(ProjectMeta.load(d))
    return out


def get_project(lab: Lab, pid: str) -> ProjectMeta:
    return ProjectMeta.load(project_dir(lab, pid))


def _touch(meta: ProjectMeta) -> None:
    meta.updated = date.today().isoformat()


def set_status(lab: Lab, pid: str, status: str) -> Path:
    d = project_dir(lab, pid)
    meta = ProjectMeta.load(d)
    meta.status = status  # pydantic validates the lifecycle enum
    _touch(meta)
    meta.save(d)
    return d / "project.yaml"


def archive_project(lab: Lab, pid: str) -> Path:
    return set_status(lab, pid, "archived")


def delete_project(lab: Lab, pid: str, confirm: bool = False) -> None:
    """Delete is only safe for empty drafts — anything with research
    data must be archived instead (history stays auditable)."""
    d = project_dir(lab, pid)
    meta = ProjectMeta.load(d)
    has_data = any(any((d / sub).glob("*")) for sub in ENTITY_DIRS)
    if meta.status != "draft" or has_data:
        raise LabError(
            f"project '{pid}' holds research data — archive it instead "
            "(`lab project archive`). Deletion is only for empty drafts.")
    if not confirm:
        raise LabError("pass --confirm to delete a project")
    import shutil
    shutil.rmtree(d)


# ---------- generic entity helpers ----------


def _entity_dir(lab: Lab, pid: str, kind: str) -> Path:
    return project_dir(lab, pid) / kind


def _load_all(lab: Lab, pid: str, kind: str, cls) -> list:
    d = _entity_dir(lab, pid, kind)
    out = []
    if d.is_dir():
        for p in sorted(d.glob("*.yaml")):
            out.append(cls(**load_yaml(p)))
    return out


def _load_one(lab: Lab, pid: str, kind: str, eid: str, cls):
    p = _entity_dir(lab, pid, kind) / f"{check_id(kind, eid)}.yaml"
    if not p.is_file():
        raise LabError(f"{kind[:-1].title()} '{eid}' not found in "
                       f"project '{pid}'.")
    return cls(**load_yaml(p)), p


# ---------- questions ----------


def add_question(lab: Lab, pid: str, text: str, objective: str = "",
                 hypothesis: str = "") -> ResearchQuestion:
    d = _entity_dir(lab, pid, "questions")
    q = ResearchQuestion(id=_next_id(d, "q"), question=text,
                         objective=objective, hypothesis=hypothesis,
                         created=date.today().isoformat())
    dump_yaml(q.model_dump(mode="json"), d / f"{q.id}.yaml")
    return q


def list_questions(lab: Lab, pid: str) -> list[ResearchQuestion]:
    return _load_all(lab, pid, "questions", ResearchQuestion)


def set_question_status(lab: Lab, pid: str, qid: str,
                        status: str) -> None:
    q, p = _load_one(lab, pid, "questions", qid, ResearchQuestion)
    q.status = status
    dump_yaml(q.model_dump(mode="json"), p)


def link_question(lab: Lab, pid: str, qid: str, field: str,
                  ref: str) -> None:
    """Attach a finding/experiment ref to a question (findings=|
    experiments= fields)."""
    if field not in ("findings", "experiments"):
        raise LabError("can only link 'findings' or 'experiments'")
    q, p = _load_one(lab, pid, "questions", qid, ResearchQuestion)
    if field == "findings":
        _load_one(lab, pid, "findings", ref, ResearchFinding)
    elif not (lab.experiments_dir / ref / "experiment.yaml").is_file():
        raise LabError(f"experiment '{ref}' not found in this lab")
    lst = getattr(q, field)
    if ref not in lst:
        lst.append(ref)
        dump_yaml(q.model_dump(mode="json"), p)


# ---------- sources ----------


def add_source(lab: Lab, pid: str, stype: str, title: str,
               url: str = "", path: str = "", author: str = "",
               excerpt: str = "") -> ResearchSource:
    if stype == "url" and not url:
        raise LabError("source type 'url' requires --url")
    if stype == "doc" and path and not Path(path).is_file():
        raise LabError(f"source document '{path}' not found")
    d = _entity_dir(lab, pid, "sources")
    s = ResearchSource(id=_next_id(d, "s"), type=stype, title=title,
                       url=url, path=path, author=author,
                       accessed=date.today().isoformat(),
                       excerpt=excerpt)
    dump_yaml(s.model_dump(mode="json"), d / f"{s.id}.yaml")
    return s


def list_sources(lab: Lab, pid: str) -> list[ResearchSource]:
    return _load_all(lab, pid, "sources", ResearchSource)


def annotate_source(lab: Lab, pid: str, sid: str, note: str) -> None:
    s, p = _load_one(lab, pid, "sources", sid, ResearchSource)
    s.annotations.append(note)
    dump_yaml(s.model_dump(mode="json"), p)


# ---------- notes ----------


def add_note(lab: Lab, pid: str, title: str) -> Path:
    d = _entity_dir(lab, pid, "notes")
    p = d / f"{_slug(title)}.md"
    if p.exists():
        raise LabError(f"note '{p.stem}' already exists")
    p.write_text(NOTE_TEMPLATE.format(nid=p.stem,
                                      today=date.today().isoformat()))
    return p


def list_notes(lab: Lab, pid: str) -> list[dict]:
    d = _entity_dir(lab, pid, "notes")
    out = []
    if d.is_dir():
        for p in sorted(d.glob("*.md")):
            fm, _ = parse_frontmatter(p.read_text())
            out.append({"id": fm.get("id", p.stem),
                        "created": fm.get("created", ""),
                        "tags": fm.get("tags", []),
                        "path": str(p)})
    return out


# ---------- findings ----------


def add_finding(lab: Lab, pid: str, statement: str, kind: str,
                question: str = "", confidence: str = "low",
                sources: list[str] | None = None,
                evidence: list[str] | None = None,
                limitations: str = "") -> ResearchFinding:
    if question:
        _load_one(lab, pid, "questions", question, ResearchQuestion)
    for sid in sources or []:
        _load_one(lab, pid, "sources", sid, ResearchSource)
    for ref in evidence or []:
        if not _evidence_exists(lab, ref):
            raise LabError(f"evidence '{ref}' is not an experiment or "
                           "run in this lab")
    d = _entity_dir(lab, pid, "findings")
    f = ResearchFinding(id=_next_id(d, "f"), statement=statement,
                        kind=kind, question=question,
                        confidence=confidence, sources=sources or [],
                        evidence=evidence or [], limitations=limitations,
                        created=date.today().isoformat())
    dump_yaml(f.model_dump(mode="json"), d / f"{f.id}.yaml")
    return f


def _evidence_exists(lab: Lab, ref: str) -> bool:
    return ((lab.experiments_dir / ref / "experiment.yaml").is_file()
            or (lab.runs_dir / ref / "run.yaml").is_file())


def list_findings(lab: Lab, pid: str) -> list[ResearchFinding]:
    return _load_all(lab, pid, "findings", ResearchFinding)


def set_finding_status(lab: Lab, pid: str, fid: str,
                       status: str) -> None:
    """`supported` is evidence-gated: needs ≥1 real source or
    experiment/run link, and `unverified` kind can never be
    promoted to supported."""
    f, p = _load_one(lab, pid, "findings", fid, ResearchFinding)
    if status == "supported":
        if f.kind == "unverified":
            raise LabError(
                f"finding '{fid}' is kind=unverified — mark an "
                "evidence kind (verified-source/observation/ai-hypothesis)"
                " before it can be supported")
        if not f.sources and not f.evidence:
            raise LabError(
                f"finding '{fid}' has no sources or experiment evidence "
                "— supported status requires a real evidence link")
    f.status = status
    dump_yaml(f.model_dump(mode="json"), p)


# ---------- decisions ----------


def add_decision(lab: Lab, pid: str, decision: str, rationale: str = "",
                 alternatives: list[str] | None = None) -> ResearchDecision:
    d = _entity_dir(lab, pid, "decisions")
    dec = ResearchDecision(id=_next_id(d, "d"), decision=decision,
                           rationale=rationale,
                           alternatives=alternatives or [],
                           created=date.today().isoformat())
    dump_yaml(dec.model_dump(mode="json"), d / f"{dec.id}.yaml")
    return dec


def list_decisions(lab: Lab, pid: str) -> list[ResearchDecision]:
    return _load_all(lab, pid, "decisions", ResearchDecision)


def set_decision_status(lab: Lab, pid: str, did: str,
                        status: str) -> None:
    dec, p = _load_one(lab, pid, "decisions", did, ResearchDecision)
    dec.status = status
    dump_yaml(dec.model_dump(mode="json"), p)


# ---------- summaries ----------


def project_summary(lab: Lab, pid: str) -> dict:
    """Counts for dashboards / `project show`."""
    meta = get_project(lab, pid)
    return {
        "meta": meta,
        "questions": list_questions(lab, pid),
        "sources": list_sources(lab, pid),
        "findings": list_findings(lab, pid),
        "decisions": list_decisions(lab, pid),
        "notes": list_notes(lab, pid),
    }
