"""SkillLab Web API — Phase 1 foundation.

Read-mostly slice: exposes the existing lab's domain objects over REST.
Business logic lives in skilllab/* — routes only serialize it.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from skilllab.lab import Lab, LabError, check_id

LAB_DIR = Path(os.environ.get("SKILLLAB_DIR", "examples/demo-lab"))

app = FastAPI(title="SkillLab API", version="0.1.0")


@app.exception_handler(LabError)
def _lab_error_handler(_req, exc: LabError):
    """Catch-all for domain errors outside per-endpoint try blocks —
    invalid ids/inputs surface as 400, never as a bare 500."""
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": str(exc)}, status_code=400)


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
        s = research.project_summary(l, pid)
    except LabError as e:
        raise HTTPException(404, str(e))
    out = {}
    for k, v in s.items():
        if isinstance(v, list):
            out[k] = [x.model_dump(mode="json")
                      if hasattr(x, "model_dump") else x for x in v]
        else:
            out[k] = v.model_dump(mode="json") \
                if hasattr(v, "model_dump") else v
    return out


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
_ENV = os.environ.get("SKILLLAB_ENV", "development").lower()
if not _TOKEN:
    if _ENV == "production":
        raise RuntimeError(
            "SKILLLAB_TOKEN is required in production — refusing to "
            "start with an auto-generated credential")
    _TOKEN = secrets.token_urlsafe(24)
    import sys
    print(f"[skilllab-web] dev token (set SKILLLAB_TOKEN to fix): "
          f"{_TOKEN}", file=sys.stderr)
_REQUIRE = f"Bearer {_TOKEN}"


def _ok(header: str) -> bool:
    # constant-time compare on the full header value
    return secrets.compare_digest(header.encode(), _REQUIRE.encode())


def auth(authorization: str = Header(default="")) -> None:
    if not _ok(authorization):
        raise HTTPException(401, "missing/invalid bearer token")


# ---- global guards -------------------------------------------------
# every /api/* route requires the bearer token (incl. GET streams);
# only the health probe stays open for Docker/monitors.
from fastapi import Request
from fastapi.responses import JSONResponse

_PUBLIC = {"/api/v1/health"}


@app.middleware("http")
async def guards(request: Request, call_next):
    p = request.url.path
    if p.startswith("/api/") and p not in _PUBLIC:
        if not _ok(request.headers.get("authorization", "")):
            return JSONResponse({"detail": "missing/invalid bearer token"},
                                status_code=401)
        if len(p) > 2048:
            return JSONResponse({"detail": "url too long"}, 414)
        rl = _rate_limit(request)
        if rl is not None:
            return rl
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if p.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


# simple fixed-window rate limiter for expensive endpoints (per-token
# isn't meaningful here — single-user lab; bound global concurrency)
import threading, time as _time

_RL = {"lock": threading.Lock(), "buckets": {}}
_RL_RULES = {                       # prefix -> (max_calls, window_s)
    "/api/v1/web-search": (10, 60),
    "/api/v1/web-fetch": (10, 60),
    "/api/v1/research/": (4, 60),          # deep-research streams
    "/api/v1/skills/import": (6, 60),
    "/api/v1/import": (6, 60),
}
_RL_DEFAULT_RUN = (12, 60)          # experiment run/retry POSTs


def _rate_limit(request: Request):
    if request.method != "POST":
        return None
    p = request.url.path
    cap = None
    for prefix, rule in _RL_RULES.items():
        if p.startswith(prefix):
            cap = rule
            break
    if cap is None and ("/run" in p or p.endswith("/proposals")):
        cap = _RL_DEFAULT_RUN
    if cap is None:
        return None
    now = _time.monotonic()
    key = p.split("?")[0]
    with _RL["lock"]:
        n, t0 = _RL["buckets"].get(key, (0, now))
        if now - t0 > cap[1]:
            n, t0 = 0, now
        if n >= cap[0]:
            return JSONResponse(
                {"detail": "rate limited — retry later"}, 429)
        _RL["buckets"][key] = (n + 1, t0)
    return None


# CORS — same-origin SPA needs none; dev uses the vite proxy. Origins
# are explicit, never "*", and only when SKILLLAB_CORS_ORIGINS is set.
from fastapi.middleware.cors import CORSMiddleware
_origins = [o.strip() for o in os.environ.get(
    "SKILLLAB_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins,
                   allow_methods=["GET", "POST", "PUT", "DELETE"],
                   allow_headers=["authorization", "content-type"],
                   max_age=600)


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


# ---------------- skill file editor (Skill Studio) -----------------

def _variant_file(l: Lab, ref: str, rel: str) -> Path:
    """Resolve a file inside a variant dir — both segments contained."""
    from skilllab.models import parse_skill_ref
    sid, vid = parse_skill_ref(ref)
    vdir = l.variant_dir(sid, vid).resolve()
    p = (vdir / rel).resolve()
    if not p.is_relative_to(vdir) or p.is_symlink():
        raise HTTPException(400, "path escapes the variant dir")
    return p


def _vdir(l: Lab, ref: str) -> Path:
    from skilllab.models import parse_skill_ref
    sid, vid = parse_skill_ref(ref)
    return l.variant_dir(sid, vid).resolve()


@app.get("/api/v1/skills/{ref}/files")
def skill_files(ref: str, l: Lab = Depends(lab)):
    """File tree for the in-browser editor: path/size/sha per file."""
    import hashlib
    vdir = _vdir(l, ref)
    out = []
    for p in sorted(vdir.rglob("*")):
        if p.is_file() and not p.is_symlink() \
                and "revisions" not in p.relative_to(vdir).parts:
            out.append({"path": str(p.relative_to(vdir)),
                        "bytes": p.stat().st_size,
                        "sha": hashlib.sha256(
                            p.read_bytes()).hexdigest()[:12]})
    return {"variant": ref, "files": out}


@app.get("/api/v1/skills/{ref}/file")
def skill_file_read(ref: str, path: str, l: Lab = Depends(lab)):
    import hashlib
    p = _variant_file(l, ref, path)
    if not p.is_file():
        raise HTTPException(404, "file not found")
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(415, "binary file — not editable")
    return {"path": path, "text": text,
            "sha": hashlib.sha256(raw).hexdigest()[:12]}


class FileWriteIn(BaseModel):
    path: str
    text: str
    base_sha: str = ""               # optimistic concurrency check


@app.put("/api/v1/skills/{ref}/file", dependencies=[Depends(auth)])
def skill_file_write(ref: str, body: FileWriteIn, l: Lab = Depends(lab)):
    """Save a variant file. `base_sha` must match the current hash —
    a stale buffer never silently overwrites someone else's edit.
    Every write snapshots the previous content under revisions/."""
    import hashlib
    from datetime import datetime
    p = _variant_file(l, ref, body.path)
    if len(body.text.encode()) > 2_000_000:
        raise HTTPException(413, "file >2MB")
    old = p.read_bytes() if p.exists() else None
    cur = hashlib.sha256(old).hexdigest()[:12] if old else ""
    if body.base_sha != cur:
        raise HTTPException(
            409, f"stale buffer — file changed (have {cur or 'none'}, "
            f"sent {body.base_sha or 'none'}); reload and retry")
    if old is not None:
        rev = _vdir(l, ref) / "revisions" / (
            datetime.now().strftime("%Y%m%d-%H%M%S") + "-" +
            body.path.replace("/", "__"))
        rev.parent.mkdir(parents=True, exist_ok=True)
        rev.write_bytes(old)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.text)
    return {"path": body.path,
            "sha": hashlib.sha256(p.read_bytes()).hexdigest()[:12],
            "revision": old is not None}


# ---------------- revisions (Skill Editor history) ------------------

def _rev_dir(l: Lab, ref: str) -> Path:
    return _vdir(l, ref) / "revisions"


@app.get("/api/v1/skills/{ref}/revisions")
def skill_revisions(ref: str, path: str, l: Lab = Depends(lab)):
    """List snapshots for one file, newest first."""
    rd = _rev_dir(l, ref)
    stem = path.replace("/", "__")
    out = []
    if rd.is_dir():
        for p in sorted(rd.glob(f"*-{stem}"), reverse=True):
            if p.is_file() and not p.is_symlink():
                out.append({"rev": p.name[:15], "file": p.name,
                            "bytes": p.stat().st_size,
                            "ts": p.name[:15]})
    return {"path": path, "revisions": out}


@app.get("/api/v1/skills/{ref}/revision")
def skill_revision_read(ref: str, path: str, rev: str,
                        l: Lab = Depends(lab)):
    """Read one snapshot — never writable through this route."""
    fname = f"{rev}-{path.replace('/', '__')}"
    p = (_rev_dir(l, ref) / fname).resolve()
    if not p.is_relative_to(_rev_dir(l, ref).resolve()) \
            or not p.is_file():
        raise HTTPException(404, "revision not found")
    try:
        return {"path": path, "rev": rev, "text": p.read_text()}
    except UnicodeDecodeError:
        raise HTTPException(415, "binary revision")


class RestoreIn(BaseModel):
    path: str
    rev: str
    base_sha: str = ""


@app.post("/api/v1/skills/{ref}/restore", dependencies=[Depends(auth)])
def skill_revision_restore(ref: str, body: RestoreIn,
                           l: Lab = Depends(lab)):
    """Restore a snapshot into the file. The CURRENT content is first
    snapshotted itself — restore is an edit, never a history rewrite."""
    import hashlib
    from datetime import datetime
    src = skill_revision_read(ref, body.path, body.rev, l)["text"]
    p = _variant_file(l, ref, body.path)
    old = p.read_bytes() if p.exists() else b""
    cur = hashlib.sha256(old).hexdigest()[:12] if old else ""
    if body.base_sha != cur:
        raise HTTPException(409, f"file changed since you loaded it "
                           f"(current {cur or 'none'})")
    rd = _rev_dir(l, ref)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" +
           body.path.replace("/", "__"))).write_bytes(old)
    p.write_text(src)
    return {"path": body.path, "restored_from": body.rev,
            "sha": hashlib.sha256(p.read_bytes()).hexdigest()[:12]}


@app.delete("/api/v1/skills/{ref}/file", dependencies=[Depends(auth)])
def skill_file_delete(ref: str, path: str, l: Lab = Depends(lab)):
    """Delete a file — snapshots it first (recoverable via revisions)."""
    from datetime import datetime
    p = _variant_file(l, ref, path)
    if not p.is_file():
        raise HTTPException(404, "file not found")
    if p.name == "SKILL.md":
        raise HTTPException(400, "SKILL.md is the variant entry — "
                            "edit it, don't delete it")
    rd = _rev_dir(l, ref)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" +
           path.replace("/", "__"))).write_bytes(p.read_bytes())
    p.unlink()
    return {"deleted": path}


class RenameIn(BaseModel):
    path: str
    to: str


@app.post("/api/v1/skills/{ref}/rename", dependencies=[Depends(auth)])
def skill_file_rename(ref: str, body: RenameIn, l: Lab = Depends(lab)):
    """Move/rename a file inside the variant. Both sides pass the same
    containment checks; the old content is snapshotted under the new
    name (rename = delete + create in the audit log)."""
    from datetime import datetime
    src = _variant_file(l, ref, body.path)
    dst = _variant_file(l, ref, body.to)
    if not src.is_file():
        raise HTTPException(404, f"'{body.path}' not found")
    if src.name == "SKILL.md" or dst.name == "SKILL.md":
        raise HTTPException(400, "SKILL.md is the variant entry — "
                            "its name is fixed")
    if dst.exists():
        raise HTTPException(409, f"'{body.to}' already exists")
    if "revisions" in dst.relative_to(
            _vdir(l, ref)).parts:
        raise HTTPException(400, "cannot rename into revisions/")
    rd = _rev_dir(l, ref)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" +
           body.to.replace("/", "__"))).write_bytes(src.read_bytes())
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return {"renamed": body.path, "to": body.to}


@app.post("/api/v1/skills/{ref}/proposals", dependencies=[Depends(auth)])
def suggest(ref: str, l: Lab = Depends(lab), llm: bool = False):
    """Deterministic patch proposals; ?llm=true asks the lab model for
    full-file rewrites (refused when model=mock). Same approval gate."""
    from skilllab import architect
    try:
        props = architect.suggest(l, ref, use_llm=llm)
    except LabError as e:
        raise HTTPException(409, str(e))
    return [p.model_dump(mode="json") for p in props]


@app.get("/api/v1/proposals")
def proposals(l: Lab = Depends(lab)):
    from skilllab import architect
    return [p.model_dump(mode="json") for p in architect.list_proposals(l)]


@app.post("/api/v1/proposals/{pid}/approve", dependencies=[Depends(auth)])
def approve(pid: str, l: Lab = Depends(lab)):
    from skilllab import architect
    try:
        architect.set_status(l, pid, "approved")
    except LabError as e:
        raise HTTPException(404, str(e))
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
        release.list_releases(l, skill)          # 404 when absent
        return release.checklist(l, skill, version)
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
    from skilllab.lab import check_id
    rd = deep.runs_dir(l, pid) / check_id("run", rid)
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
    from skilllab.lab import check_id
    rd = deep.runs_dir(l, pid) / check_id("run", rid)
    if not (rd / "run.yaml").is_file():
        raise HTTPException(404, "research run not found")
    st = deep.get(rd)
    rep = rd / "report.md"
    if rep.is_file():
        st["report_md"] = rep.read_text()
    return st


def _preflight(l: Lab, eid: str, arm=None, limit=None, batch=None,
               model=None, force=False):
    """Synchronous validation for a run — raises HTTPException on any
    condition that must stop execution before a job is enqueued."""
    import re
    from skilllab.engine import (planned_run_ids,
                                 validate_experiment)
    try:
        exp = l.experiment(eid)
    except LabError as e:
        raise HTTPException(404, str(e))
    if exp.status == "concluded":
        raise HTTPException(409, f"experiment '{eid}' is concluded "
                               "(immutable) — start a new experiment")
    errors, warns = validate_experiment(l, exp)
    if errors:
        raise HTTPException(409, "experiment invalid: "
                               + "; ".join(errors))
    if model and model != exp.fixed.model and not batch:
        batch = re.sub(r"[^a-z0-9-]+", "-", model.lower())[:40]
    planned = planned_run_ids(exp, arm, limit, batch)
    existing = [r for r in planned
                if (l.runs_dir / r / "run.yaml").is_file()]
    if existing and not force:
        raise HTTPException(
            409, f"{len(existing)}/{len(planned)} planned run(s) exist "
                 f"(e.g. {existing[0]}) — use batch or force")
    return exp, batch, planned, warns


@app.post("/api/v1/experiments/{eid}/run", dependencies=[Depends(auth)])
def run_exp(eid: str, l: Lab = Depends(lab)):
    """Enqueue `lab run` as a background job — returns the job id;
    progress via GET /api/v1/jobs/{id} (count is real rollouts done)."""
    exp, batch, planned, _ = _preflight(l, eid)

    def work(job):
        _exec_runs(l, eid, None, None, batch, None, False,
                   job=job, total=len(planned))
    j = _jobs(l).submit("experiment-run", f"exp:{eid}:{batch or ''}",
                        work)
    return {"job": j["id"], "status": j["status"],
            "planned": len(planned)}


@app.get("/api/v1/runs")
def runs(l: Lab = Depends(lab)):
    from skilllab.models import RunRecord, load_yaml
    d = l.runs_dir
    if not d.is_dir():
        return []
    out = []
    for rd in sorted(d.iterdir(),
                     key=lambda p: (p / "run.yaml").stat().st_mtime
                     if (p / "run.yaml").is_file() else 0):
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
    if body.status not in ("candidate", "supported", "refuted",
                           "inconclusive"):
        raise HTTPException(400, "status must be candidate|supported|"
                               "refuted|inconclusive")
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
    name = Path(file.filename or "doc").name     # strip client dirs
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
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                    suffix=name[name.rfind("."):],
                    delete=False) as tf:
                tf.write(raw)
                tmp = tf.name
            text = webio.extract_doc(tmp)
        except LabError as e:
            raise HTTPException(400, str(e))
        finally:
            if tmp:
                Path(tmp).unlink(missing_ok=True)
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
    from skilllab.lab import check_id
    rd = deep.runs_dir(l, pid) / check_id("run", rid)
    if not (rd / "run.yaml").is_file():
        raise HTTPException(404, "research run not found")

    # GET streams only OBSERVE — execution starts via POST .../run
    st = deep.get(rd)

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


@app.post("/api/v1/research/{pid}/{rid}/run", dependencies=[Depends(auth)])
def deep_run_start(pid: str, rid: str, l: Lab = Depends(lab)):
    """Start (or resume) a research run through the job queue — one
    active job per run dir, resumable via deep's persisted state."""
    from skilllab import deep
    from skilllab.lab import check_id
    rd = deep.runs_dir(l, pid) / check_id("run", rid)
    if not (rd / "run.yaml").is_file():
        raise HTTPException(404, "research run not found")
    st = deep.get(rd)
    if st["status"] == "completed":
        return {"id": rid, "status": "completed", "job": None}
    if st["status"] in ("planned", "failed"):
        deep.approve(rd)

    def work(job):
        deep.execute(l, pid, rd, log=job.log)
    j = _jobs(l).submit("deep-research", f"{pid}/{rid}", work)
    return {"id": rid, "status": "running", "job": j["id"]}


