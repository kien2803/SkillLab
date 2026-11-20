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
    n_runs: int = 0
    activation_rate: float | None = None
    false_activation_rate: float | None = None
    task_deltas: dict[str, float] = field(default_factory=dict)
    verdicts: list[tuple[str, bool | None, str]] = field(default_factory=list)
    # per-variant rates: ref -> {"act": [...], "false": [...]}
    by_ref: dict[str, dict[str, list[float]]] = field(default_factory=dict)


def evaluate_skill(lab: Lab, skill_id: str) -> GraduationReport:
    cfg = {**DEFAULT_GRADUATION, **lab.cfg.get("graduation", {})}
    rep = GraduationReport(skill_id=skill_id)

    skill_runs: list[tuple[RunRecord, EvalResult | None]] = []
    ctrl_runs: dict[str, list[tuple[RunRecord, EvalResult | None]]] = {}
    for d in lab.runs_dir.iterdir() if lab.runs_dir.is_dir() else []:
        ry = d / "run.yaml"
        if not ry.is_file():
            continue
        rec = RunRecord(**load_yaml(ry))
        ev = EvalResult(**load_yaml(d / "eval.yaml")) \
            if (d / "eval.yaml").is_file() else None
        ref = rec.skill_ref or ""
        if ref == skill_id or ref.startswith(skill_id + "@"):
            skill_runs.append((rec, ev))
        else:
            ctrl_runs.setdefault(rec.experiment, []).append((rec, ev))
    rep.n_runs = len(skill_runs)

    act, false_act = [], []
    task_scores: dict[str, list[float]] = {}
    ctrl_scores: dict[str, dict[str, list[float]]] = {}

    def score_of(ev: EvalResult | None) -> float | None:
        if ev is None or ev.status not in ("passed", "failed"):
            return None  # pending/error evals aren't evidence
        return ev.rubric_score if ev.rubric_score is not None \
            else (1.0 if ev.status == "passed" else 0.0)

    for rec, ev in skill_runs:
        try:
            task = lab.task(rec.task)
        except LabError:
            continue   # task left the bank — run isn't usable evidence
        activated = {e.skill for e in rec.skill_events
                     if e.event == "activated"}
        # activation metrics are only meaningful when the agent had to
        # decide to load the skill itself (available mode)
        if rec.injection_mode != "available":
            if task.kind == "performance":
                s = score_of(ev)
                if s is not None:
                    task_scores.setdefault(rec.task, []).append(s)
            continue
        ref_slot = rep.by_ref.setdefault(rec.skill_ref or "?",
                                         {"act": [], "false": []})
        if task.kind == "activation-positive":
            v = 1.0 if task.skill_relevance.expected and any(
                s in activated for s in task.skill_relevance.expected) else 0.0
            act.append(v)
            ref_slot["act"].append(v)
        elif task.kind == "activation-negative":
            v = 1.0 if any(s in activated for s in
                           task.skill_relevance.unexpected) else 0.0
            false_act.append(v)
            ref_slot["false"].append(v)
        elif task.kind == "performance":
            s = score_of(ev)
            if s is not None:
                task_scores.setdefault(rec.task, []).append(s)

    for exp_id, runs in ctrl_runs.items():
        try:
            exp = lab.experiment(exp_id)
        except Exception:
            continue
        ctrl_names = {a.name for a in exp.arms if a.skill is None}
        for rec, ev in runs:
            if rec.arm not in ctrl_names or rec.task not in task_scores:
                continue
            s = score_of(ev)
            if s is not None:
                ctrl_scores.setdefault(exp_id, {}) \
                    .setdefault(rec.task, []).append(s)

    rep.activation_rate = statistics.mean(act) if act else None
    rep.false_activation_rate = statistics.mean(false_act) if false_act else None
    for tid, scores in task_scores.items():
        ctrl = [s for exp_map in ctrl_scores.values()
                for t, ss in exp_map.items() if t == tid for s in ss]
        if ctrl:
            rep.task_deltas[tid] = statistics.mean(scores) - statistics.mean(ctrl)

    ar, far = rep.activation_rate, rep.false_activation_rate
    rep.verdicts = [
        ("sample size", rep.n_runs >= 9,
         f"{rep.n_runs} runs (want >=9: 3 rollouts x 3 tasks)"),
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
