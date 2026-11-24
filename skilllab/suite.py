"""Test-suite domain ops — validation, safe CRUD, fixtures, datasets.

Source of truth for "is this suite runnable": the same rules the engine
and evaluator enforce at run time (preflight task/rubric/fixture checks
in engine.validate_experiment, criterion checks in evaluate). The web
layer serializes these results — it never re-implements them.

Severity contract:
  "error"   — a benchmark containing this task/suite cannot honestly run
              (engine would reject or the eval would record an error).
  "warning" — runs, but the evidence needs a caveat (mock judge, sandbox
              disabled command checks, missing relevance expectations).
"""
from __future__ import annotations

import base64
import csv
import io
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from skilllab.lab import Lab, LabError, check_id
from skilllab.models import (Check, Rubric, TaskSpec, dump_yaml,
                             load_yaml)

MAX_UPLOAD = 512 * 1024              # fixture/prompt file upload cap
TASK_YAML = "task.yaml"


# ---------------------------------------------------------------- issues --

def _iss(sev: str, obj: str, field: str, msg: str, fix: str = "") -> dict:
    return {"severity": sev, "object": obj, "field": field,
            "message": msg, "fix": fix}


def _check_problem(c: Check) -> str | None:
    """Fields every check type actually needs — mirrors evaluate's use."""
    if c.type == "command" and not (c.command or "").strip():
        return "command check needs 'command'"
    if c.type in ("file-exists", "file-content", "script") \
            and not (c.path or "").strip():
        return f"{c.type} check needs 'path'"
    if c.type == "json" and not (c.keys or c.field):
        return "json check needs 'keys' or 'field'"
    if c.type == "file-content" \
            and not (c.contains or c.regex or c.equals):
        return ("file-content check needs 'contains', 'regex' "
                "or 'equals'")
    return None


def validate_task(lab: Lab, spec: TaskSpec, sandbox: str | None = None,
                  judge_model: str | None = None) -> list[dict]:
    """All issues that matter for one task — errors block a benchmark,
    warnings caveat the evidence."""
    issues: list[dict] = []
    tid, tdir = spec.id, lab.tasks_dir / spec.id
    if sandbox is None:
        sandbox = lab.cfg.get("sandbox")
    if judge_model is None:
        judge_model = lab.cfg.get("judge_model", "mock")

    if not (spec.prompt or "").strip():
        issues.append(_iss("error", tid, "prompt",
                           "prompt is empty — the agent would see "
                           "nothing", "Input tab"))
    else:
        p = (tdir / spec.prompt).resolve()
        if spec.prompt.startswith("/") or ".." in \
                Path(spec.prompt).parts or \
                not p.is_relative_to(tdir.resolve()):
            issues.append(_iss("error", tid, "prompt",
                               "prompt path escapes the task dir",
                               "Input tab"))
        elif p.is_file():
            if not p.read_text(errors="replace").strip():
                issues.append(_iss("error", tid, "prompt",
                                   f"prompt file '{spec.prompt}' is "
                                   "empty", "Input tab"))
        elif re.fullmatch(r"[\w./-]+\.(md|txt)", spec.prompt):
            # reads as a file ref the engine would silently treat as
            # literal text — almost certainly a missing file
            issues.append(_iss("error", tid, "prompt",
                               f"prompt file '{spec.prompt}' not found "
                               "in the task dir", "Input tab"))

    for fx in spec.fixtures:
        src = (tdir / fx).resolve()
        if not src.is_relative_to(tdir.resolve()):
            issues.append(_iss("error", tid, "fixtures",
                               f"fixture '{fx}' escapes the task dir",
                               "Fixtures tab"))
        elif not src.exists():
            issues.append(_iss("error", tid, "fixtures",
                               f"fixture '{fx}' does not exist in the "
                               "task dir", "Fixtures tab"))
        elif not src.is_dir():
            # the engine only copies directories — a file fixture is
            # silently ignored, producing a workspace without it
            issues.append(_iss("error", tid, "fixtures",
                               f"fixture '{fx}' is a file — only "
                               "directories are copied into the "
                               "workspace", "Fixtures tab"))

    names = [c.name() for c in spec.deterministic_checks]
    for c in spec.deterministic_checks:
        bad = _check_problem(c)
        if bad:
            issues.append(_iss("error", tid,
                               f"checks.{c.name()}", bad,
                               "Evaluation tab"))
        if c.type in ("command", "script") and sandbox != "bwrap":
            issues.append(_iss(
                "warning", tid, f"checks.{c.name()}",
                f"{c.type} check runs through sandbox policy — "
                f"sandbox={sandbox or 'disabled'} makes it record an "
                "eval error", "set sandbox: bwrap in lab.yaml"))
    if len(names) != len(set(names)):
        issues.append(_iss("error", tid, "checks",
                           "duplicate check names — rubric criteria "
                           "resolve checks by name", "Evaluation tab"))

    if spec.rubric:
        try:
            rub = lab.rubric(spec.rubric)
        except LabError as e:
            issues.append(_iss("error", tid, "rubric", str(e),
                               "Evaluation tab"))
        else:
            for crit in rub.criteria:
                issues.extend(_criterion_issues(
                    tid, crit, names, judge_model, where="Evaluation"))
    if spec.kind == "activation-positive" and \
            not spec.skill_relevance.expected:
        issues.append(_iss("warning", tid, "skill_relevance",
                           "activation-positive task lists no expected "
                           "skill — activation can't be scored",
                           "Evaluation tab"))
    if spec.kind == "activation-negative" and \
            not spec.skill_relevance.unexpected:
        issues.append(_iss("warning", tid, "skill_relevance",
                           "activation-negative task lists no "
                           "unexpected skill — false activation can't "
                           "be scored", "Evaluation tab"))
    return issues