# ---------------- background jobs ----------------

def _jobs(l: Lab):
    """Lazily-created per-lab job store (SQLite under <lab>/jobs/)."""
    global _JOB_STORES
    try:
        _JOB_STORES
    except NameError:
        _JOB_STORES = {}
    k = str(l.root)
    if k not in _JOB_STORES:
        from .jobs import Jobs
        _JOB_STORES[k] = Jobs(l.d("jobs") / "jobs.sqlite")
    return _JOB_STORES[k]


@app.get("/api/v1/jobs")
def jobs_list(l: Lab = Depends(lab)):
    return _jobs(l).list()


@app.get("/api/v1/jobs/{jid}")
def jobs_get(jid: str, l: Lab = Depends(lab)):
    j = _jobs(l).get(jid)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@app.post("/api/v1/jobs/{jid}/cancel", dependencies=[Depends(auth)])
def jobs_cancel(jid: str, l: Lab = Depends(lab)):
    j = _jobs(l).get(jid)
    if not j:
        raise HTTPException(404, "job not found")
    return _jobs(l).cancel(jid)


# ---------------- run inspection + evaluation ----------------

def _run_dir(l: Lab, rid: str) -> Path:
    from skilllab.lab import check_id
    rd = l.runs_dir / check_id("run", rid)
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
    from skilllab.lab import check_id
    frep = l.d("failures") / f"{check_id('run', rid)}.yaml"
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


