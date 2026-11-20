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


# ---------------- auth (single-user token) ----------------

import secrets
from fastapi import Header
from pydantic import BaseModel

_TOKEN = os.environ.get("SKILLLAB_TOKEN", "")
if not _TOKEN:
    _TOKEN = secrets.token_urlsafe(24)
    import sys
    print(f"[skilllab-web] dev token (set SKILLLAB_TOKEN to fix): "
          f"{_TOKEN}", file=sys.stderr)


def auth(authorization: str = Header(default="")) -> None:
    if authorization != f"Bearer {_TOKEN}":
        raise HTTPException(401, "missing/invalid bearer token")


class ProjectIn(BaseModel):
    id: str
    title: str = ""
    objective: str = ""


class QuestionIn(BaseModel):
    text: str
    objective: str = ""
    hypothesis: str = ""


class FindingIn(BaseModel):
    statement: str
    kind: str = "observation"
    confidence: str = "low"
    question: str = ""
    sources: list[str] = []
    evidence: list[str] = []


class BpFieldIn(BaseModel):
    fields: dict = {}


class GenerateIn(BaseModel):
    skill: str
    variant: str
    format: str = "skill-md"
    force: bool = False


# ---------------- research write ----------------

@app.post("/api/v1/projects", dependencies=[Depends(auth)])
def new_project(body: ProjectIn, l: Lab = Depends(lab)):
    from skilllab import research
    try:
        research.new_project(l, body.id, body.title, body.objective)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"id": body.id}


@app.post("/api/v1/projects/{pid}/questions",
          dependencies=[Depends(auth)])
def new_question(pid: str, body: QuestionIn, l: Lab = Depends(lab)):
    from skilllab import research
    try:
        q = research.add_question(l, pid, body.text, body.objective,
                                  body.hypothesis)
    except LabError as e:
        raise HTTPException(404, str(e))
    return q.model_dump(mode="json")


@app.post("/api/v1/projects/{pid}/findings",
          dependencies=[Depends(auth)])
def new_finding(pid: str, body: FindingIn, l: Lab = Depends(lab)):
    from skilllab import research
    try:
        f = research.add_finding(l, pid, body.statement, kind=body.kind,
                                 confidence=body.confidence,
                                 question=body.question,
                                 sources=body.sources,
                                 evidence=body.evidence)
    except LabError as e:
        raise HTTPException(404, str(e))
    return f.model_dump(mode="json")


# ---------------- blueprints ----------------

@app.get("/api/v1/projects/{pid}/blueprints")
def blueprints(pid: str, l: Lab = Depends(lab)):
    from skilllab import blueprint
    return [b.model_dump(mode="json")
            for b in blueprint.list_blueprints(l, pid)]


@app.post("/api/v1/projects/{pid}/blueprints/{bid}/fields",
          dependencies=[Depends(auth)])
def bp_set(pid: str, bid: str, body: BpFieldIn, l: Lab = Depends(lab)):
    from skilllab import blueprint
    try:
        for k, v in body.fields.items():
            blueprint.set_field(l, pid, bid, k, v)
    except LabError as e:
        raise HTTPException(400, str(e))
    return blueprint.get_blueprint(l, pid, bid).model_dump(mode="json")


@app.get("/api/v1/projects/{pid}/blueprints/{bid}/validate")
def bp_validate(pid: str, bid: str, l: Lab = Depends(lab)):
    from skilllab import blueprint
    return blueprint.validate(l, pid, bid)


@app.post("/api/v1/projects/{pid}/blueprints/{bid}/generate",
          dependencies=[Depends(auth)])
def bp_generate(pid: str, bid: str, body: GenerateIn,
                l: Lab = Depends(lab)):
    from skilllab import studio
    try:
        out = studio.generate_skill(l, pid, bid, body.skill,
                                    body.variant, body.format,
                                    body.force)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"path": str(out)}


# ---------------- studio / ai / failure / release ----------------

@app.get("/api/v1/skills/{ref}/preview")
def preview(ref: str, l: Lab = Depends(lab)):
    from skilllab import studio
    try:
        return studio.preview(l, ref)
    except LabError as e:
        raise HTTPException(404, str(e))


@app.get("/api/v1/skills/{ref}/check")
def check(ref: str, l: Lab = Depends(lab)):
    from skilllab import studio
    return studio.validate_skill(l, ref)


@app.post("/api/v1/skills/{ref}/proposals", dependencies=[Depends(auth)])
def suggest(ref: str, l: Lab = Depends(lab)):
    from skilllab import architect
    return [p.model_dump(mode="json") for p in architect.suggest(l, ref)]