_SCALE_RE = re.compile(r"^\d+(\.\d+)?-\d+(\.\d+)?$")


def _criterion_issues(obj: str, crit, check_names: list[str],
                      judge_model: str, where: str) -> list[dict]:
    """Mirrors evaluate._validate_criterion + the resolvable-check rule
    (`crit.check or crit.id` must name a task deterministic check)."""
    out: list[dict] = []
    f = f"criteria.{crit.id}"
    if crit.weight <= 0:
        out.append(_iss("error", obj, f,
                        f"weight must be > 0 (got {crit.weight})",
                        where))
    if crit.scale and not _SCALE_RE.match(crit.scale):
        out.append(_iss("error", obj, f,
                        f"scale must look like '1-5' "
                        f"(got {crit.scale!r})", where))
    if crit.method == "deterministic":
        if not crit.check:
            out.append(_iss("error", obj, f,
                            "deterministic criterion needs 'check' "
                            "naming a task check", where))
        elif check_names is not None and \
                (crit.check or crit.id) not in check_names:
            out.append(_iss("error", obj, f,
                            f"check '{crit.check or crit.id}' is not "
                            "defined on this task's deterministic "
                            "checks", where))
    elif crit.method == "llm-judge":
        if judge_model in ("mock", "") or judge_model.startswith("mock:"):
            out.append(_iss("warning", obj, f,
                            "llm-judge scores with the offline mock "
                            "judge (heuristic) — set judge_model in "
                            "lab.yaml for real judging", where))
    elif crit.method == "human":
        out.append(_iss("warning", obj, f,
                        "human criterion stays 'pending' until scored "
                        "via lab eval / run scoring", where))
    return out


def validate_rubric(lab: Lab, rub: Rubric) -> list[dict]:
    """Rubric-only issues — check-name resolution needs a task context,
    so that part is validated per-task instead."""
    issues: list[dict] = []
    if not rub.criteria:
        issues.append(_iss("warning", rub.id, "criteria",
                           "rubric has no criteria — tasks using it "
                           "fall back to deterministic checks only"))
    names = [c.id for c in rub.criteria]
    if len(names) != len(set(names)):
        issues.append(_iss("error", rub.id, "criteria",
                           "duplicate criterion ids"))
    for crit in rub.criteria:
        issues.extend(_criterion_issues(
            rub.id, crit, None, lab.cfg.get("judge_model", "mock"),
            where="rubric editor"))
    return issues


