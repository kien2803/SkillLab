"""Failure analysis: classify the first observable failure of a run.

Deterministic, evidence-linked analysis — every cause cites the artifact
it was read from (run.yaml / eval.yaml / transcript / skill events).
Reports persist to `failures/<run_id>.yaml` so improvement loops can
accumulate: Failure → Analysis → Proposal → new variant → experiment.

Categories follow the spec taxonomy: incorrect-activation,
missing-context, ambiguous-instructions, incomplete-workflow,
incorrect-tool-usage, missing-resource, output-format-violation,
hallucinated-information, poor-error-recovery, excessive-tokens,
runtime-incompatibility — plus `infrastructure` and `evaluation-error`
for failures that are NOT the skill's fault.
"""

from __future__ import annotations

from pathlib import Path

from .lab import Lab, LabError
from .models import (EvalResult, RunRecord, TaskSpec, dump_yaml,
                     load_yaml, parse_skill_ref)

CATEGORIES = [
    "incorrect-activation", "missing-context", "ambiguous-instructions",
    "incomplete-workflow", "incorrect-tool-usage", "missing-resource",
    "output-format-violation", "hallucinated-information",
    "poor-error-recovery", "excessive-tokens",
    "runtime-incompatibility", "infrastructure", "evaluation-error",
]


# ---------- analysis ----------


def _load_run(lab: Lab, run_id: str) -> tuple[RunRecord, Path]:
    d = lab.runs_dir / run_id
    if not (d / "run.yaml").is_file():
        raise LabError(f"run '{run_id}' not found")
    return RunRecord(**load_yaml(d / "run.yaml")), d


def _load_eval(run_dir: Path) -> EvalResult | None:
    p = run_dir / "eval.yaml"
    return EvalResult(**load_yaml(p)) if p.is_file() else None


def _task_kind(lab: Lab, task_id: str) -> str:
    try:
        return lab.task(task_id).kind
    except LabError:
        return "performance"


