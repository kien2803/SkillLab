"""Evaluator: deterministic checks + optional LLM-judge, scored against rubric."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .engine import run_in_workspace
from .lab import Lab
from .llm import LLMClient
from .models import (CheckResult, EvalResult, RunRecord, Rubric, TaskSpec,
                     dump_yaml)

_JUDGE_TMPL = """You are evaluating an AI agent's work on a task.

## Task
{task_prompt}

## Agent's final message
{final}

## Workspace files after the run
{listing}

## Criterion
{criterion}

Rate the work on a {scale} scale. Reply with exactly:
SCORE: <number>
WHY: <one or two sentences>"""


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
        task_prompt=task_prompt[:4000], final=(rec.final_message or "")[:2000],
        listing=listing[:3000], criterion=judge_prompt, scale=scale)
    client = LLMClient(model)
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
                res = _judge(lab, jp or crit.id, task.resolve_prompt(
                    lab.task_dir(task.id)), rec, ws, crit.scale)
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
