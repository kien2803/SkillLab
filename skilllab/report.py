"""Report: aggregate run records + evals into an experiment comparison table."""

from __future__ import annotations

import math
import statistics
from pathlib import Path

from .lab import Lab, LabError
from .models import (EvalResult, Experiment, RunRecord, est_tokens, load_yaml,
                     parse_skill_ref)
from .registry import skill_entry_file


def load_runs(lab: Lab, exp_id: str) -> list[tuple[RunRecord, EvalResult | None]]:
    out = []
    if not lab.runs_dir.is_dir():
        return out
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


def _load_cost(lab: Lab, rec: RunRecord,
               activated: set[str]) -> float | None:
    """Estimated tokens the skill occupied in context: entry file plus the
    resources actually read. Counted when the skill is in context — always
    for injected mode, only on activation for available mode."""
    if not rec.skill_ref:
        return None
    sid, vid = parse_skill_ref(rec.skill_ref)
    if rec.injection_mode == "available" and sid not in activated:
        return None
    try:
        vdir = lab.variant_dir(sid, vid)
    except LabError:
        return None
    entry = skill_entry_file(vdir)
    if entry is None:
        return None
    cost = est_tokens(entry.read_text())
    for e in rec.skill_events:
        if e.event == "resource_read" and e.skill == sid and e.path:
            p = vdir / e.path
            if p.is_file():
                cost += est_tokens(p.read_text())
    return float(cost)


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
        inc = 0
        act, false_act, tta = [], [], []
        scores, succ, toks, turns, load = [], [], [], [], []
        for rec, ev in rows:
            activated = {e.skill for e in rec.skill_events
                         if e.event == "activated"}
            if rec.status != "error":
                toks.append(rec.usage.input_tokens + rec.usage.output_tokens)
                turns.append(rec.usage.turns)
            if (rec.task in pos_tasks or rec.task in neg_tasks) \
                    and rec.injection_mode == "available":
                try:
                    task_spec = lab.task(rec.task)
                except LabError:
                    task_spec = None  # task deleted after the run
                if task_spec is not None:
                    for sid in task_spec.skill_relevance.expected:
                        if rec.task in pos_tasks:
                            act.append(1.0 if sid in activated else 0.0)
                            if sid in activated:
                                tta.append(min(
                                    e.t for e in rec.skill_events
                                    if e.event == "activated"
                                    and e.skill == sid))
                    for sid in task_spec.skill_relevance.unexpected:
                        false_act.append(1.0 if sid in activated else 0.0)
            cost = _load_cost(lab, rec, activated)
            if cost is not None:
                load.append(cost)
            if ev and rec.status != "error":
                if ev.rubric_score is not None:
                    scores.append(ev.rubric_score)
                # only final (passed/failed) evals feed the success rate;
                # pending/error evals are counted separately, not as fails
                if ev.status in ("passed", "failed"):
                    succ.append(1.0 if ev.status == "passed" else 0.0)
                else:
                    inc += 1
            elif ev is None and rec.status != "error":
                inc += 1
        return {
            "n": len(rows), "errs": errs, "inc": inc, "act": _mean(act),
            "false_act": _mean(false_act), "tta": _mean(tta),
            "score": _mean(scores), "succ": _mean(succ),
            "toks": _mean(toks), "load": _mean(load),
            "turns": _mean(turns),
            "var": statistics.pstdev(scores) if len(scores) > 1 else None,
        }

    def row_cells(name, m):
        return (f"| {name} | {m['n']} | {m['errs']} | {m['inc']}"
                f" | {_fmt(m['act'], 1)}"
                f" | {_fmt(m['false_act'], 1)} | {_fmt(m['tta'])}"
                f" | {_fmt(m['score'])}"
                f" | {_fmt(m['succ'], 1)} | {_fmt(m['toks'])}"
                f" | {_fmt(m['load'])}"
                f" | {_fmt(m['turns'])} | {_fmt(m['var'])} |")

    lines += ["## Arms", "",
              "| arm | n | err | incomplete | activation | false-act |"
              " act@turn | rubric | success | tokens | load-cost | turns |"
              " variance |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    arm_scores: dict[str, float | None] = {}
    arm_rates: dict[str, dict] = {}
    for arm in exp.arms:
        m = metrics(by_arm.get(arm.name, []))
        arm_scores[arm.name] = m["score"]
        arm_rates[arm.name] = {"act": m["act"], "false_act": m["false_act"],
                               "var": m["var"]}
        lines.append(row_cells(arm.name, m))

    # multi-model comparison: same arms, different models (e.g. rerun
    # --model). Group by (model, arm) so treatments don't pool with controls.
    by_model_arm: dict[tuple[str, str], list] = {}
    models_seen = set()
    for r in runs:
        mname = r[0].model.get("name", "?")
        models_seen.add(mname)
        by_model_arm.setdefault((mname, r[0].arm), []).append(r)
    if len(models_seen) > 1:
        lines += ["", "## By model (per arm)", "",
                  "| model · arm | n | err | incomplete | activation |"
                  " false-act | act@turn | rubric | success | tokens |"
                  " load-cost | turns | variance |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for (mname, aname), rows in sorted(by_model_arm.items()):
            lines.append(row_cells(f"{mname} · {aname}", metrics(rows)))

    # delta vs first arm with skill=None (control) + Welch CI
    def arm_score_list(name: str) -> list[float]:
        xs = []
        for rec, ev in by_arm.get(name, []):
            if rec.status == "error" or not ev \
                    or ev.rubric_score is None:
                continue
            xs.append(ev.rubric_score)
        return xs

    ctrl = next((a for a in exp.arms if a.skill is None), exp.arms[0])
    ctrl_xs = arm_score_list(ctrl.name)
    if ctrl.name in arm_scores and ctrl_xs:
        lines += ["", "## Delta vs control "
                  f"(`{ctrl.name}`)", ""]
        for a in exp.arms:
            xs = arm_score_list(a.name)
            if a.name == ctrl.name or not xs:
                continue
            d = statistics.mean(xs) - statistics.mean(ctrl_xs)
            if len(xs) >= 2 and len(ctrl_xs) >= 2:
                se = math.sqrt(statistics.variance(xs) / len(xs)
                               + statistics.variance(ctrl_xs)
                               / len(ctrl_xs))
                lines.append(f"- `{a.name}`: {d:+.2f} rubric "
                             f"(95% CI ±{1.96 * se:.2f}, "
                             f"n={len(xs)}v{len(ctrl_xs)})")
            else:
                lines.append(f"- `{a.name}`: {d:+.2f} rubric "
                             "(n too small for CI)")

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
        rows = by_arm.get(arm.name, [])
        n = len(rows)
        if 0 < n < 3:
            warns.append(f"arm `{arm.name}` has only {n} run(s) — "
                         "conclusions from n<3 are unreliable")
        if n and not arm_score_list(arm.name):
            warns.append(f"arm `{arm.name}` has {n} run(s) but no rubric "
                         "scores — outcome data insufficient (missing "
                         "rubric or all runs errored)")
    # tasks that can't tell arms apart aren't measuring anything
    for t in exp.tasks:
        try:
            if lab.task(t).kind != "performance":
                continue
        except LabError:
            continue
        means = []
        for a in exp.arms:
            xs = [ev.rubric_score for rec, ev in by_arm.get(a.name, [])
                  if rec.task == t and rec.status != "error"
                  and ev and ev.rubric_score is not None]
            if xs:
                means.append(statistics.mean(xs))
        if len(means) >= 2 and max(means) - min(means) < 0.05:
            warns.append(f"task '{t}' shows no score spread across arms "
                         "(<0.05) — it may not discriminate; consider a "
                         "harder or more targeted task")
    if warns:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in warns]

    lines += ["", "## Runs", ""]
    for rec, ev in runs:
        flag = "" if rec.status == "ok" else f" ⚠ {rec.error}"
        if ev is not None and ev.status in ("pending", "error"):
            flag += f" ⚠ eval={ev.status}"
        elif ev is None:
            flag += " ⚠ eval=missing"
        score = f" score={ev.rubric_score:.2f}" if ev and ev.rubric_score is not None else ""
        lines.append(f"- `{rec.run_id}`{score}{flag}")
    return "\n".join(lines) + "\n"


def write_report(lab: Lab, exp_id: str) -> Path:
    exp = lab.experiment(exp_id)
    text = build_report(lab, exp)
    p = lab.exp_dir(exp_id) / "analysis.md"
    p.write_text(text)
    return p


def compare_table(lab: Lab, exp_id: str) -> str:
    """Pivot table: mean score ± stdev per arm × task (run-level variance)."""
    exp = lab.experiment(exp_id)
    runs = load_runs(lab, exp_id)
    cells: dict[tuple[str, str], list[float]] = {}
    tasks: list[str] = []
    for rec, ev in runs:
        if rec.status == "error" or not ev \
                or ev.status not in ("passed", "failed"):
            continue
        s = ev.rubric_score if ev.rubric_score is not None else (
            1.0 if ev.status == "passed" else 0.0)
        cells.setdefault((rec.arm, rec.task), []).append(s)
        if rec.task not in tasks:
            tasks.append(rec.task)
    out = [f"# Compare: {exp_id}", ""]
    if not cells:
        out.append("(no scored runs)")
        return "\n".join(out) + "\n"
    out.append("| arm | " + " | ".join(tasks) + " |")
    out.append("|" + "---|" * (len(tasks) + 1))
    for arm in exp.arms:
        row = [arm.name]
        for t in tasks:
            xs = cells.get((arm.name, t), [])
            if not xs:
                row.append("—")
            elif len(xs) > 1:
                row.append(f"{statistics.mean(xs):.2f}±"
                           f"{statistics.pstdev(xs):.2f}")
            else:
                row.append(f"{xs[0]:.2f}")
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out) + "\n"