def analyze_run(lab: Lab, run_id: str) -> dict:
    """Return a structured failure report for one run."""
    rec, d = _load_run(lab, run_id)
    ev = _load_eval(d)
    kind = _task_kind(lab, rec.task)
    causes: list[dict] = []

    # 1. infrastructure: the rollout itself broke — NOT a task failure
    if rec.status == "error":
        causes.append({
            "category": "infrastructure",
            "hypothesis": "rollout terminated with an error — harness, "
                          "sandbox, driver or model failure",
            "evidence": f"run.yaml: status=error "
                        f"({(rec.error or '')[:120]})"})

    # 2. evaluation infrastructure failed — distinct from task failure
    if ev and ev.status == "error":
        causes.append({
            "category": "evaluation-error",
            "hypothesis": "evaluation pipeline errored — check commands or "
                          "judge calls failed, not necessarily the task",
            "evidence": "eval.yaml: status=error"})
    # (missing eval is appended later only if nothing else surfaced —
    # a data gap must never mask a real task failure)

    # 3. activation signals (only meaningful for `available` mode)
    sid = parse_skill_ref(rec.skill_ref)[0] if rec.skill_ref else None
    if rec.injection_mode == "available" and sid:
        activated = rec.activated(sid)
        if kind == "activation-positive" and not activated:
            causes.append({
                "category": "incorrect-activation",
                "hypothesis": "skill was offered but never activated on a "
                              "task designed to trigger it — weak trigger "
                              "conditions or description",
                "evidence": "run.yaml: no 'activated' skill_event on "
                            "activation-positive task"})
        if kind == "activation-negative" and activated:
            causes.append({
                "category": "incorrect-activation",
                "hypothesis": "skill activated on a task designed NOT to "
                              "trigger it — description too broad",
                "evidence": "run.yaml: 'activated' event on "
                            "activation-negative task"})
        offered = any(e.event == "offered" for e in rec.skill_events)
        if activated and not offered:
            causes.append({
                "category": "missing-context",
                "hypothesis": "skill activated without an 'offered' event "
                              "— catalog wiring anomaly",
                "evidence": "run.yaml: skill_events sequence"})

    # 4. failed checks — first observable failure inside the work itself
    if ev:
        for c in ev.checks:
            if c.status != "failed":
                continue
            if c.method == "deterministic":
                cat = ("output-format-violation"
                       if any(k in c.id for k in
                              ("content", "format", "json", "schema"))
                       else "incomplete-workflow")
            elif c.method == "llm-judge":
                cat = "ambiguous-instructions"
            else:
                cat = "incomplete-workflow"
            causes.append({
                "category": cat,
                "hypothesis": {
                    "output-format-violation":
                        "expected output missing or malformed — artifact "
                        "did not satisfy the check",
                    "ambiguous-instructions":
                        "judge scored the output low — instructions may "
                        "be underspecified for this task",
                    "incomplete-workflow":
                        "a deterministic requirement was not met — "
                        "workflow did not reach the required end state",
                }[cat],
                "evidence": f"eval.yaml: check '{c.id}' "
                            f"({c.method}) failed — {c.detail[:100]}"})

    # 5. resource usage: offered resources never read (skip on errored
    # rollouts — a dead run can't read anything)
    if sid and rec.injection_mode == "available" \
            and rec.status != "error":
        reads = [e for e in rec.skill_events
                 if e.event == "resource_read"]
        if rec.activated(sid) and not reads:
            try:
                vdir = lab.variant_dir(
                    sid, parse_skill_ref(rec.skill_ref)[1])
                if list(vdir.rglob("resources/*")) or \
                        list(vdir.rglob("scripts/*")):
                    causes.append({
                        "category": "missing-resource",
                        "hypothesis": "skill activated but never read its "
                                      "bundled resources — content may be "
                                      "unused or links unclear",
                        "evidence": "run.yaml: activated with 0 "
                                    "resource_read events"})
            except LabError:
                pass

    # 6. token outlier vs same task+arm siblings
    if rec.usage.input_tokens or rec.usage.output_tokens:
        tot = rec.usage.input_tokens + rec.usage.output_tokens
        siblings = []
        for rd in lab.runs_dir.iterdir() if lab.runs_dir.is_dir() else []:
            ry = rd / "run.yaml"
            if not ry.is_file() or rd.name == run_id:
                continue
            other = RunRecord(**load_yaml(ry))
            if (other.task == rec.task and other.arm == rec.arm
                    and other.experiment == rec.experiment):
                siblings.append(
                    other.usage.input_tokens + other.usage.output_tokens)
        if len(siblings) >= 2:
            med = sorted(siblings)[len(siblings) // 2]
            if med and tot > med * 1.5:
                causes.append({
                    "category": "excessive-tokens",
                    "hypothesis": f"token usage {tot} is >1.5× sibling "
                                  f"median {int(med)} on the same "
                                  "task+arm — runaway loops or bloat",
                    "evidence": f"run.yaml: usage {tot} vs median "
                                f"{int(med)} over {len(siblings)} runs"})

    if ev is None and rec.status == "ok" and not causes:
        causes.append({
            "category": "evaluation-error",
            "hypothesis": "no eval.yaml — run finished but was never "
                          "evaluated (data gap, not a failure)",
            "evidence": "missing eval.yaml"})

    order = {"infrastructure": 0, "evaluation-error": 1,
             "incorrect-activation": 2, "missing-context": 3,
             "missing-resource": 4, "output-format-violation": 5,
             "incomplete-workflow": 6, "ambiguous-instructions": 7,
             "excessive-tokens": 8}
    causes.sort(key=lambda c: order.get(c["category"], 9))

    soft = {"missing-resource", "excessive-tokens", "missing-context"}
    infra = {"infrastructure", "evaluation-error"}
    if not causes:
        verdict = "clean" if (ev is None or ev.status == "passed") \
            else "clean"
    elif all(c["category"] in infra for c in causes):
        verdict = "inconclusive"          # not the skill's fault
    elif all(c["category"] in soft for c in causes):
        verdict = "warning"               # signals worth investigating
    else:
        verdict = "failed"

    report = {
        "run_id": run_id,
        "experiment": rec.experiment,
        "arm": rec.arm,
        "task": rec.task,
        "skill_ref": rec.skill_ref,
        "injection_mode": rec.injection_mode,
        "verdict": verdict,
        "first_failure": causes[0] if causes else None,
        "causes": causes,
    }
    return report


def proposals(report: dict) -> list[dict]:
    """Rule-based improvement proposals for each cause."""
    table = {
        "incorrect-activation": (
            "tighten `description` trigger wording — name the concrete "
            "situation ('use when …') or narrow over-broad terms",
            "higher activation precision on activation tasks",
            "too-narrow wording can reduce recall — re-run the "
            "activation suite"),
        "incomplete-workflow": (
            "add the missing end-state to the workflow steps or make "
            "the required artifact explicit in the output contract",
            "deterministic checks pass — output reaches required state",
            "more explicit steps raise token cost slightly"),
        "output-format-violation": (
            "state the output contract (file names, schema) verbatim in "
            "the skill and add an example block",
            "artifact matches the expected format",
            "rigid formats can hurt valid-but-different outputs"),
        "ambiguous-instructions": (
            "sharpen the failing criterion's requirement in the skill "
            "instructions or add a worked example",
            "judge scores improve on the same rubric",
            "task-specific tuning risks overfitting the eval"),
        "missing-resource": (
            "surface resource links earlier in the entry file or fold "
            "critical content inline",
            "resource_read events appear on activated runs",
            "inlining raises entry-file token cost"),
        "missing-context": (
            "check the catalog/offer wiring — the skill may be injected "
            "without being advertised",
            "offered events precede activated events",
            "none — harness/config fix"),
        "excessive-tokens": (
            "cap loop iterations and compress the skill body; move "
            "detail into resources/",
            "token usage returns toward the arm median",
            "aggressive trimming can drop guidance quality"),
        "infrastructure": (
            "inspect the error field — this is harness/sandbox/driver "
            "failure, not a skill regression",
            "rollout completes with status=ok",
            "none — fix the environment, not the skill"),
        "evaluation-error": (
            "re-run evaluation (`lab eval`) — the run itself may be "
            "fine; data gap only",
            "eval.yaml exists with a real status",
            "none"),
    }
    out = []
    for c in report["causes"]:
        change, impact, side = table.get(
            c["category"], ("investigate manually", "", ""))
        out.append({"category": c["category"], "problem": c["hypothesis"],
                    "evidence": c["evidence"], "change": change,
                    "expected_impact": impact, "side_effects": side})
    return out


def write_report(lab: Lab, report: dict) -> Path:
    d = lab.d("failures")
    d.mkdir(exist_ok=True)
    p = d / f"{report['run_id']}.yaml"
    dump_yaml({**report, "proposals": proposals(report)}, p)
    return p