def validate_suite(lab: Lab) -> dict:
    """Whole-suite report — per-task issues, per-rubric issues, suite
    file issues, and a runnable flag per task (no errors = runnable)."""
    task_issues: dict[str, list[dict]] = {}
    for spec in lab.tasks():
        task_issues[spec.id] = validate_task(lab, spec)
    rubric_issues: dict[str, list[dict]] = {}
    if lab.rubrics_dir.is_dir():
        for p in sorted(lab.rubrics_dir.glob("*.yaml")):
            try:
                rub = Rubric(**load_yaml(p))
            except (ValidationError, TypeError) as e:
                rubric_issues[p.stem] = [_iss(
                    "error", p.stem, "rubric",
                    f"invalid rubric yaml: {str(e).splitlines()[0]}")]
                continue
            rubric_issues[rub.id] = validate_rubric(lab, rub)
    suite_issues: list[dict] = []
    if lab.suites_dir.is_dir():
        for p in sorted(lab.suites_dir.glob("*.yaml")):
            data = load_yaml(p)
            ids = data.get("tasks", []) if isinstance(data, dict) \
                else (data if isinstance(data, list) else [])
            seen: set[str] = set()
            for t in ids:
                if t in seen:
                    suite_issues.append(_iss(
                        "warning", p.stem, "tasks",
                        f"task '{t}' listed twice", "Suites tab"))
                seen.add(t)
                if t not in task_issues:
                    suite_issues.append(_iss(
                        "error", p.stem, "tasks",
                        f"task '{t}' does not exist", "Suites tab"))
    runnable = {t: not any(i["severity"] == "error" for i in iss)
                    for t, iss in task_issues.items()}
    return {"tasks": task_issues, "rubrics": rubric_issues,
            "suites": suite_issues, "runnable": runnable}


# ------------------------------------------------------------- task CRUD --

def _write_task(spec: TaskSpec, task_dir: Path) -> None:
    dump_yaml(spec.model_dump(mode="json", exclude_none=True),
              task_dir / TASK_YAML)


def create_task(lab: Lab, spec: TaskSpec) -> TaskSpec:
    check_id("task", spec.id)
    d = lab.task_dir(spec.id)
    if (d / TASK_YAML).is_file():
        raise LabError(f"task '{spec.id}' already exists")
    d.mkdir(parents=True, exist_ok=True)
    _write_task(spec, d)
    return spec


def update_task(lab: Lab, task_id: str, spec: TaskSpec) -> TaskSpec:
    lab.task(task_id)                        # 404s if absent
    if spec.id != task_id:
        check_id("task", spec.id)
        nd = lab.task_dir(spec.id)
        if nd.exists():
            raise LabError(f"task '{spec.id}' already exists")
        shutil.move(str(lab.task_dir(task_id)), str(nd))
    _write_task(spec, lab.task_dir(spec.id))
    return spec


