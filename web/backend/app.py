"""SkillLab Web API — Phase 1 foundation.

Read-mostly slice: exposes the existing lab's domain objects over REST.
Business logic lives in skilllab/* — routes only serialize it.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from skilllab.lab import Lab, LabError

LAB_DIR = Path(os.environ.get("SKILLLAB_DIR", "examples/demo-lab"))

app = FastAPI(title="SkillLab API", version="0.1.0")


def lab() -> Lab:
    root = Path(os.environ.get("SKILLLAB_DIR", str(LAB_DIR)))
    if not (root / "lab.yaml").is_file():
        raise HTTPException(503, f"no lab at {root} — set SKILLLAB_DIR")
    return Lab(root)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/projects")
def projects(l: Lab = Depends(lab)):
    from skilllab.research import list_projects
    return [p.model_dump(mode="json") for p in list_projects(l)]


@app.get("/api/v1/projects/{pid}")
def project(pid: str, l: Lab = Depends(lab)):
    from skilllab import research
    try:
        p = research.get_project(l, pid)
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"meta": p.model_dump(mode="json"),
            "questions": [q.model_dump(mode="json")
                          for q in research.list_questions(l, pid)],
            "findings": [f.model_dump(mode="json")
                         for f in research.list_findings(l, pid)]}


@app.get("/api/v1/skills")
def skills(l: Lab = Depends(lab)):
    return [m.model_dump(mode="json") for m in l.skills()]


@app.get("/api/v1/experiments")
def experiments(l: Lab = Depends(lab)):
    from skilllab.models import Experiment
    d = l.experiments_dir
    if not d.is_dir():
        return []
    return [Experiment.load(x).model_dump(mode="json")
            for x in sorted(d.iterdir()) if (x / "experiment.yaml").is_file()]


@app.get("/api/v1/releases")
def releases(l: Lab = Depends(lab)):
    from skilllab.release import list_releases
    return [r.model_dump(mode="json") for r in list_releases(l)]


@app.get("/api/v1/trace/{ref}")
def trace(ref: str, l: Lab = Depends(lab)):
    from skilllab.release import trace as do_trace
    try:
        return do_trace(l, ref)
    except LabError as e:
        raise HTTPException(404, str(e))