# ---------------- quality report (module 4) ----------------

@app.get("/api/v1/report/{skill}/{variant}")
def quality_report(skill: str, variant: str, format: str = "json",
                   l: Lab = Depends(lab)):
    """Assembled evidence report for one skill variant — the agency
    deliverable: config, score matrix, regressions, release checklist,
    verdict. `?format=md` returns a markdown file for export."""
    import statistics
    from skilllab.models import load_yaml
    from skilllab.release import checklist, variant_hash
    from skilllab.report import load_runs
    ref = f"{skill}@{variant}"
    try:
        l.variant_dir(skill, variant)
    except LabError as e:
        raise HTTPException(404, str(e))
    vhash = variant_hash(l, skill, variant)

    # --- experiments where this variant is an arm ---
    exps = []
    all_exps = [l.experiment(x.name)
                for x in sorted(l.experiments_dir.iterdir())
                if (x / "experiment.yaml").is_file()] \
        if l.experiments_dir.is_dir() else []
    for e in all_exps:
        arm_names = [a.name for a in e.arms if a.skill == ref]
        if not arm_names:
            continue
        # per-arm mean; delta computed only over tasks both arms ran
        cells: dict[tuple[str, str], list[float]] = {}
        for rec, ev in load_runs(l, e.id):
            if rec.status == "error" or not ev \
                    or ev.status not in ("passed", "failed"):
                continue
            s = ev.rubric_score if ev.rubric_score is not None else (
                1.0 if ev.status == "passed" else 0.0)
            cells.setdefault((rec.arm, rec.task), []).append(s)
        def _mean(a, t):
            xs = cells.get((a, t))
            return statistics.mean(xs) if xs else None
        tasks = sorted({t for (_, t) in cells})
        arms = {}
        for a in e.arms:
            xs = [x for (an, _), lst in cells.items() if an == a.name
                  for x in lst]
            if xs:
                arms[a.name] = {"skill": a.skill,
                                "mean": statistics.mean(xs), "n": len(xs)}
        ctrl = next((a for a in e.arms if not a.skill), None)
        entry = {"experiment": e.id, "title": e.title,
                 "status": e.status, "model": e.fixed.model,
                 "injection_mode": e.fixed.injection_mode,
                 "tasks": tasks, "arms": arms}
        an = arm_names[0]
        if ctrl and an in arms and ctrl.name in arms:
            ds = [_mean(an, t) - _mean(ctrl.name, t) for t in tasks
                  if _mean(an, t) is not None
                  and _mean(ctrl.name, t) is not None]
            if ds:
                entry["delta_vs_control"] = round(
                    statistics.mean(ds), 3)
                entry["shared_tasks"] = len(ds)
        exps.append(entry)

    # --- regressions touching this variant ---
    from skilllab.regression import list_regressions
    regs = [r for r in list_regressions(l)
            if r.get("skill") == skill and variant in
            (r.get("baseline"), r.get("candidate"))]
    for r in regs:
        rp = l.d("regressions") / r["id"] / "report.yaml"
        if rp.is_file():
            r["report"] = load_yaml(rp)

    # --- releases for this variant ---
    rels = []
    rdir = l.d("releases") / skill
    if rdir.is_dir():
        for f in sorted(rdir.glob("*.yaml")):
            r = load_yaml(f)
            if r.get("variant") == variant:
                rels.append({"version": r.get("version"),
                             "status": r.get("status"),
                             "released_at": r.get("released_at"),
                             "checklist": checklist(
                                 l, skill, r["version"])})

    mock = l.cfg.get("model") == "mock" or all(
        e["model"] == "mock" for e in exps) if exps else \
        l.cfg.get("model") == "mock"
    report = {
        "skill": skill, "variant": variant, "content_hash": vhash,
        "generated": __import__("datetime").datetime.now()
        .astimezone().isoformat(timespec="seconds"),
        "experiments": exps, "regressions": regs, "releases": rels,
        "simulated": bool(mock),
        "verdict": _report_verdict(exps, regs, rels),
    }
    if format == "md":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            _report_markdown(report),
            media_type="text/markdown",
            headers={"Content-Disposition":
                     f'attachment; filename="{skill}-{variant}-report.md"'})
    return report