def _archive(lab: Lab, src: Path, kind: str) -> Path:
    """Move to archive/ — auditable, nothing is deleted."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest = lab.archive_dir / kind / f"{src.stem if src.is_file() else src.name}-{ts}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    return dest


def task_refs(lab: Lab, task_id: str) -> dict:
    """Who references this task — experiments and suite files.
    Historical runs are self-contained and never block deletion."""
    exps, suites = [], []
    ed = lab.d("experiments")
    if ed.is_dir():
        for d in sorted(ed.iterdir()):
            ey = d / "experiment.yaml"
            if ey.is_file() and task_id in \
                    (load_yaml(ey).get("tasks") or []):
                exps.append(d.name)
    if lab.suites_dir.is_dir():
        for p in sorted(lab.suites_dir.glob("*.yaml")):
            data = load_yaml(p)
            ids = data.get("tasks", []) if isinstance(data, dict) \
                else (data if isinstance(data, list) else [])
            if task_id in ids:
                suites.append(p.stem)
    return {"experiments": exps, "suites": suites}


def delete_task(lab: Lab, task_id: str, force: bool = False) -> dict:
    lab.task(task_id)
    refs = task_refs(lab, task_id)
    live = [e for e in refs["experiments"]]
    if (live or refs["suites"]) and not force:
        raise LabError(
            f"task '{task_id}' is referenced by experiments "
            f"{live} and suites {refs['suites']} — remove those "
            "references first or repeat with force=true")
    dest = _archive(lab, lab.task_dir(task_id), "tasks")
    return {"archived_to": str(dest), "refs": refs}


def duplicate_task(lab: Lab, task_id: str, new_id: str) -> TaskSpec:
    lab.task(task_id)
    check_id("task", new_id)
    src, dst = lab.task_dir(task_id), lab.task_dir(new_id)
    if dst.exists():
        raise LabError(f"task '{new_id}' already exists")
    shutil.copytree(src, dst)
    spec = TaskSpec.load(dst)
    spec.id = new_id
    _write_task(spec, dst)
    return spec


# ----------------------------------------------------------- rubric CRUD --

def save_rubric(lab: Lab, rub: Rubric, old_id: str | None = None
                ) -> Rubric:
    """Create (old_id=None) or update/rename (old_id set) a rubric.
    A rename writes the new file first, then unlinks the old one —
    a mid-flight failure never leaves zero rubrics."""
    p = lab.rubrics_dir / f"{check_id('rubric', rub.id)}.yaml"
    if old_id is None and p.is_file():
        raise LabError(f"rubric '{rub.id}' already exists")
    old_p = None
    if old_id and old_id != rub.id:
        if p.is_file():
            raise LabError(f"rubric '{rub.id}' already exists")
        old_p = lab.rubrics_dir / f"{check_id('rubric', old_id)}.yaml"
        if not old_p.is_file():
            raise LabError(f"rubric '{old_id}' not found")
    lab.rubrics_dir.mkdir(parents=True, exist_ok=True)
    dump_yaml(rub.model_dump(mode="json", exclude_none=True), p)
    if old_p:
        old_p.unlink()
    return rub


def rubric_refs(lab: Lab, rubric_id: str) -> list[str]:
    return [t.id for t in lab.tasks() if t.rubric == rubric_id]


def delete_rubric(lab: Lab, rubric_id: str, force: bool = False) -> dict:
    lab.rubric(rubric_id)
    refs = rubric_refs(lab, rubric_id)
    if refs and not force:
        raise LabError(
            f"rubric '{rubric_id}' is used by tasks {refs} — repoint "
            "them first or repeat with force=true")
    dest = _archive(lab, lab.rubrics_dir / f"{rubric_id}.yaml",
                    "rubrics")
    return {"archived_to": str(dest), "tasks_using": refs}


def duplicate_rubric(lab: Lab, rubric_id: str, new_id: str) -> Rubric:
    rub = lab.rubric(rubric_id)
    check_id("rubric", new_id)
    if (lab.rubrics_dir / f"{new_id}.yaml").exists():
        raise LabError(f"rubric '{new_id}' already exists")
    rub.id = new_id
    lab.rubrics_dir.mkdir(parents=True, exist_ok=True)
    dump_yaml(rub.model_dump(mode="json", exclude_none=True),
              lab.rubrics_dir / f"{new_id}.yaml")
    return rub


# ------------------------------------------------------------ suite files --

def _suite_path(lab: Lab, suite_id: str) -> Path:
    return lab.suites_dir / f"{check_id('suite', suite_id)}.yaml"


def list_suites(lab: Lab) -> list[dict]:
    out = []
    if lab.suites_dir.is_dir():
        for p in sorted(lab.suites_dir.glob("*.yaml")):
            data = load_yaml(p)
            ids = data.get("tasks", []) if isinstance(data, dict) \
                else (data if isinstance(data, list) else [])
            out.append({"id": p.stem, "tasks": ids})
    return out


def get_suite(lab: Lab, suite_id: str) -> dict:
    p = _suite_path(lab, suite_id)
    if not p.is_file():
        raise LabError(f"suite '{suite_id}' not found")
    data = load_yaml(p)
    ids = data.get("tasks", []) if isinstance(data, dict) \
        else (data if isinstance(data, list) else [])
    return {"id": suite_id, "tasks": ids}


def save_suite(lab: Lab, suite_id: str, tasks: list[str]) -> dict:
    lab.suites_dir.mkdir(parents=True, exist_ok=True)
    dump_yaml({"tasks": list(tasks)}, _suite_path(lab, suite_id))
    return {"id": suite_id, "tasks": list(tasks)}


def delete_suite(lab: Lab, suite_id: str) -> dict:
    p = _suite_path(lab, suite_id)
    if not p.is_file():
        raise LabError(f"suite '{suite_id}' not found")
    dest = _archive(lab, p, "suites")
    return {"archived_to": str(dest)}


# ------------------------------------------------------------ task files --

def _task_file(lab: Lab, task_id: str, rel: str) -> Path:
    """Resolve `rel` strictly inside the task dir — no traversal, no
    absolute paths, never task.yaml itself (that goes through the task
    endpoints so schema validation can't be bypassed)."""
    d = lab.task_dir(task_id).resolve()
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise LabError(f"unsafe file path {rel!r}")
    p = (d / rel).resolve()
    if not p.is_relative_to(d):
        raise LabError(f"file path {rel!r} escapes the task dir")
    if p == d / TASK_YAML:
        raise LabError("task.yaml is managed by the task endpoints")
    return p


def list_task_files(lab: Lab, task_id: str) -> list[dict]:
    spec = lab.task(task_id)
    d = lab.task_dir(task_id)
    out = []
    for p in sorted(d.rglob("*")):
        rel = str(p.relative_to(d))
        out.append({"path": rel, "dir": p.is_dir(),
                    "size": p.stat().st_size if p.is_file() else None,
                    "fixture": rel in spec.fixtures})
    return out


def read_task_file(lab: Lab, task_id: str, rel: str) -> dict:
    p = _task_file(lab, task_id, rel)
    if not p.is_file():
        raise LabError(f"no file '{rel}' in task '{task_id}'")
    data = p.read_bytes()
    try:
        return {"path": rel, "content": data.decode(), "binary": False}
    except UnicodeDecodeError:
        return {"path": rel, "content_b64": base64.b64encode(data)
                .decode(), "binary": True}


def put_task_file(lab: Lab, task_id: str, rel: str, content: str | None,
                  content_b64: str | None = None) -> dict:
    p = _task_file(lab, task_id, rel)
    raw = base64.b64decode(content_b64) if content_b64 is not None \
        else (content or "").encode()
    if len(raw) > MAX_UPLOAD:
        raise LabError(f"file exceeds {MAX_UPLOAD // 1024}KB limit")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(p)                       # atomic on POSIX
    return {"path": rel, "size": len(raw)}


def delete_task_file(lab: Lab, task_id: str, rel: str) -> dict:
    p = _task_file(lab, task_id, rel)
    if not p.exists():
        raise LabError(f"no file '{rel}' in task '{task_id}'")
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"deleted": rel}


