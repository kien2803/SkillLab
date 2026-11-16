"""Report: aggregate run records + evals into an experiment comparison table."""

from __future__ import annotations

import statistics
from pathlib import Path

from .lab import Lab
from .models import EvalResult, Experiment, RunRecord, load_yaml


def load_runs(lab: Lab, exp_id: str) -> list[tuple[RunRecord, EvalResult | None]]:
    out = []
    for d in sorted(lab.runs_dir.iterdir()):
        ry = d / "run.yaml"
        if not ry.is_file():
            continue
        rec = RunRecord(**load_yaml(ry))
        if rec.experiment != exp_id:
            continue
        ev = None
        ey = d / "eval.yaml"
        if ey.is_file():
            ev = EvalResult(**load_yaml(ey))
        out.append((rec, ev))
    return out


def _mean(xs: list[float]) -> float | None:
    return statistics.mean(xs) if xs else None


def _fmt(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x:.0%}" if pct else f"{x:.2f}"


def build_report(lab: Lab, exp: Experiment) -> str:
    runs = load_runs(lab, exp.id)
    lines = [f"# Report: {exp.id}", "",
             f"**Hypothesis:** {exp.hypothesis or '—'}", "",
             f"- model: `{exp.fixed.model}` · injection: `{exp.fixed.injection_mode}`"
             f" · rollouts/arm: {exp.rollouts_per_arm}",
             f"- runs found: {len(runs)}", ""]

    # bucket by arm
    by_arm: dict[str, list[tuple[RunRecord, EvalResult | None]]] = {}
    for r in runs:
        by_arm.setdefault(r[0].arm, []).append(r)

    # per-arm skill usage: skill -> [offered_runs, activated_runs, resources]
    usage: dict[str, dict[str, list]] = {}
    for arm_name, rows in by_arm.items():
        for rec, _ in rows:
            for e in rec.skill_events:
                if e.skill is None:
                    continue
                slot = usage.setdefault(arm_name, {}).setdefault(
                    e.skill, [set(), set(), set()])
                if e.event == "offered":
                    slot[0].add(rec.run_id)
                elif e.event == "activated":
                    slot[1].add(rec.run_id)
                elif e.event == "resource_read" and e.path:
                    slot[2].add(e.path)

    pos_tasks = {t.id for t in lab.tasks() if t.kind == "activation-positive"
                 and t.id in exp.tasks}
    neg_tasks = {t.id for t in lab.tasks() if t.kind == "activation-negative"
                 and t.id in exp.tasks}

    def metrics(rows):
        errs = sum(1 for r, _ in rows if r.status == "error")
        act, false_act = [], []
        scores, succ, toks, turns = [], [], [], []
        for rec, ev in rows:
            toks.append(rec.usage.input_tokens + rec.usage.output_tokens)
            turns.append(rec.usage.turns)
            if (rec.task in pos_tasks or rec.task in neg_tasks) \
                    and rec.injection_mode == "available":
                activated = {e.skill for e in rec.skill_events
                             if e.event == "activated"}
                task_spec = lab.task(rec.task)
                for sid in task_spec.skill_relevance.expected:
                    if rec.task in pos_tasks:
                        act.append(1.0 if sid in activated else 0.0)
                for sid in task_spec.skill_relevance.unexpected:
                    false_act.append(1.0 if sid in activated else 0.0)
            if ev:
                if ev.rubric_score is not None:
                    scores.append(ev.rubric_score)
                succ.append(1.0 if ev.success else 0.0)
        return {
            "n": len(rows), "errs": errs, "act": _mean(act),
            "false_act": _mean(false_act), "score": _mean(scores),
            "succ": _mean(succ), "toks": _mean(toks), "turns": _mean(turns),
            "var": statistics.pstdev(scores) if len(scores) > 1 else None,
        }

    def row_cells(name, m):
        return (f"| {name} | {m['n']} | {m['errs']} | {_fmt(m['act'], 1)}"
                f" | {_fmt(m['false_act'], 1)} | {_fmt(m['score'])}"
                f" | {_fmt(m['succ'], 1)} | {_fmt(m['toks'])}"
                f" | {_fmt(m['turns'])} | {_fmt(m['var'])} |")

    lines += ["## Arms", "",
              "| arm | n | err | activation | false-act | rubric | success |"
              " tokens | turns | variance |",
              "|---|---|---|---|---|---|---|---|---|---|"]

    arm_scores: dict[str, float | None] = {}
    arm_rates: dict[str, dict] = {}
    for arm in exp.arms:
        m = metrics(by_arm.get(arm.name, []))
        arm_scores[arm.name] = m["score"]
        arm_rates[arm.name] = {"act": m["act"], "false_act": m["false_act"],
                               "var": m["var"]}
        lines.append(row_cells(arm.name, m))

    # multi-model comparison: same arms, different models (e.g. rerun --model)
    by_model: dict[str, list] = {}
    for r in runs:
        by_model.setdefault(r[0].model.get("name", "?"), []).append(r)
    if len(by_model) > 1:
        lines += ["", "## By model", "",
                  "| model | n | err | activation | false-act | rubric |"
                  " success | tokens | turns | variance |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for name, rows in sorted(by_model.items()):
            lines.append(row_cells(name, metrics(rows)))

    # delta vs first arm with skill=None (control)
    ctrl = next((a for a in exp.arms if a.skill is None), exp.arms[0])
    if ctrl.name in arm_scores and arm_scores[ctrl.name] is not None:
        lines += ["", "## Delta vs control "
                  f"(`{ctrl.name}`)", ""]
        for a in exp.arms:
            if a.name == ctrl.name or arm_scores.get(a.name) is None:
                continue
            d = arm_scores[a.name] - arm_scores[ctrl.name]  # type: ignore[operator]
            lines.append(f"- `{a.name}`: {d:+.2f} rubric")

    if usage:
        lines += ["", "## Skill usage", ""]
        for arm_name in [a.name for a in exp.arms if a.name in usage]:
            for sid, (offered, activated, resources) in sorted(
                    usage[arm_name].items()):
                res = f" · read: {', '.join(sorted(resources))}" \
                    if resources else ""
                lines.append(f"- `{arm_name}` **{sid}**: offered "
                             f"{len(offered)} run(s), activated "
                             f"{len(activated)}{res}")

    # --- suggested insights: heuristics only, user decides ---------------
    sugg: list[str] = []
    c = arm_rates.get(ctrl.name, {})
    for a in exp.arms:
        if a.name == ctrl.name:
            continue
        r = arm_rates.get(a.name, {})
        if c.get("act") is not None and r.get("act") is not None:
            d = r["act"] - c["act"]
            if abs(d) >= 0.2:
                sugg.append(f"`{a.name}` vs `{ctrl.name}`: activation "
                            f"{d:+.0%} — trigger wording may matter")
        if c.get("false_act") is not None and r.get("false_act") is not None:
            d = r["false_act"] - c["false_act"]
            if d >= 0.2:
                sugg.append(f"`{a.name}` over-triggers vs `{ctrl.name}` "
                            f"(false-activation {d:+.0%})")
    for a in exp.arms:
        r = arm_rates.get(a.name, {})
        if r.get("var") is not None and r["var"] > 0.2:
            sugg.append(f"`{a.name}` has high outcome variance "
                        f"({r['var']:.2f}) — skill may be unstable")
    if sugg:
        lines += ["", "## Suggested insights *(review before recording)*",
                  ""] + [f"- {s}" for s in sugg]
        lines += ["", f"Record with: `lab insight new \"<statement>\" "
                      f"--evidence {exp.id}`"]

    # warnings — the lab should discourage weak conclusions
    warns = []
    for arm in exp.arms:
        n = len(by_arm.get(arm.name, []))
        if 0 < n < 3:
            warns.append(f"arm `{arm.name}` has only {n} run(s) — "
                         "conclusions from n<3 are unreliable")
    if warns:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in warns]

    lines += ["", "## Runs", ""]
    for rec, ev in runs:
        flag = "" if rec.status == "ok" else f" ⚠ {rec.error}"
        score = f" score={ev.rubric_score:.2f}" if ev and ev.rubric_score is not None else ""
        lines.append(f"- `{rec.run_id}`{score}{flag}")
    return "\n".join(lines) + "\n"


def write_report(lab: Lab, exp_id: str) -> Path:
    exp = lab.experiment(exp_id)
    text = build_report(lab, exp)
    p = lab.exp_dir(exp_id) / "analysis.md"
    p.write_text(text)
    return p