def _report_verdict(exps, regs, rels):
    """Deterministic plain-language verdict — no invented confidence."""
    deltas = [e["delta_vs_control"] for e in exps
              if "delta_vs_control" in e]
    regressed = [r for r in regs
                 if (r.get("report") or {}).get("verdict") == "regressed"]
    released = any(r["status"] == "released" for r in rels)
    if regressed:
        return {"label": "regressed",
                "text": f"{len(regressed)} regression suite(s) report a "
                        "regression for this variant."}
    if deltas:
        d = sum(deltas) / len(deltas)
        label = "improved" if d > 0.02 else ("degraded" if d < -0.02
                                             else "neutral")
        return {"label": label,
                "text": f"Mean delta vs control across {len(deltas)} "
                        f"experiment(s): {d:+.3f}."
                        + (" Released." if released else "")}
    clean = [r for r in regs
             if (r.get("report") or {}).get("verdict") == "clean"]
    if clean or released:
        return {"label": "validated",
                "text": f"{len(clean)} clean regression suite(s)"
                        + (" and a passed release checklist"
                           if released else "") + " for this variant."}
    return {"label": "insufficient-evidence",
            "text": "No completed benchmark evidence for this variant "
                    "yet — run a benchmark first."}


def _report_markdown(r):
    lines = [f"# Quality Report — {r['skill']}@{r['variant']}",
             f"Generated: {r['generated']} · Content hash: "
             f"`{r['content_hash']}`", ""]
    if r["simulated"]:
        lines.append("> **Simulated data** — benchmarks ran under "
                     "`model: mock`. Not real model evidence.")
        lines.append("")
    v = r["verdict"]
    lines += [f"## Verdict: {v['label']}", "", v["text"], ""]
    if r["experiments"]:
        lines += ["## Benchmark results", "",
                  "| Experiment | Arm | Mean score | n | Δ vs control |",
                  "|---|---|---|---|---|"]
        for e in r["experiments"]:
            for an, a in e["arms"].items():
                lines.append(
                    f"| {e['experiment']} | {an} | {a['mean']:.3f} | "
                    f"{a['n']} | "
                    f"{e.get('delta_vs_control', '—') if a['skill'] else 'control'} |")
        lines.append("")
    if r["regressions"]:
        lines += ["## Regression suites", "",
                  "| Suite | Baseline → Candidate | Verdict |",
                  "|---|---|---|"]
        for rg in r["regressions"]:
            verdict = (rg.get("report") or {}).get("verdict",
                                                  rg.get("verdict") or "—")
            lines.append(f"| {rg['id']} | {rg.get('baseline')} → "
                         f"{rg.get('candidate')} | {verdict} |")
        lines.append("")
    if r["releases"]:
        lines += ["## Release checklist", ""]
        for rel in r["releases"]:
            lines.append(f"### v{rel['version']} — {rel['status']}")
            for c in rel.get("checklist", []):
                lines.append(f"- [{'x' if c['ok'] else ' '}] "
                             f"{c['id']} — {c.get('detail', '')}")
            lines.append("")
    return "\n".join(lines)


# ---------------- knowledge base: insights + principles ----------------

@app.get("/api/v1/insights")
def insights(l: Lab = Depends(lab)):
    """Insights AND promoted principles — `kind` field distinguishes."""
    from skilllab.insights import list_insights
    return list_insights(l)


@app.get("/api/v1/insights/{iid}")
def insight_detail(iid: str, l: Lab = Depends(lab)):
    from skilllab.models import parse_frontmatter
    for d, kind in ((l.insights_dir, "insight"),
                    (l.principles_dir, "principle")):
        p = d / f"{iid}.md"
        if p.is_file():
            fm, body = parse_frontmatter(p.read_text())
            return {"id": fm.get("id", p.stem), "kind": kind,
                    "frontmatter": fm, "body": body}
    raise HTTPException(404, f"insight '{iid}' not found")


class InsightIn(BaseModel):
    title: str
    evidence: str = ""


@app.post("/api/v1/insights", dependencies=[Depends(auth)])
def insight_new(body: InsightIn, l: Lab = Depends(lab)):
    from skilllab.insights import new_insight
    try:
        p = new_insight(l, body.title, body.evidence)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"path": str(p)}


@app.post("/api/v1/insights/{iid}/{action}", dependencies=[Depends(auth)])
def insight_action(iid: str, action: str, l: Lab = Depends(lab)):
    """confirm (needs valid evidence refs) / refute / promote (gated on
    >=2 independent experiments, scope, no TODOs — enforced server-side)."""
    from skilllab import insights as ins
    fn = {"confirm": ins.confirm, "refute": ins.refute,
          "promote": ins.promote}.get(action)
    if fn is None:
        raise HTTPException(
            400, f"unknown action '{action}' — confirm|refute|promote")
    try:
        p = fn(l, iid)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"id": iid, "action": action, "path": str(p)}


# ---------------- regressions ----------------

@app.get("/api/v1/regressions")
def regressions(l: Lab = Depends(lab)):
    from skilllab.regression import list_regressions
    return list_regressions(l)


@app.get("/api/v1/regressions/{rid}")
def regression_detail(rid: str, l: Lab = Depends(lab)):
    from skilllab.models import load_yaml
    from skilllab.lab import check_id
    d = l.d("regressions") / check_id("regression", rid)
    if not (d / "regression.yaml").is_file():
        raise HTTPException(404, f"regression '{rid}' not found")
    out = {"meta": load_yaml(d / "regression.yaml")}
    ry = d / "report.yaml"
    if ry.is_file():
        out["report"] = load_yaml(ry)
    rm = d / "report.md"
    if rm.is_file():
        out["markdown"] = rm.read_text()
    return out


class RegIn(BaseModel):
    skill: str
    baseline: str
    candidate: str
    tasks: str = "default"           # all|default|<suite>|<csv ids>
    model: str | None = None
    mode: str | None = None          # available | injected
    rollouts: int | None = None
    thresholds: dict[str, float] = {}


@app.post("/api/v1/regressions", dependencies=[Depends(auth)])
def regression_run(body: RegIn, l: Lab = Depends(lab)):
    from skilllab.regression import run_regression, resolve_tasks
    if body.mode is not None and body.mode not in ("available", "injected"):
        raise HTTPException(400, "mode must be 'available' or 'injected'")
    try:
        l.skill(body.skill)
        l.variant_dir(body.skill, body.baseline)
        l.variant_dir(body.skill, body.candidate)
        n_tasks = len(resolve_tasks(l, body.tasks))
    except LabError as e:
        raise HTTPException(409, str(e))
    n_roll = body.rollouts or int(l.cfg["rollouts_per_arm"])
    planned = 2 * n_tasks * min(n_roll, int(l.cfg["rollouts_per_arm"])) \
        if body.rollouts else 2 * n_tasks * n_roll

    def work(job):
        def progress(done, total):
            job.progress(done / max(total, 1),
                         f"rollout {done}/{total}")
        return run_regression(
            l, body.skill, body.baseline, body.candidate, body.tasks,
            model=body.model, mode=body.mode, rollouts=body.rollouts,
            overrides=body.thresholds or None, progress=progress,
            should_stop=lambda: job.cancelled)

    key = f"reg:{body.skill}:{body.baseline}:{body.candidate}:{body.tasks}"
    j = _jobs(l).submit("regression-run", key, work)
    return {"job": j["id"], "status": j["status"], "planned": planned}


# ---------------- releases: create + lifecycle ----------------

class ReleaseIn(BaseModel):
    skill: str
    version: str
    variant: str                     # "v3-bp" or full "skill@v3-bp"
    changelog: str = ""


@app.post("/api/v1/releases", dependencies=[Depends(auth)])
def release_new(body: ReleaseIn, l: Lab = Depends(lab)):
    from skilllab.release import new_release
    try:
        p = new_release(l, body.skill, body.version, body.variant,
                        body.changelog)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"path": str(p)}


@app.get("/api/v1/releases/{skill}/{version}")
def release_detail(skill: str, version: str, l: Lab = Depends(lab)):
    from skilllab.release import checklist, list_releases
    r = next((r for r in list_releases(l, skill)
              if r.version == version), None)
    if r is None:
        raise HTTPException(404, f"release '{skill}@{version}' not found")
    return {"release": r.model_dump(mode="json"),
            "checklist": checklist(l, skill, version)}