@app.get("/api/v1/proposals")
def proposals(l: Lab = Depends(lab)):
    from skilllab import architect
    return [p.model_dump(mode="json") for p in architect.list_proposals(l)]


@app.post("/api/v1/proposals/{pid}/approve", dependencies=[Depends(auth)])
def approve(pid: str, l: Lab = Depends(lab)):
    from skilllab import architect
    architect.set_status(l, pid, "approved")
    return {"id": pid, "status": "approved"}


@app.post("/api/v1/proposals/{pid}/apply", dependencies=[Depends(auth)])
def apply_prop(pid: str, l: Lab = Depends(lab)):
    from skilllab import architect
    try:
        out = architect.apply(l, pid)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"applied": str(out)}


@app.get("/api/v1/failures")
def failures(l: Lab = Depends(lab)):
    d = l.d("failures")
    if not d.is_dir():
        return []
    from skilllab.models import load_yaml
    return [load_yaml(p) for p in sorted(d.glob("*.yaml"))]


@app.post("/api/v1/failures/{run_id}", dependencies=[Depends(auth)])
def analyze(run_id: str, l: Lab = Depends(lab)):
    from skilllab import failure
    try:
        rep = failure.analyze_run(l, run_id)
        rep["proposals"] = failure.proposals(rep)
        failure.write_report(l, rep)
    except LabError as e:
        raise HTTPException(404, str(e))
    return rep


@app.get("/api/v1/releases/{skill}/{version}/check")
def rel_check(skill: str, version: str, l: Lab = Depends(lab)):
    from skilllab import release
    try:
        return release.check(l, skill, version)
    except LabError as e:
        raise HTTPException(404, str(e))


# ---------------- web explorer ----------------

class SearchIn(BaseModel):
    query: str
    limit: int = 10


class FetchIn(BaseModel):
    url: str


@app.post("/api/v1/web-search", dependencies=[Depends(auth)])
def web_search(body: SearchIn, l: Lab = Depends(lab)):
    from skilllab import webio
    try:
        return webio.search(l, body.query, body.limit)
    except LabError as e:
        raise HTTPException(502, str(e))


@app.post("/api/v1/web-fetch", dependencies=[Depends(auth)])
def web_fetch(body: FetchIn):
    from skilllab import webio
    try:
        return webio.fetch(body.url)
    except LabError as e:
        raise HTTPException(400, str(e))


class SaveIn(BaseModel):
    url: str


@app.post("/api/v1/projects/{pid}/sources/from-url",
          dependencies=[Depends(auth)])
def source_from_url(pid: str, body: SaveIn, l: Lab = Depends(lab)):
    from skilllab import webio
    try:
        return webio.save_source(l, pid, webio.fetch(body.url))
    except LabError as e:
        raise HTTPException(400, str(e))


class AnnotIn(BaseModel):
    note: str


@app.post("/api/v1/projects/{pid}/sources/{sid}/annotate",
          dependencies=[Depends(auth)])
def annotate(pid: str, sid: str, body: AnnotIn, l: Lab = Depends(lab)):
    from skilllab import research
    try:
        research.annotate_source(l, pid, sid, body.note)
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"id": sid, "annotated": True}


# ---------------- deep research ----------------

class DrIn(BaseModel):
    objective: str
    plan: dict | None = None


@app.post("/api/v1/projects/{pid}/research",
          dependencies=[Depends(auth)])
def dr_start(pid: str, body: DrIn, l: Lab = Depends(lab)):
    from skilllab import deep
    rd = deep.start(l, pid, body.objective, body.plan)
    return {"id": rd.name, "state": deep.get(rd)}


@app.post("/api/v1/research/{pid}/{rid}/run",
          dependencies=[Depends(auth)])
def dr_run(pid: str, rid: str, l: Lab = Depends(lab)):
    from skilllab import deep
    rd = deep.runs_dir(l, pid) / rid
    if not (rd / "run.yaml").is_file():
        raise HTTPException(404, "research run not found")
    deep.approve(rd)
    try:
        return deep.execute(l, pid, rd, log=lambda m: None)
    except LabError as e:
        raise HTTPException(502, str(e))


@app.get("/api/v1/research/{pid}/{rid}")
def dr_get(pid: str, rid: str, l: Lab = Depends(lab)):
    from skilllab import deep
    rd = deep.runs_dir(l, pid) / rid
    if not (rd / "run.yaml").is_file():
        raise HTTPException(404, "research run not found")
    st = deep.get(rd)
    rep = rd / "report.md"
    if rep.is_file():
        st["report_md"] = rep.read_text()
    return st