# ------------------------------------------------------------- datasets --

CSV_FIELDS = ("id", "kind", "prompt", "fixtures", "expected_skills",
              "unexpected_skills", "rubric", "checks")


def export_tasks_json(lab: Lab) -> list[dict]:
    return [t.model_dump(mode="json", exclude_none=True)
            for t in lab.tasks()]


def export_tasks_csv(lab: Lab) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    w.writeheader()
    for t in lab.tasks():
        d = t.model_dump(mode="json", exclude_none=True)
        sr = d.get("skill_relevance") or {}
        w.writerow({
            "id": d["id"], "kind": d["kind"],
            "prompt": d.get("prompt") or "",
            "fixtures": ";".join(d.get("fixtures") or []),
            "expected_skills": ";".join(sr.get("expected") or []),
            "unexpected_skills": ";".join(sr.get("unexpected") or []),
            "rubric": d.get("rubric") or "",
            "checks": __import__("json").dumps(
                d.get("deterministic_checks") or [])})
    return buf.getvalue()


def _task_from_record(rec: dict) -> TaskSpec:
    """Coerce a JSON/CSV-shaped record into a validated TaskSpec."""
    import json
    d = dict(rec)
    if isinstance(d.get("fixtures"), str):
        d["fixtures"] = [s for s in d["fixtures"].split(";") if s]
    for flat, nest in (("expected_skills", "expected"),
                       ("unexpected_skills", "unexpected")):
        if flat in d:
            sr = dict(d.get("skill_relevance") or {})
            v = d.pop(flat)
            sr[nest] = [s for s in v.split(";") if s] \
                if isinstance(v, str) else v
            d["skill_relevance"] = sr
    if "checks" in d:
        d["deterministic_checks"] = json.loads(d["checks"]) \
            if isinstance(d["checks"], str) else d["checks"]
        d.pop("checks")
    if "rubric" in d and d["rubric"] in ("", None):
        d.pop("rubric")
    for k in list(d):
        if k not in ("id", "kind", "prompt", "fixtures",
                     "skill_relevance", "rubric",
                     "deterministic_checks"):
            d.pop(k)
    return TaskSpec(**d)


