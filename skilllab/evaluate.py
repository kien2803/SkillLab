"""Evaluator: deterministic checks + optional LLM-judge, scored against rubric."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .engine import run_in_workspace
from .lab import Lab, LabError
from .llm import LLMClient
from .models import (CheckResult, EvalResult, RunRecord, Rubric, TaskSpec,
                     dump_yaml, load_yaml)

_JUDGE_TMPL = """You are evaluating an AI agent's work on a task.

## Task
{task_prompt}

## Agent transcript (last steps)
{transcript}

## Agent's final message
{final}

## Workspace files after the run
{listing}

## Artifact excerpts
{artifacts}

## Criterion
{criterion}

Rate the work on a {scale} scale. Reply with exactly:
SCORE: <number>
WHY: <one or two sentences>"""


def _transcript_tail(run_dir: Path, n: int = 6, limit: int = 400) -> str:
    tp = run_dir / "transcript.jsonl"
    if not tp.is_file():
        return "(no transcript)"
    out = []
    for line in tp.read_text().splitlines()[-n:]:
        m = json.loads(line)
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                out.append(f"assistant→{tc['function']['name']}"
                           f"({tc['function']['arguments'][:200]})")
        else:
            out.append(f"{m.get('role', '?')}: "
                       f"{(m.get('content') or '')[:limit]}")
    return "\n".join(out)


def _artifact_excerpt(ws: Path, max_files: int = 5,
                      per_file: int = 1200) -> str:
    parts = []
    for p in sorted(ws.rglob("*")):
        if not p.is_file():
            continue
        parts.append(f"### {p.relative_to(ws)}\n"
                     f"{p.read_text(errors='replace')[:per_file]}")
        if len(parts) >= max_files:
            break
    return "\n".join(parts) or "(empty)"


def _run_check(lab: Lab, check, ws: Path) -> CheckResult:
    cid = check.name()
    if check.type == "file-exists":
        ok = (ws / check.path).exists()
        return CheckResult(id=cid, method="deterministic", passed=ok,
                           score=1.0 if ok else 0.0,
                           detail=f"{check.path} {'exists' if ok else 'missing'}")
    cmd = check.command or check.path
    try:
        r = run_in_workspace(lab, ws, cmd, timeout=120)
        ok = r.returncode == 0
        return CheckResult(id=cid, method="deterministic", passed=ok,
                           score=1.0 if ok else 0.0,
                           detail=(r.stdout + r.stderr)[-500:])
    except Exception as e:
        return CheckResult(id=cid, method="deterministic", passed=False,
                           score=0.0, detail=str(e)[:200])


def _judge(lab: Lab, judge_prompt: str, task_prompt: str, rec: RunRecord,
           ws: Path, scale: str) -> CheckResult:
    model = lab.cfg["judge_model"]
    listing = "\n".join(f"- {p.relative_to(ws)}" for p in ws.rglob("*")
                        if p.is_file()) or "(empty)"
    if model == "mock" or model.startswith("mock:"):
        # offline heuristic: reward the agent for producing artifacts
        score = 0.8 if any(ws.iterdir()) else 0.2
        return CheckResult(id="judge", method="llm-judge", score=score,
                           detail="mock judge (offline heuristic)")
    prompt = _JUDGE_TMPL.format(
        task_prompt=task_prompt[:4000],
        transcript=_transcript_tail(ws.parent),
        final=(rec.final_message or "")[:2000],
        listing=listing[:3000], artifacts=_artifact_excerpt(ws),
        criterion=judge_prompt, scale=scale)
    client = LLMClient(model,
                       timeout=float(lab.cfg.get("llm_timeout", 120)),
                       max_retries=int(lab.cfg.get("llm_retries", 3)))
    reply = client.complete([{"role": "user", "content": prompt}])
    m = re.search(r"SCORE:\s*([\d.]+)", reply.content)
    smax = float(scale.split("-")[-1]) if "-" in scale else 5.0
    score = min(float(m.group(1)) / smax, 1.0) if m else None
    return CheckResult(id="judge", method="llm-judge", score=score,
                       detail=reply.content[:300])


def evaluate_run(lab: Lab, rec: RunRecord, task: TaskSpec,
                 run_dir: Path) -> EvalResult:
    ws = run_dir / "workspace"
    results: list[CheckResult] = []
    det_by_name = {c.name(): c for c in task.deterministic_checks}

    rubric: Rubric | None = None
    if task.rubric:
        try:
            rubric = lab.rubric(task.rubric)
        except Exception:
            rubric = None

    if rubric and rubric.criteria:
        weighted, wsum = 0.0, 0.0
        for crit in rubric.criteria:
            if crit.method == "deterministic":
                chk = det_by_name.get(crit.check or crit.id)
                res = _run_check(lab, chk, ws) if chk else CheckResult(
                    id=crit.id, method="deterministic", passed=None,
                    detail=f"check '{crit.check or crit.id}' not defined on task")
                res.id = crit.id
            elif crit.method == "llm-judge":
                jp = crit.judge_prompt or ""
                jf = lab.rubrics_dir / jp
                if jp and jf.is_file():
                    jp = jf.read_text()
                try:
                    res = _judge(lab, jp or crit.id, task.resolve_prompt(
                        lab.task_dir(task.id)), rec, ws, crit.scale)
                except Exception as e:  # noqa: BLE001 - judge outage ≠ eval failure
                    res = CheckResult(
                        id=crit.id, method="llm-judge", score=None,
                        detail=f"judge error: {type(e).__name__}: {e}")
                res.id = crit.id
            else:
                res = CheckResult(id=crit.id, method="human", passed=None,
                                  detail="pending human review")
            results.append(res)
            if res.score is not None:
                weighted += res.score * crit.weight
                wsum += crit.weight
        score = weighted / wsum if wsum else None
        det = [r for r in results if r.method == "deterministic"
               and r.passed is not None]
        success = all(r.passed for r in det) if det else bool(
            score is not None and score >= 0.5)
        ev = EvalResult(checks=results, rubric_score=score, success=success)
    else:
        for c in task.deterministic_checks:
            results.append(_run_check(lab, c, ws))
        ev = EvalResult(
            checks=results,
            success=bool(results) and all(r.passed for r in results))
    dump_yaml(ev.model_dump(mode="json"), run_dir / "eval.yaml")
    return ev


def apply_human_scores(lab: Lab, rec: RunRecord, task: TaskSpec,
                       run_dir: Path,
                       scores: dict[str, float]) -> EvalResult:
    """Fill pending `method: human` checks with user scores, recompute.

    Scores are given per criterion id (e.g. `quality=4`). Values >1 are
    interpreted on the criterion's declared scale; values <=1 as already
    normalized.
    """
    ey = run_dir / "eval.yaml"
    if not ey.is_file():
        raise LabError(f"no eval.yaml for run '{rec.run_id}' — run "
                       "`lab eval` first")
    ev = EvalResult(**load_yaml(ey))
    rubric: Rubric | None = None
    if task.rubric:
        try:
            rubric = lab.rubric(task.rubric)
        except Exception:
            rubric = None
    weights: dict[str, tuple[float, str]] = {
        c.id: (c.weight, c.scale)
        for c in (rubric.criteria if rubric else [])
    }
    check_ids = {c.id for c in ev.checks}
    unknown = set(scores) - check_ids
    if unknown:
        raise LabError(f"no such criterion id(s) on this run's eval: "
                       f"{', '.join(sorted(unknown))}")
    applied = []
    for chk in ev.checks:
        if chk.id not in scores:
            continue
        if chk.method != "human":
            raise LabError(f"criterion '{chk.id}' is method "
                           f"'{chk.method}', not 'human'")
        _, scale = weights.get(chk.id, (1.0, "1-5"))
        smax = float(scale.split("-")[-1]) if "-" in scale else 5.0
        raw = scores[chk.id]
        chk.score = raw / smax if raw > 1 else raw
        chk.passed = chk.score >= 0.5
        chk.detail = f"human score {raw}/{smax}"
        applied.append(chk.id)
    if not applied:
        raise LabError("none of the given criteria are pending human checks")
    weighted, wsum = 0.0, 0.0
    for chk in ev.checks:
        w, _ = weights.get(chk.id, (1.0, "1-5"))
        if chk.score is not None:
            weighted += chk.score * w
            wsum += w
    if wsum:
        ev.rubric_score = weighted / wsum
    det = [c for c in ev.checks if c.method == "deterministic"
           and c.passed is not None]
    ev.success = all(c.passed for c in det) if det else bool(
        ev.rubric_score is not None and ev.rubric_score >= 0.5)
    dump_yaml(ev.model_dump(mode="json"), ey)
    return ev