@app.post("/api/v1/releases/{skill}/{version}/status",
          dependencies=[Depends(auth)])
def release_status(skill: str, version: str, body: StatusIn,
                   l: Lab = Depends(lab)):
    from skilllab.release import set_status
    valid = {"draft", "candidate", "validated", "released", "deprecated"}
    if body.status not in valid:
        raise HTTPException(
            400, f"status must be one of {sorted(valid)}")
    try:
        set_status(l, skill, version, body.status)   # 'released' gated
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"skill": skill, "version": version, "status": body.status}


# ---------------- research lifecycle + entities ----------------

_PROJECT_STATUSES = ("draft", "active", "researching", "designing",
                     "developing", "experimenting", "validating",
                     "completed", "archived")


@app.post("/api/v1/projects/{pid}/status", dependencies=[Depends(auth)])
def project_status(pid: str, body: StatusIn, l: Lab = Depends(lab)):
    from skilllab import research
    if body.status not in _PROJECT_STATUSES:
        raise HTTPException(
            400, f"status must be one of {_PROJECT_STATUSES}")
    try:
        research.get_project(l, pid)
        research.set_status(l, pid, body.status)
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"id": pid, "status": body.status}


class ConfirmIn(BaseModel):
    confirm: bool = False


@app.post("/api/v1/projects/{pid}/delete", dependencies=[Depends(auth)])
def project_delete(pid: str, body: ConfirmIn, l: Lab = Depends(lab)):
    """Deletion is only safe for empty drafts — data-bearing projects
    must be archived instead (archive-over-delete policy)."""
    from skilllab import research
    try:
        research.delete_project(l, pid, confirm=body.confirm)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"id": pid, "deleted": True}


_QUESTION_STATUSES = ("open", "investigating", "answered", "deferred")


@app.post("/api/v1/projects/{pid}/questions/{qid}/status",
          dependencies=[Depends(auth)])
def question_status(pid: str, qid: str, body: StatusIn,
                    l: Lab = Depends(lab)):
    from skilllab import research
    if body.status not in _QUESTION_STATUSES:
        raise HTTPException(
            400, f"status must be one of {_QUESTION_STATUSES}")
    try:
        research.set_question_status(l, pid, qid, body.status)
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"id": qid, "status": body.status}


class LinkIn(BaseModel):
    field: str                       # findings | experiments
    ref: str


@app.post("/api/v1/projects/{pid}/questions/{qid}/link",
          dependencies=[Depends(auth)])
def question_link(pid: str, qid: str, body: LinkIn,
                  l: Lab = Depends(lab)):
    from skilllab import research
    try:
        research.link_question(l, pid, qid, body.field, body.ref)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"id": qid, "field": body.field, "ref": body.ref}


class SourceIn(BaseModel):
    type: str = "other"              # url|doc|note|paper|other
    title: str
    url: str = ""
    path: str = ""
    author: str = ""
    excerpt: str = ""


@app.post("/api/v1/projects/{pid}/sources", dependencies=[Depends(auth)])
def source_add(pid: str, body: SourceIn, l: Lab = Depends(lab)):
    from skilllab import research
    if body.type not in ("url", "doc", "note", "paper", "other"):
        raise HTTPException(400, "type must be url|doc|note|paper|other")
    try:
        s = research.add_source(l, pid, body.type, body.title,
                                url=body.url, path=body.path,
                                author=body.author, excerpt=body.excerpt)
    except LabError as e:
        raise HTTPException(409, str(e))
    return s.model_dump(mode="json")


class DecisionIn(BaseModel):
    decision: str
    rationale: str = ""
    alternatives: list[str] = []


@app.post("/api/v1/projects/{pid}/decisions", dependencies=[Depends(auth)])
def decision_add(pid: str, body: DecisionIn, l: Lab = Depends(lab)):
    from skilllab import research
    try:
        d = research.add_decision(l, pid, body.decision, body.rationale,
                                  body.alternatives)
    except LabError as e:
        raise HTTPException(404, str(e))
    return d.model_dump(mode="json")


_DECISION_STATUSES = ("proposed", "accepted", "rejected", "superseded")


@app.post("/api/v1/projects/{pid}/decisions/{did}/status",
          dependencies=[Depends(auth)])
def decision_status(pid: str, did: str, body: StatusIn,
                    l: Lab = Depends(lab)):
    from skilllab import research
    if body.status not in _DECISION_STATUSES:
        raise HTTPException(
            400, f"status must be one of {_DECISION_STATUSES}")
    try:
        research.set_decision_status(l, pid, did, body.status)
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"id": did, "status": body.status}


# ---------------- blueprint lifecycle ----------------

class BpIn(BaseModel):
    id: str
    title: str = ""


@app.post("/api/v1/projects/{pid}/blueprints",
          dependencies=[Depends(auth)])
def bp_new(pid: str, body: BpIn, l: Lab = Depends(lab)):
    from skilllab import blueprint, research
    try:
        research.get_project(l, pid)
    except LabError as e:
        raise HTTPException(404, str(e))
    try:
        d = blueprint.new_blueprint(l, pid, body.id, body.title)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"path": str(d)}


_BP_STATUSES = ("draft", "designing", "ready_for_generation",
                "generated", "testing", "improving", "validated",
                "released", "archived")


@app.post("/api/v1/projects/{pid}/blueprints/{bid}/status",
          dependencies=[Depends(auth)])
def bp_status(pid: str, bid: str, body: StatusIn, l: Lab = Depends(lab)):
    """Statuses beyond `designing` are gated on `blueprint validate`
    (enforced server-side, same as CLI)."""
    from skilllab import blueprint
    if body.status not in _BP_STATUSES:
        raise HTTPException(400, f"status must be one of {_BP_STATUSES}")
    try:
        bp = blueprint.set_status(l, pid, bid, body.status)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"id": bid, "status": bp.status, "rev": bp.rev}


class FromQIn(BaseModel):
    qid: str


@app.post("/api/v1/projects/{pid}/blueprints/{bid}/from-question",
          dependencies=[Depends(auth)])
def bp_from_q(pid: str, bid: str, body: FromQIn, l: Lab = Depends(lab)):
    from skilllab import blueprint
    try:
        bp = blueprint.from_question(l, pid, bid, body.qid)
    except LabError as e:
        raise HTTPException(404, str(e))
    return bp.model_dump(mode="json")


class LinkFindingIn(BaseModel):
    finding: str


@app.post("/api/v1/projects/{pid}/blueprints/{bid}/link",
          dependencies=[Depends(auth)])
def bp_link(pid: str, bid: str, body: LinkFindingIn,
            l: Lab = Depends(lab)):
    from skilllab import blueprint
    try:
        blueprint.link_finding(l, pid, bid, body.finding)
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"id": bid, "linked": body.finding}


@app.post("/api/v1/projects/{pid}/blueprints/{bid}/draft",
          dependencies=[Depends(auth)])
def bp_draft(pid: str, bid: str, l: Lab = Depends(lab)):
    """Deterministic prefill of empty fields from project research."""
    from skilllab import blueprint
    try:
        touched = blueprint.draft_from_research(l, pid, bid)
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"id": bid, "touched": touched}


@app.get("/api/v1/projects/{pid}/blueprints/{bid}/revisions")
def bp_revisions(pid: str, bid: str, l: Lab = Depends(lab)):
    from skilllab import blueprint
    try:
        revs = blueprint.revisions(l, pid, bid)
    except LabError as e:
        raise HTTPException(404, str(e))
    return [{"rev": b.rev, "status": b.status, "updated": b.updated,
             "title": b.title} for b in revs]


@app.get("/api/v1/projects/{pid}/blueprints/{bid}/diff")
def bp_diff(pid: str, bid: str, from_rev: int, to_rev: int | None = None,
            l: Lab = Depends(lab)):
    from skilllab import blueprint
    try:
        return {"diffs": blueprint.diff_revisions(l, pid, bid, from_rev,
                                                  to_rev)}
    except LabError as e:
        raise HTTPException(404, str(e))