@app.post("/api/v1/experiments/{eid}/run", dependencies=[Depends(auth)])
def run_exp(eid: str, l: Lab = Depends(lab)):
    from skilllab.engine import run_experiment
    try:
        recs = run_experiment(l, eid)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"runs": [r.run_id for r in recs],
            "count": len(recs),
            "note": "synchronous — fine for mock; real models need "
                    "the worker queue"}


@app.get("/api/v1/runs")
def runs(l: Lab = Depends(lab)):
    from skilllab.models import RunRecord, load_yaml
    d = l.runs_dir
    if not d.is_dir():
        return []
    out = []
    for rd in sorted(d.iterdir()):
        ry = rd / "run.yaml"
        if ry.is_file():
            out.append(RunRecord(**load_yaml(ry)).model_dump(mode="json"))
    return out[-100:]



class NoteIn(BaseModel):
    title: str


@app.post("/api/v1/projects/{pid}/notes", dependencies=[Depends(auth)])
def add_note(pid: str, body: NoteIn, l: Lab = Depends(lab)):
    from skilllab import research
    try:
        p = research.add_note(l, pid, body.title)
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"path": str(p)}


class StatusIn(BaseModel):
    status: str


@app.post("/api/v1/projects/{pid}/findings/{fid}/status",
          dependencies=[Depends(auth)])
def finding_status(pid: str, fid: str, body: StatusIn,
                   l: Lab = Depends(lab)):
    from skilllab import research
    try:
        research.set_finding_status(l, pid, fid, body.status)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"id": fid, "status": body.status}


from fastapi import UploadFile


@app.post("/api/v1/projects/{pid}/sources/upload",
          dependencies=[Depends(auth)])
async def upload(pid: str, file: UploadFile, l: Lab = Depends(lab)):
    """md/txt/html document upload -> text extract -> project source."""
    from skilllab import research
    name = file.filename or "doc"
    if not name.lower().endswith(
            (".md", ".txt", ".html", ".htm", ".docx", ".pdf")):
        raise HTTPException(400,
                            "supported: md/txt/html/docx/pdf")
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "file >2MB")
    if name.lower().endswith((".docx", ".pdf")):
        import tempfile
        from skilllab import webio
        with tempfile.NamedTemporaryFile(
                suffix=name[name.rfind("."):], delete=False) as tf:
            tf.write(raw)
            tmp = tf.name
        try:
            text = webio.extract_doc(tmp)
        except LabError as e:
            raise HTTPException(400, str(e))
    else:
        text = raw.decode("utf-8", "replace")
    if name.lower().endswith((".html", ".htm")):
        import re as _re
        text = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text,
                       flags=_re.S | _re.I)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _re.sub(r"\s+", " ", text).strip()
    try:
        s = research.add_source(l, pid, "note", name,
                                excerpt=text[:400])
    except LabError as e:
        raise HTTPException(404, str(e))
    d = research.project_dir(l, pid) / "sources" / "_uploads"
    d.mkdir(exist_ok=True)
    (d / name).write_text(text)
    return {"source": s.model_dump(mode="json"),
            "stored": str(d / name)}


@app.get("/api/v1/research/{pid}/{rid}/stream")
def dr_stream(pid: str, rid: str, l: Lab = Depends(lab)):
    """SSE: stream run.yaml state while the job executes in a thread.
    Polls the state file every 0.5s — no fabricated progress."""
    import json, threading, time
    from fastapi.responses import StreamingResponse
    from skilllab import deep
    rd = deep.runs_dir(l, pid) / rid
    if not (rd / "run.yaml").is_file():
        raise HTTPException(404, "research run not found")

    st = deep.get(rd)
    if st["status"] in ("planned", "approved", "failed"):
        deep.approve(rd)
        threading.Thread(
            target=lambda: _safe_execute(l, pid, rd),
            daemon=True).start()

    def gen():
        last = ""
        for _ in range(7200):          # hard cap ~1h
            cur = json.dumps(deep.get(rd))
            if cur != last:
                last = cur
                yield f"data: {cur}\n\n"
            st = deep.get(rd)["status"]
            if st in ("completed", "failed"):
                rep = rd / "report.md"
                if rep.is_file():
                    yield ("data: " + json.dumps(
                        {"status": st,
                         "report_md": rep.read_text()}) + "\n\n")
                return
            time.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream")


def _safe_execute(l, pid, rd):
    from skilllab import deep
    try:
        deep.execute(l, pid, rd, log=lambda m: None)
    except Exception:
        pass


# ---------------- run inspection + evaluation ----------------

def _run_dir(l: Lab, rid: str) -> Path:
    rd = l.runs_dir / rid
    if not (rd / "run.yaml").is_file():
        raise HTTPException(404, f"run '{rid}' not found")
    return rd