def parse_dataset(fmt: str, text: str) -> tuple[list[dict], list[dict]]:
    """(records, parse_errors) — errors carry row numbers for UI."""
    import json
    records, errors = [], []
    if fmt == "json":
        try:
            data = json.loads(text)
            if not isinstance(data, list):
                raise ValueError("dataset must be a JSON array")
            for i, rec in enumerate(data):
                if isinstance(rec, dict):
                    records.append(rec)
                else:
                    errors.append({"row": i, "error":
                                   "record is not an object"})
        except ValueError as e:
            errors.append({"row": 0, "error": f"invalid JSON: {e}"})
    elif fmt == "csv":
        try:
            for i, rec in enumerate(csv.DictReader(
                    io.StringIO(text))):
                records.append(dict(rec))
        except csv.Error as e:
            errors.append({"row": i + 1 if records else 0,
                           "error": f"invalid CSV: {e}"})
    else:
        errors.append({"row": 0, "error": f"unknown format '{fmt}'"})
    return records, errors


def preview_import(lab: Lab, fmt: str, text: str) -> dict:
    """Validate every record without writing — per-row reasons."""
    records, errors = parse_dataset(fmt, text)
    ok, bad, dupes = [], [], []
    seen: set[str] = set()
    for i, rec in enumerate(records):
        try:
            spec = _task_from_record(rec)
        except (ValidationError, ValueError, TypeError) as e:
            bad.append({"row": i, "id": rec.get("id", "?"),
                        "error": "; ".join(
                            m.split(": ", 1)[-1] for m in
                            str(e).splitlines() if m.strip())[:300]})
            continue
        try:
            check_id("task", spec.id)
        except LabError as e:
            bad.append({"row": i, "id": spec.id, "error": str(e)})
            continue
        if spec.id in seen:
            bad.append({"row": i, "id": spec.id,
                        "error": "duplicate id within the dataset"})
            continue
        seen.add(spec.id)
        if (lab.task_dir(spec.id) / TASK_YAML).is_file():
            dupes.append(spec.id)
        ok.append({"row": i, "task": spec.model_dump(mode="json",
                                                    exclude_none=True)})
    return {"ok": ok, "bad": bad, "conflicts": dupes,
            "parse_errors": errors}


def apply_import(lab: Lab, fmt: str, text: str,
                 on_conflict: str = "skip") -> dict:
    """Write an all-valid dataset; conflicts skip or overwrite only
    when explicitly requested. Any invalid row aborts the whole import
    — no partial writes."""
    prev = preview_import(lab, fmt, text)
    if prev["bad"] or prev["parse_errors"]:
        raise LabError(f"dataset has {len(prev['bad']) + len(prev['parse_errors'])} "
                       "invalid row(s) — fix or remove them before "
                       "importing")
    if prev["conflicts"] and on_conflict == "reject":
        raise LabError(f"task ids already exist: {prev['conflicts']} — "
                       "rename or choose overwrite")
    imported, skipped = [], []
    for row in prev["ok"]:
        spec = TaskSpec(**row["task"])
        if spec.id in prev["conflicts"]:
            if on_conflict == "skip":
                skipped.append(spec.id)
                continue
            update_task(lab, spec.id, spec)   # overwrite
        else:
            create_task(lab, spec)
        imported.append(spec.id)
    return {"imported": imported, "skipped": skipped,
            "rejected": prev["conflicts"] if on_conflict == "reject"
            else []}