@app.get("/api/v1/projects/{pid}/blueprints/{bid}/drift")
def bp_drift(pid: str, bid: str, ref: str, l: Lab = Depends(lab)):
    """On-disk artifact vs fresh emit — synced | drifted + unified diff."""
    from skilllab import studio
    try:
        return studio.artifact_diff(l, pid, bid, ref)
    except LabError as e:
        raise HTTPException(404, str(e))


class BpExpIn(BaseModel):
    skill: str
    variant: str
    exp_id: str | None = None


@app.post("/api/v1/projects/{pid}/blueprints/{bid}/experiment",
          dependencies=[Depends(auth)])
def bp_experiment(pid: str, bid: str, body: BpExpIn,
                  l: Lab = Depends(lab)):
    """Scaffold task-bank entries + two-arm experiment from scope lists.
    Draft tasks ship without checks — evals stay incomplete until
    authored (honest scaffolding, no fabricated evidence)."""
    from skilllab import blueprint
    try:
        exp_id, created, skipped = blueprint.experiment_from_blueprint(
            l, pid, bid, body.skill, body.variant, body.exp_id)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"experiment": exp_id, "tasks_created": created,
            "tasks_skipped": skipped}


# ---------------- skills: registry ops + studio ----------------

class SkillIn(BaseModel):
    id: str
    kind: str = "skill-md"


@app.post("/api/v1/skills", dependencies=[Depends(auth)])
def skill_new(body: SkillIn, l: Lab = Depends(lab)):
    from skilllab.registry import new_skill
    try:
        d = new_skill(l, body.id, body.kind)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"path": str(d)}


class ImportIn(BaseModel):
    src: str                         # git URL[#subdir] or lab-relative dir


def _lab_path(l: Lab, s: str, base: str) -> Path:
    """Resolve a lab-relative import path — the web never accepts
    arbitrary server paths, only dirs under <lab>/<base>/."""
    cand = (l.d(base) / s).resolve()
    if not cand.is_relative_to(l.d(base).resolve()) or not cand.is_dir():
        raise HTTPException(
            400, f"path must be a directory under <lab>/{base}/")
    return cand


@app.post("/api/v1/skills/import", dependencies=[Depends(auth)])
def skill_import(body: ImportIn, l: Lab = Depends(lab)):
    from skilllab.registry import add_skill
    src = body.src
    if not re.match(r"^(https://|ssh://|git@|git://)", src):
        src = str(_lab_path(l, src, "imports"))   # staged imports only
    try:
        d = add_skill(l, src)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"path": str(d)}


@app.get("/api/v1/skill-scan")
def skill_scan(l: Lab = Depends(lab)):
    """Discover skills in well-known agent dirs (no import)."""
    from skilllab.registry import scan_skill_dirs, skill_entry_file
    from skilllab.models import parse_frontmatter
    out = []
    for d in scan_skill_dirs():
        entry = skill_entry_file(d)
        fm = parse_frontmatter(entry.read_text())[0] if entry else {}
        out.append({"path": str(d), "name": fm.get("name") or d.name})
    return out


@app.post("/api/v1/skills/{ref}/resources", dependencies=[Depends(auth)])
async def skill_resource(ref: str, file: UploadFile,
                         l: Lab = Depends(lab)):
    """Upload a file into the variant's resources/ (progressive
    disclosure — referenced from SKILL.md on demand)."""
    import tempfile
    from skilllab import studio
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "file >2MB")
    name = Path(file.filename or "resource").name   # strip client dirs
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / name
        src.write_bytes(raw)
        try:
            dest = studio.add_resource(l, ref, str(src))
        except LabError as e:
            raise HTTPException(404, str(e))
    return {"path": str(dest)}


@app.get("/api/v1/skills/{sid}/graduation")
def skill_graduation(sid: str, l: Lab = Depends(lab)):
    """`lab skill evaluate` — activation/false-activation/delta verdicts."""
    import dataclasses
    from skilllab.graduation import evaluate_skill
    try:
        rep = evaluate_skill(l, sid)
    except LabError as e:
        raise HTTPException(404, str(e))
    return dataclasses.asdict(rep)


# ---------------- experiments: ops ----------------

class IdIn(BaseModel):
    id: str


class ExpIn(BaseModel):
    id: str
    category: str = "trigger"
    config: dict | None = None      # full Experiment Builder payload


@app.post("/api/v1/experiments", dependencies=[Depends(auth)])
def exp_new(body: ExpIn, l: Lab = Depends(lab)):
    """Create an experiment — either a scaffold (id only) or a full
    config from the Experiment Builder (`config` object)."""
    import datetime
    from skilllab.cli import EXP_TEMPLATE
    from skilllab.models import ExpCategory, Experiment
    if body.category not in ExpCategory.__args__:
        raise HTTPException(400, f"invalid category '{body.category}' — "
                            f"one of {list(ExpCategory.__args__)}")
    check_id("experiment", body.id)
    d = l.experiments_dir / body.id
    if (d / "experiment.yaml").is_file():
        raise HTTPException(409, f"experiment '{body.id}' already exists")
    d.mkdir(parents=True, exist_ok=True)
    if body.config:
        try:
            exp = Experiment(**{**body.config, "id": body.id})
        except Exception as e:
            raise HTTPException(400, f"invalid experiment config: {e}")
        exp.save(d)
        return {"path": str(d / "experiment.yaml"), "id": body.id}
    (d / "experiment.yaml").write_text(EXP_TEMPLATE.format(
        eid=body.id, model=l.cfg["model"],
        n=l.cfg["rollouts_per_arm"], cat=body.category,
        today=datetime.date.today().isoformat()))
    return {"path": str(d / "experiment.yaml"), "id": body.id}


@app.get("/api/v1/experiments/{eid}")
def exp_get(eid: str, l: Lab = Depends(lab)):
    """Full experiment config + run stats for the Builder detail view."""
    from skilllab.report import load_runs
    try:
        exp = l.experiment(eid)
    except LabError as e:
        raise HTTPException(404, str(e))
    runs = load_runs(l, eid)
    return {"experiment": exp.model_dump(mode="json"),
            "n_runs": len(runs),
            "n_evaluated": sum(1 for _, e in runs
                               if e and e.status in ("passed", "failed"))}


@app.put("/api/v1/experiments/{eid}/config", dependencies=[Depends(auth)])
def exp_config(eid: str, body: dict, l: Lab = Depends(lab)):
    """Replace experiment.yaml with the Builder's config. Pydantic +
    domain validation run server-side; concluded experiments are
    immutable. Returns the post-save validation result."""
    from skilllab.engine import validate_experiment
    from skilllab.models import Experiment
    try:
        cur = l.experiment(eid)
    except LabError as e:
        raise HTTPException(404, str(e))
    if cur.status == "concluded":
        raise HTTPException(409, "concluded experiments are immutable")
    try:
        exp = Experiment(**{**body, "id": eid,
                            "status": cur.status,
                            "conclusion": cur.conclusion,
                            "insights_generated":
                                cur.insights_generated})
    except Exception as e:
        raise HTTPException(400, f"invalid experiment config: {e}")
    exp.save(l.exp_dir(eid))
    errors, warns = validate_experiment(l, exp)
    return {"id": eid, "valid": not errors,
            "errors": errors, "warnings": warns}


@app.post("/api/v1/experiments/{eid}/duplicate",
          dependencies=[Depends(auth)])
def exp_duplicate(eid: str, body: IdIn, l: Lab = Depends(lab)):
    """Copy an experiment's config to a new id (status resets to
    designed; runs are never copied)."""
    from skilllab.models import Experiment
    try:
        exp = l.experiment(eid)
    except LabError as e:
        raise HTTPException(404, str(e))
    check_id("experiment", body.id)
    d = l.experiments_dir / body.id
    if (d / "experiment.yaml").is_file():
        raise HTTPException(409, f"experiment '{body.id}' exists")
    d.mkdir(parents=True, exist_ok=True)
    data = exp.model_dump(mode="json")
    data.update(id=body.id, status="designed", conclusion=None,
                insights_generated=[])
    Experiment(**data).save(d)
    return {"id": body.id}


