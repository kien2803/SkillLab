"""Graduation check: does a skill earn 'graduated' status from run history?

Criteria (defaults overridable via lab.yaml `graduation:` block):
- activation_rate >= 0.8 on activation-positive tasks
- false_activation_rate <= 0.2 on activation-negative tasks
- positive score delta vs control on >= 3 performance tasks (or all scored
  tasks if fewer exist — reported, not auto-failed)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .lab import Lab, LabError
from .models import EvalResult, RunRecord, load_yaml

DEFAULT_GRADUATION = {
    "activation_rate": 0.8,
    "false_activation_max": 0.2,
    "min_positive_delta_tasks": 3,
}


@dataclass
class GraduationReport:
    skill_id: str
    n_runs: int = 0                     # usable runs (non-error)
    n_total: int = 0                    # all runs incl. infra failures
    # sample accounting: what each run could/couldn't prove
    n_evaluated: int = 0                # evals in a terminal state
    n_activation: int = 0               # available-mode runs on act tasks
    n_performance: int = 0              # scored runs on perf tasks
    exclusions: dict[str, int] = field(default_factory=dict)
    activation_rate: float | None = None
    false_activation_rate: float | None = None
    task_deltas: dict[str, float] = field(default_factory=dict)
    verdicts: list[tuple[str, bool | None, str]] = field(default_factory=list)
    # per-variant rates: ref -> {"act": [...], "false": [...]}
    by_ref: dict[str, dict[str, list[float]]] = field(default_factory=dict)


def _run_cfg(rec: RunRecord) -> tuple:
    """Equivalence key for comparing runs: experiment context, the model
    actually used (rerun --model records it per run), injection mode and
    temperature. Only runs sharing this key are scientifically comparable."""
    return (rec.experiment, str((rec.model or {}).get("name", "?")),
            rec.injection_mode,
            str((rec.model or {}).get("temperature", "?")))


def evaluate_skill(lab: Lab, skill_id: str) -> GraduationReport:
    cfg = {**DEFAULT_GRADUATION, **lab.cfg.get("graduation", {})}
    rep = GraduationReport(skill_id=skill_id)

    skill_runs: list[tuple[RunRecord, EvalResult | None]] = []
    ctrl_runs: list[tuple[RunRecord, EvalResult | None]] = []
    n_total = 0
    for d in lab.runs_dir.iterdir() if lab.runs_dir.is_dir() else []:
        ry = d / "run.yaml"
        if not ry.is_file():
            continue
        rec = RunRecord(**load_yaml(ry))
        ev = EvalResult(**load_yaml(d / "eval.yaml")) \
            if (d / "eval.yaml").is_file() else None
        ref = rec.skill_ref or ""
        if ref == skill_id or ref.startswith(skill_id + "@"):
            n_total += 1
            if rec.status == "error":
                rep.exclusions["infra-error"] = \
                    rep.exclusions.get("infra-error", 0) + 1
                continue   # infra failure ≠ quality evidence
            skill_runs.append((rec, ev))
        elif rec.status != "error":
            ctrl_runs.append((rec, ev))
    rep.n_runs = len(skill_runs)
    rep.n_total = n_total
    rep.n_evaluated = sum(
        1 for _, ev in skill_runs
        if ev is not None and ev.status in ("passed", "failed"))

    act, false_act = [], []
    # skill scores grouped by equivalence key: (exp, model, mode, temp)
    skill_scores: dict[tuple, dict[str, list[float]]] = {}
    ctrl_pool: dict[tuple, dict[str, list[float]]] = {}

    def score_of(ev: EvalResult | None) -> float | None:
        if ev is None or ev.status not in ("passed", "failed"):
            return None  # pending/error evals aren't evidence
        return ev.rubric_score if ev.rubric_score is not None \
            else (1.0 if ev.status == "passed" else 0.0)

    for rec, ev in skill_runs:
        try:
            task = lab.task(rec.task)
        except LabError:
            rep.exclusions["task-deleted"] = \
                rep.exclusions.get("task-deleted", 0) + 1
            continue   # task left the bank — run isn't usable evidence
        activated = {e.skill for e in rec.skill_events
                     if e.event == "activated"}
        # activation metrics are only meaningful when the agent had to
        # decide to load the skill itself (available mode)
        if rec.injection_mode != "available":
            if task.kind == "performance":
                s = score_of(ev)
                if s is not None:
                    rep.n_performance += 1
                    skill_scores.setdefault(_run_cfg(rec), {}) \
                        .setdefault(rec.task, []).append(s)
                else:
                    rep.exclusions["eval-incomplete"] = \
                        rep.exclusions.get("eval-incomplete", 0) + 1
            continue
        ref_slot = rep.by_ref.setdefault(rec.skill_ref or "?",
                                         {"act": [], "false": []})
        if task.kind == "activation-positive":
            v = 1.0 if task.skill_relevance.expected and any(
                s in activated for s in task.skill_relevance.expected) else 0.0
            act.append(v)
            rep.n_activation += 1
            ref_slot["act"].append(v)
        elif task.kind == "activation-negative":
            v = 1.0 if any(s in activated for s in
                           task.skill_relevance.unexpected) else 0.0
            false_act.append(v)
            rep.n_activation += 1
            ref_slot["false"].append(v)
        elif task.kind == "performance":
            s = score_of(ev)
            if s is not None:
                rep.n_performance += 1
                skill_scores.setdefault(_run_cfg(rec), {}) \
                    .setdefault(rec.task, []).append(s)
            else:
                rep.exclusions["eval-incomplete"] = \
                    rep.exclusions.get("eval-incomplete", 0) + 1

    # pool control runs ONLY inside the same equivalence cell —
    # a control from a different experiment/model/mode is not evidence
    exp_ctrl_arms: dict[str, set] = {}
    for rec, ev in ctrl_runs:
        key = _run_cfg(rec)
        if key not in skill_scores:
            continue
        if rec.experiment not in exp_ctrl_arms:
            try:
                exp = lab.experiment(rec.experiment)
                exp_ctrl_arms[rec.experiment] = {
                    a.name for a in exp.arms if a.skill is None}
            except LabError:
                exp_ctrl_arms[rec.experiment] = set()
        if rec.arm not in exp_ctrl_arms[rec.experiment]:
            continue
        s = score_of(ev)
        if s is not None:
            ctrl_pool.setdefault(key, {}).setdefault(rec.task, []).append(s)

    rep.activation_rate = statistics.mean(act) if act else None
    rep.false_activation_rate = statistics.mean(false_act) if false_act else None
    task_delta_samples: dict[str, list[float]] = {}
    for key, per_task in skill_scores.items():
        ctrls = ctrl_pool.get(key, {})
        for tid, scores in per_task.items():
            if ctrls.get(tid):
                task_delta_samples.setdefault(tid, []).append(
                    statistics.mean(scores) - statistics.mean(ctrls[tid]))
    for tid, ds in task_delta_samples.items():
        rep.task_deltas[tid] = statistics.mean(ds)

    ar, far = rep.activation_rate, rep.false_activation_rate
    excl = (", excluded: " + ", ".join(f"{k}={v}" for k, v in
            rep.exclusions.items())) if rep.exclusions else ""
    rep.verdicts = [
        ("sample size", rep.n_runs >= 9,
         f"{rep.n_runs} usable of {rep.n_total} recorded "
         f"({rep.n_evaluated} evaluated, {rep.n_activation} activation-"
         f"eligible, {rep.n_performance} performance-scored"
         f"{excl}; want >=9: 3 rollouts x 3 tasks)"),
        ("activation",
         ar >= cfg["activation_rate"] if ar is not None else None,
         f"{ar:.0%} >= {cfg['activation_rate']:.0%}"
         if ar is not None else "no activation-positive data"),
        ("false activation",
         far <= cfg["false_activation_max"] if far is not None else None,
         f"{far:.0%} <= {cfg['false_activation_max']:.0%}"
         if far is not None else "no negative data"),
        ("positive delta",
         sum(1 for d in rep.task_deltas.values() if d > 0)
         >= cfg["min_positive_delta_tasks"] if rep.task_deltas else None,
         f"{sum(1 for d in rep.task_deltas.values() if d > 0)} tasks "
         f"positive vs control (want {cfg['min_positive_delta_tasks']})"
         if rep.task_deltas else "no performance data"),
    ]
    return rep