@app.get("/api/v1/runs/{rid}")
def run_detail(rid: str, l: Lab = Depends(lab)):
    """Full run detail: record + eval + transcript + artifacts + any
    persisted failure analysis. Read-only — mirrors `lab ui` run pages."""
    import json
    from skilllab.models import EvalResult, RunRecord, load_yaml
    rd = _run_dir(l, rid)
    rec = RunRecord(**load_yaml(rd / "run.yaml"))
    out = {"run": rec.model_dump(mode="json")}
    ey = rd / "eval.yaml"
    if ey.is_file():
        out["eval"] = EvalResult(**load_yaml(ey)).model_dump(mode="json")
    tp = rd / "transcript.jsonl"
    if tp.is_file():
        msgs = []
        for line in tp.read_text().splitlines():
            try:
                msgs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(msgs) >= 500:
                out["transcript_truncated"] = True
                break
        out["transcript"] = msgs
    ws = rd / "workspace"
    if ws.is_dir():
        out["artifacts"] = sorted(
            str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file())
    frep = l.d("failures") / f"{rid}.yaml"
    if frep.is_file():
        out["failure"] = load_yaml(frep)
    return out


@app.get("/api/v1/runs/{rid}/artifact")
def run_artifact(rid: str, path: str, l: Lab = Depends(lab)):
    rd = _run_dir(l, rid)
    ws = (rd / "workspace").resolve()
    f = (ws / path).resolve()
    if not f.is_file() or f == ws or ws not in f.parents:
        raise HTTPException(404, "artifact not found")
    if f.stat().st_size > 200_000:
        raise HTTPException(413, "artifact >200KB")
    return {"path": path, "text": f.read_text(errors="replace")}


class EvalIn(BaseModel):
    scores: dict[str, float] = {}
    comments: dict[str, str] = {}


@app.post("/api/v1/runs/{rid}/eval", dependencies=[Depends(auth)])
def run_eval(rid: str, body: EvalIn, l: Lab = Depends(lab)):
    """`lab eval` over HTTP: scores present -> fill human criteria and
    recompute; empty -> re-run deterministic/judge checks."""
    from skilllab.evaluate import apply_human_scores, evaluate_run
    from skilllab.models import RunRecord, load_yaml
    rd = _run_dir(l, rid)
    rec = RunRecord(**load_yaml(rd / "run.yaml"))
    try:
        task = l.task(rec.task)
        ev = (apply_human_scores(l, rec, task, rd, body.scores,
                                 body.comments)
              if body.scores else evaluate_run(l, rec, task, rd))
    except LabError as e:
        raise HTTPException(409, str(e))
    return ev.model_dump(mode="json")


@app.get("/api/v1/experiments/{eid}/compare")
def exp_compare(eid: str, l: Lab = Depends(lab)):
    """Structured arm x task score matrix — same data as
    `lab compare`, shaped for tables instead of markdown."""
    import statistics
    from skilllab.report import load_runs
    try:
        exp = l.experiment(eid)
    except LabError as e:
        raise HTTPException(404, str(e))
    cells: dict[tuple[str, str], list[float]] = {}
    tasks: list[str] = []
    for rec, ev in load_runs(l, eid):
        if rec.status == "error" or not ev \
                or ev.status not in ("passed", "failed"):
            continue
        s = ev.rubric_score if ev.rubric_score is not None else (
            1.0 if ev.status == "passed" else 0.0)
        cells.setdefault((rec.arm, rec.task), []).append(s)
        if rec.task not in tasks:
            tasks.append(rec.task)
    arms = []
    for a in exp.arms:
        row = {"name": a.name, "skill": a.skill, "cells": {}}
        for t in tasks:
            xs = cells.get((a.name, t), [])
            if xs:
                row["cells"][t] = {
                    "n": len(xs), "mean": statistics.mean(xs),
                    "stdev": statistics.pstdev(xs) if len(xs) > 1 else 0.0}
        arms.append(row)
    return {"experiment": eid, "tasks": tasks, "arms": arms}


@app.get("/api/v1/experiments/{eid}/report")
def exp_report(eid: str, l: Lab = Depends(lab)):
    from skilllab.report import build_report
    try:
        exp = l.experiment(eid)
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"experiment": eid, "markdown": build_report(l, exp)}


# ---- production: serve the built SPA from the same port -------------
# NOTE: must stay LAST — a `/{path:path}` GET registered earlier would
# shadow every /api/v1 GET route defined below it.

_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    from fastapi.responses import FileResponse

    @app.get("/{path:path}", include_in_schema=False)
    def spa_catchall(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (_DIST / path).resolve()
        if f.is_file() and _DIST in f.parents:
            return FileResponse(f)
        return FileResponse(_DIST / "index.html")  # client routing