@app.get("/api/v1/experiments/{eid}/validate")
def exp_validate(eid: str, l: Lab = Depends(lab)):
    from skilllab.engine import validate_experiment
    try:
        exp = l.experiment(eid)
    except LabError as e:
        raise HTTPException(404, str(e))
    errors, warnings = validate_experiment(l, exp)
    return {"experiment": eid, "valid": not errors,
            "errors": errors, "warnings": warnings}


@app.get("/api/v1/experiments/{eid}/runs")
def exp_runs(eid: str, l: Lab = Depends(lab)):
    from skilllab.report import load_runs
    try:
        l.experiment(eid)
    except LabError as e:
        raise HTTPException(404, str(e))
    return [{"run": r.model_dump(mode="json"),
             "eval": e.model_dump(mode="json") if e else None}
            for r, e in load_runs(l, eid)]


def _exec_runs(l: Lab, eid: str, arm: str | None, limit: int | None,
               batch: str | None, model: str | None,
               force: bool, job=None, total: int | None = None) -> dict:
    """Shared run/rerun driver — mirrors `lab run`/`rerun`. When `job`
    is given (worker thread), each rollout logs progress + checks
    cancellation; without it the call stays synchronous (CLI parity)."""
    from skilllab.engine import run_rollout
    from skilllab.evaluate import evaluate_run
    exp, batch, planned, warns = _preflight(
        l, eid, arm, limit, batch, model, force)
    exp.status = "running"
    exp.save(l.exp_dir(exp.id))
    if model:
        exp.fixed.model = model  # in-memory only — after save (config kept)
    recs = []
    total = total or len(planned)
    done = 0
    for a in exp.arms:
        if arm and a.name != arm:
            continue
        for tid in exp.tasks:
            n = min(limit, exp.rollouts_per_arm) if limit \
                else exp.rollouts_per_arm
            for i in range(n):
                if job:
                    job.progress(done / max(total, 1),
                                 f"{a.name}/{tid} r{i}")
                rec = run_rollout(l, exp, a, tid, i, batch,
                                  overwrite=force)
                try:
                    evaluate_run(l, rec, l.task(tid),
                                 l.runs_dir / rec.run_id)
                except Exception:
                    pass                # recorded, doesn't kill batch
                recs.append(rec.run_id)
                done += 1
                if job:
                    job.log(f"run {rec.run_id}")
    if job:
        job.progress(1.0, f"{done} rollouts")
    return {"runs": recs, "count": len(recs), "batch": batch,
            "warnings": warns}


class RerunIn(BaseModel):
    arm: str | None = None
    limit: int | None = None
    model: str | None = None
    batch: str | None = None
    force: bool = False


@app.post("/api/v1/experiments/{eid}/rerun", dependencies=[Depends(auth)])
def exp_rerun(eid: str, body: RerunIn, l: Lab = Depends(lab)):
    """`lab rerun` as a background job — batch suffix keeps history
    append-only; --model auto-batches for drift probes."""
    exp, batch, planned, _ = _preflight(
        l, eid, body.arm, body.limit, body.batch, body.model,
        body.force)

    def work(job):
        _exec_runs(l, eid, body.arm, body.limit, batch, body.model,
                   body.force, job=job, total=len(planned))
    j = _jobs(l).submit("experiment-run",
                        f"exp:{eid}:{batch or body.arm or ''}", work)
    return {"job": j["id"], "status": j["status"],
            "planned": len(planned), "batch": batch}


class ConcludeIn(BaseModel):
    conclusion: str
    insights: list[str] = []


@app.post("/api/v1/experiments/{eid}/conclude",
          dependencies=[Depends(auth)])
def exp_conclude(eid: str, body: ConcludeIn, l: Lab = Depends(lab)):
    try:
        exp = l.experiment(eid)
    except LabError as e:
        raise HTTPException(404, str(e))
    exp.status = "concluded"
    exp.conclusion = body.conclusion
    for i in body.insights:
        if i not in exp.insights_generated:
            exp.insights_generated.append(i)
    exp.save(l.exp_dir(exp.id))
    return {"id": eid, "status": "concluded",
            "insights": exp.insights_generated}


@app.get("/api/v1/diff/{a}/{b}")
def run_diff(a: str, b: str, l: Lab = Depends(lab)):
    """`lab diff` — transcript flow + workspace file-set comparison."""
    import difflib
    import json
    dirs = [l.runs_dir / r for r in (a, b)]
    for d, rid in zip(dirs, (a, b)):
        if not (d / "run.yaml").is_file():
            raise HTTPException(404, f"run '{rid}' not found")

    def norm(run_dir: Path) -> list[str]:
        out = []
        tp = run_dir / "transcript.jsonl"
        if tp.is_file():
            for line in tp.read_text().splitlines():
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if m.get("role") == "assistant" and m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        fn = tc.get("function") or {}
                        out.append(f"assistant→{fn.get('name', '?')}"
                                   f" {str(fn.get('arguments', ''))[:200]}")
                else:
                    nm = f"[{m['name']}] " if m.get("name") else ""
                    out.append(f"{m.get('role','?')} {nm}"
                               f"{(m.get('content') or '')[:300]}")
        return out

    tdiff = list(difflib.unified_diff(norm(dirs[0]), norm(dirs[1]),
                                      fromfile=a, tofile=b,
                                      lineterm="", n=2))
    ws_a, ws_b = (d / "workspace" for d in dirs)
    files_a = {str(p.relative_to(ws_a))
               for p in ws_a.rglob("*") if p.is_file()} \
        if ws_a.is_dir() else set()
    files_b = {str(p.relative_to(ws_b))
               for p in ws_b.rglob("*") if p.is_file()} \
        if ws_b.is_dir() else set()
    return {"run_a": a, "run_b": b,
            "transcript_diff": tdiff,
            "added": sorted(files_b - files_a),
            "removed": sorted(files_a - files_b)}


# ---------------- failures: candidate variants ----------------

class CandidateIn(BaseModel):
    variant: str


@app.post("/api/v1/failures/{run_id}/candidate",
          dependencies=[Depends(auth)])
def failure_candidate(run_id: str, body: CandidateIn,
                      l: Lab = Depends(lab)):
    """Clone the failed variant into a candidate carrying PROPOSALS.md —
    the improvement plan travels with the variant."""
    from skilllab import failure
    try:
        dest = failure.candidate(l, run_id, body.variant)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"path": str(dest)}


# ---------------- architect: reject + llm flag ----------------

@app.post("/api/v1/proposals/{pid}/reject", dependencies=[Depends(auth)])
def reject(pid: str, l: Lab = Depends(lab)):
    from skilllab import architect
    try:
        architect.set_status(l, pid, "rejected")
    except LabError as e:
        raise HTTPException(404, str(e))
    return {"id": pid, "status": "rejected"}


# ---------------- lab status + tasks + export/import ----------------

@app.get("/api/v1/status")
def lab_status(l: Lab = Depends(lab)):
    counts = {d: sum(1 for p in l.d(d).rglob("*") if p.is_file()
                     and p.name != ".gitkeep")
              for d in ("skills", "tasks", "rubrics", "experiments",
                        "insights", "principles")}
    n_runs = sum(1 for d in l.runs_dir.iterdir()
                 if (d / "run.yaml").is_file()) \
        if l.runs_dir.is_dir() else 0
    warns = []
    for m in l.skills():
        if not m.variants:
            warns.append(f"skill '{m.id}' has no variants")
    for t in l.tasks():
        for fx in t.fixtures:
            if not (l.task_dir(t.id) / fx).exists():
                warns.append(f"task '{t.id}': missing fixture '{fx}'")
    n_noeval = sum(1 for d in l.runs_dir.iterdir()
                   if (d / "run.yaml").is_file()
                   and not (d / "eval.yaml").is_file()) \
        if l.runs_dir.is_dir() else 0
    if n_noeval:
        warns.append(f"{n_noeval} run(s) missing eval.yaml")
    return {"root": str(l.root), "model": l.cfg["model"],
            "judge_model": l.cfg["judge_model"],
            "sandbox": l.cfg.get("sandbox"), "counts": counts,
            "runs": n_runs, "warnings": warns}


# --- provider / model detection -------------------------------------------
# Any litellm model string is accepted. These tables only *identify* which
# provider a model string or an API key belongs to — keys are never
# returned, only their presence + recognizable prefix.

_PROVIDERS = [
    # id, env vars (first match wins), key prefix hints, example model
    ("anthropic", ["ANTHROPIC_API_KEY"], ["sk-ant-"],
     "anthropic/claude-sonnet-4-5"),
    ("openai", ["OPENAI_API_KEY"], ["sk-proj-", "sk-"], "openai/gpt-4o"),
    ("gemini", ["GEMINI_API_KEY", "GOOGLE_API_KEY"], ["AIza", "AQ."],
     "gemini/gemini-3-flash-preview"),
    ("xai", ["XAI_API_KEY"], ["xai-"], "xai/grok-3"),
    ("groq", ["GROQ_API_KEY"], ["gsk_"], "groq/llama-3.3-70b"),
    ("mistral", ["MISTRAL_API_KEY"], [], "mistral/mistral-large-latest"),
    ("perplexity", ["PERPLEXITYAI_API_KEY"], ["pplx-"], "perplexity/sonar"),
    ("openrouter", ["OPENROUTER_API_KEY"], ["sk-or-"], "openrouter/auto"),
    ("deepseek", ["DEEPSEEK_API_KEY"], ["sk-"], "deepseek/deepseek-chat"),
    ("cohere", ["COHERE_API_KEY"], [], "cohere/command-r-plus"),
    ("huggingface", ["HF_TOKEN", "HUGGINGFACE_API_KEY"], ["hf_"],
     "huggingface/meta-llama/Llama-3.3-70B-Instruct"),
    ("nvidia", ["NVIDIA_API_KEY"], ["nvapi-"], "nvidia/llama-3.1-405b"),
    ("ollama", [], [], "ollama/llama3.2"),   # local — no key needed
]


def _resolve_provider(model: str) -> str:
    """Model string → provider id. mock/cmd are local drivers; otherwise
    ask litellm (handles unprefixed names like 'gpt-4o'), falling back to
    the prefix before '/'."""
    if model == "mock" or model.startswith("mock:"):
        return "mock"
    if model.startswith("cmd:"):
        return "cmd"
    try:
        import litellm
        return litellm.get_llm_provider(model)[1] or "unknown"
    except Exception:
        return model.split("/", 1)[0] if "/" in model else "unknown"


@app.get("/api/v1/models")
def models(l: Lab = Depends(lab)):
    """Which providers the server can actually call: env keys detected
    (never their values) + a resolve example per provider."""
    import os
    providers = []
    for pid, envs, prefixes, example in _PROVIDERS:
        hit = next((e for e in envs if os.environ.get(e)), None)
        hint = recognized = None
        if hit:
            key = os.environ[hit]
            hint = (key[:8] + "…") if len(key) > 8 else "(set)"
            recognized = (any(key.startswith(p) for p in prefixes)
                          if prefixes else None)
        providers.append({
            "id": pid, "env": hit, "detected": bool(hit),
            "hint": hint, "recognized": recognized,
            "example": example})
    return {"configured": l.cfg["model"],
            "judge_model": l.cfg["judge_model"],
            "providers": providers,
            "accepts": "any litellm provider string, 'mock', or 'cmd:<driver>'"}


@app.get("/api/v1/models/resolve")
def models_resolve(model: str):
    """Identify which provider a model string belongs to."""
    return {"model": model, "provider": _resolve_provider(model)}


@app.get("/api/v1/tasks")
def tasks(l: Lab = Depends(lab)):
    return [t.model_dump(mode="json") for t in l.tasks()]


@app.post("/api/v1/tasks", dependencies=[Depends(auth)])
def task_new(body: IdIn, l: Lab = Depends(lab)):
    """`lab task new` — scaffold task.yaml."""
    from skilllab.cli import TASK_TEMPLATE
    d = l.tasks_dir / body.id
    if (d / "task.yaml").is_file():
        raise HTTPException(409, f"task '{body.id}' already exists")
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.yaml").write_text(TASK_TEMPLATE.format(tid=body.id))
    return {"path": str(d / "task.yaml")}


@app.get("/api/v1/rubrics")
def rubrics(l: Lab = Depends(lab)):
    from skilllab.models import load_yaml
    out = []
    if l.rubrics_dir.is_dir():
        for p in sorted(l.rubrics_dir.glob("*.yaml")):
            r = load_yaml(p)
            r.setdefault("id", p.stem)
            out.append(r)
    return out


@app.post("/api/v1/rubrics", dependencies=[Depends(auth)])
def rubric_new(body: IdIn, l: Lab = Depends(lab)):
    """`lab rubric new` — scaffold rubric yaml."""
    from skilllab.cli import RUBRIC_TEMPLATE
    p = l.rubrics_dir / f"{body.id}.yaml"
    if p.is_file():
        raise HTTPException(409, f"rubric '{body.id}' already exists")
    l.rubrics_dir.mkdir(parents=True, exist_ok=True)
    p.write_text(RUBRIC_TEMPLATE.format(rid=body.id))
    return {"path": str(p)}


class ExportIn(BaseModel):
    name: str                        # dir name under <lab>/exports/
    tasks: bool = False


@app.post("/api/v1/export", dependencies=[Depends(auth)])
def export_pack(body: ExportIn, l: Lab = Depends(lab)):
    import re
    from skilllab.share import export_pack as do_export
    name = re.sub(r"[^a-z0-9._-]+", "-", body.name.lower()).strip("-.")
    if not name:
        raise HTTPException(400, "invalid pack name")
    try:
        out = do_export(l, l.d("exports") / name, body.tasks)
    except LabError as e:
        raise HTTPException(409, str(e))
    return {"path": str(out)}


class ImportPackIn(BaseModel):
    src: str                         # dir name under <lab>/exports/
    force: bool = False


@app.post("/api/v1/import", dependencies=[Depends(auth)])
def import_pack(body: ImportPackIn, l: Lab = Depends(lab)):
    """Import a share pack — packs live under <lab>/exports/ (from
    `lab export`) or <lab>/imports/ (staged); arbitrary server paths
    are not accepted over HTTP."""
    from skilllab.share import import_pack as do_import
    src = None
    for base in ("exports", "imports"):
        try:
            src = _lab_path(l, body.src, base)
            break
        except HTTPException:
            continue
    if src is None:
        raise HTTPException(
            400, "pack must be a directory under <lab>/exports/ "
            "or <lab>/imports/")
    try:
        res = do_import(l, src, body.force)
    except LabError as e:
        raise HTTPException(409, str(e))
    return res


# ---- production: serve the built SPA from the same port -------------
# NOTE: must stay LAST — a `/{path:path}` GET registered earlier would
# shadow every /api/v1 GET route defined below it.

_DIST = (Path(__file__).parent.parent / "frontend" / "dist").resolve()
if _DIST.is_dir():
    from fastapi.responses import FileResponse

    @app.get("/{path:path}", include_in_schema=False)
    def spa_catchall(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (_DIST / path).resolve()
        if f.is_file() and _DIST in f.parents:
            return FileResponse(f)
        if "." in Path(path).name:      # missing asset → 404, not HTML
            raise HTTPException(404)
        return FileResponse(_DIST / "index.html")  # client routing
