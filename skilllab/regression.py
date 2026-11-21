"""Skill regression testing: candidate variant vs baseline variant.

A regression run is a two-arm controlled experiment (``baseline`` vs
``candidate``) — both arms share the same model/harness/injection config
by construction, so only the skill variant differs. The experiment is
persisted under ``experiments/reg-<...>/`` (normal ``lab report`` /
``lab runs`` / ``lab diff`` keep working) and a regression record lives at
``regressions/reg-<...>/`` with ``regression.yaml`` (config + verdict),
``report.yaml`` (structured results) and ``report.md`` (human report).

Nothing here invents data: missing evals, error runs and small samples are
reported as data-quality issues, never silently treated as pass or fail.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .engine import run_rollout, validate_experiment
from .evaluate import evaluate_run
from .lab import Lab, LabError, check_id
from .models import (Arm, EvalResult, Experiment, FixedConfig, RunRecord,
                     TaskSpec, dump_yaml, load_yaml)
from .report import load_runs

CATEGORIES = ("critical", "quality", "activation", "false-activation",
              "efficiency", "stability")


@dataclass
class Thresholds:
    """Regression flags — all configurable via lab.yaml `regression:` or
    `--threshold key=value` on the CLI."""
    score_drop: float = 0.10      # rubric score decrease (absolute, 0..1)
    token_increase: float = 0.25  # relative token growth
    latency_increase: float = 0.25
    variance_increase: float = 0.10  # absolute pstdev growth
    min_runs: int = 3             # per arm+task; below = insufficient data


def _thresholds(lab: Lab, overrides: dict | None = None) -> Thresholds:
    cfg = dict(lab.cfg.get("regression") or {})
    cfg.update(overrides or {})
    base = Thresholds()
    valid = {k: getattr(base, k) for k in base.__dataclass_fields__}
    unknown = set(cfg) - set(valid)
    if unknown:
        raise LabError(f"unknown regression threshold(s): "
                       f"{', '.join(sorted(unknown))} "
                       f"(valid: {', '.join(sorted(valid))})")
    for k, v in cfg.items():
        setattr(base, k, int(v) if k == "min_runs" else float(v))
    return base


def resolve_tasks(lab: Lab, spec: str) -> list[str]:
    """'all'/'default' -> whole task bank; 'suites/<spec>.yaml' -> listed
    ids; otherwise a comma-separated id list."""
    ids: list[str]
    if spec in ("all", "default"):
        ids = [t.id for t in lab.tasks()]
    else:
        suite = lab.root / "suites" / f"{spec}.yaml"
        if suite.is_file():
            data = load_yaml(suite)
            ids = data.get("tasks", []) if isinstance(data, dict) else list(data)
        else:
            ids = [s.strip() for s in spec.split(",") if s.strip()]
    if not ids:
        raise LabError(f"task suite '{spec}' resolves to no tasks")
    missing = [t for t in ids
               if not (lab.task_dir(t) / "task.yaml").is_file()]
    if missing:
        raise LabError(f"unknown task(s) in suite: {', '.join(missing)}")
    return ids


def _new_reg_id(lab: Lab, skill_id: str, baseline: str,
                candidate: str) -> str:
    prefix = f"reg-{skill_id}-{baseline}-{candidate}-"
    n = 1
    rdir = lab.d("regressions")
    if rdir.is_dir():
        for d in rdir.iterdir():
            if d.name.startswith(prefix):
                try:
                    n = max(n, int(d.name[len(prefix):]) + 1)
                except ValueError:
                    continue
    return f"{prefix}{n:02d}"


# --------------------------------------------------------------------- run --


def run_regression(lab: Lab, skill_id: str, baseline: str, candidate: str,
                   tasks_spec: str, model: str | None = None,
                   mode: str | None = None, rollouts: int | None = None,
                   overrides: dict | None = None,
                   progress=None, should_stop=None) -> str:
    """Validate, execute and analyze a baseline-vs-candidate comparison.

    Returns the regression id. Both arms run under the same experiment
    (same fixed config -> experimental equivalence by construction).
    `progress(done, total)` is invoked after each rollout;
    `should_stop()` returning True aborts the batch cleanly (the
    experiment is left 'running' — resumable via rerun).
    """
    lab.skill(skill_id)  # raises when the skill is not registered
    if baseline == candidate:
        raise LabError("baseline and candidate are the same variant — "
                       "nothing to compare")
    lab.variant_dir(skill_id, baseline)
    lab.variant_dir(skill_id, candidate)
    task_ids = resolve_tasks(lab, tasks_spec)

    reg_id = _new_reg_id(lab, skill_id, baseline, candidate)
    exp = Experiment(
        id=reg_id,
        title=f"Regression {skill_id}: {baseline} → {candidate}",
        hypothesis=f"{candidate} does not regress vs {baseline} on "
                   f"'{tasks_spec}'",
        independent_var="skill_variant",
        fixed=FixedConfig(
            model=model or lab.cfg["model"],
            temperature=float(lab.cfg["temperature"]),
            injection_mode=mode or "available"),
        arms=[Arm(name="baseline", skill=f"{skill_id}@{baseline}"),
              Arm(name="candidate", skill=f"{skill_id}@{candidate}")],
        tasks=task_ids,
        rollouts_per_arm=rollouts or int(lab.cfg["rollouts_per_arm"]),
        status="running")
    errors, warnings = validate_experiment(lab, exp)
    # the "no control arm" warning does not apply — baseline IS the control
    warnings = [w for w in warnings if "control arm" not in w]
    if errors:
        raise LabError("invalid regression config — "
                       + "; ".join(errors + warnings))

    exp_dir = lab.exp_dir(reg_id)
    exp_dir.mkdir(parents=True)
    exp.save(exp_dir)
    rdir = lab.d("regressions") / reg_id
    rdir.mkdir(parents=True, exist_ok=True)
    dump_yaml({
        "id": reg_id, "skill": skill_id,
        "baseline": baseline, "candidate": candidate,
        "suite": tasks_spec, "tasks": task_ids,
        "model": exp.fixed.model,
        "temperature": exp.fixed.temperature,
        "injection_mode": exp.fixed.injection_mode,
        "harness": exp.fixed.harness,
        "rollouts_per_arm": exp.rollouts_per_arm,
        "thresholds": overrides or {},
        "experiment": reg_id,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "running",
        "verdict": None,
    }, rdir / "regression.yaml")

    n = min(rollouts, exp.rollouts_per_arm) if rollouts \
        else exp.rollouts_per_arm
    total = len(exp.arms) * len(task_ids) * n
    done = 0
    for arm in exp.arms:
        for tid in task_ids:
            for i in range(n):
                if should_stop is not None and should_stop():
                    return reg_id
                rec = run_rollout(lab, exp, arm, tid, i)
                done += 1
                if progress is not None:
                    progress(done, total)
                try:
                    evaluate_run(lab, rec, lab.task(tid),
                                 lab.runs_dir / rec.run_id)
                except Exception as e:  # noqa: BLE001 - report, don't abort
                    print(f"warn: eval failed for {rec.run_id}: "
                          f"{type(e).__name__}: {e}")
    exp.status = "analyzed"
    exp.save(exp_dir)
    write_report(lab, reg_id)
    return reg_id


# ------------------------------------------------------------- run metrics --


def _duration(rec: RunRecord) -> float | None:
    try:
        return (datetime.fromisoformat(rec.finished)
                - datetime.fromisoformat(rec.started)).total_seconds()
    except (ValueError, TypeError):
        return None


def _side_metrics(skill_id: str,
                  rows: list[tuple[RunRecord, EvalResult | None]]) -> dict:
    """Aggregate metrics for one arm on one task (or a whole arm)."""
    ok = [(r, e) for r, e in rows if r.status == "ok"]
    errors = len(rows) - len(ok)
    finals = [e for _, e in ok
              if e is not None and e.status in ("passed", "failed")]
    incomplete = len(ok) - len(finals)
    scores = [
        e.rubric_score if e.rubric_score is not None
        else (1.0 if e.status == "passed" else 0.0)
        for e in finals
    ]
    acts = [1.0 if r.activated(skill_id) else 0.0 for r, _ in ok]
    toks = [r.usage.input_tokens + r.usage.output_tokens for r, _ in ok]
    durs = [d for r, _ in ok if (d := _duration(r)) is not None]
    turns = [r.usage.turns for r, _ in ok]
    mean = statistics.mean
    return {
        "n_runs": len(rows), "errors": errors,
        "error_rate": errors / len(rows) if rows else None,
        "n_final": len(finals), "incomplete": incomplete,
        "success": (sum(1 for e in finals if e.status == "passed")
                    / len(finals)) if finals else None,
        "score": mean(scores) if scores else None,
        "activated": mean(acts) if acts else None,
        "tokens": mean(toks) if toks else None,
        "latency": mean(durs) if durs else None,
        "turns": mean(turns) if turns else None,
        "variance": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
    }


def _classify(task: TaskSpec | None, mb: dict, mc: dict,
              thr: Thresholds, mode: str) -> tuple[list[str], list[str],
                                                   list[str]]:
    """Return (regression categories, improvements, notes) for one task."""
    cats: list[str] = []
    imps: list[str] = []
    notes: list[str] = []
    if mb["n_runs"] < thr.min_runs or mc["n_runs"] < thr.min_runs:
        notes.append(f"insufficient runs (n={mb['n_runs']}v{mc['n_runs']}, "
                     f"min={thr.min_runs})")
    if mb["incomplete"] or mc["incomplete"]:
        notes.append("incomplete evaluations present "
                     "(missing/pending/error are not counted as failures)")

    # --- outcome comparisons need final evals on both sides ----------
    if mb["n_final"] and mc["n_final"]:
        bs, cs = mb["success"], mc["success"]
        if bs is not None and cs is not None:
            if bs >= 0.5 > cs:
                cats.append("critical")      # passed before, fails now
            elif cs >= 0.5 > bs:
                imps.append("task now passes")
        bs_sc, cs_sc = mb["score"], mc["score"]
        if bs_sc is not None and cs_sc is not None:
            d = cs_sc - bs_sc
            if d < -thr.score_drop:
                cats.append("quality")
            elif d > thr.score_drop:
                imps.append("score improved")
    else:
        notes.append("no final evaluations on one/both sides — outcome "
                     "comparison impossible")

    # --- activation metrics only mean something in available mode -----
    if mode == "available" and task is not None:
        if task.kind == "activation-positive":
            ba, ca = mb["activated"], mc["activated"]
            if ba is not None and ca is not None:
                if ba >= 0.5 > ca:
                    cats.append("activation")   # stopped triggering
                elif ca - ba > 0:
                    imps.append("activation improved")
        elif task.kind == "activation-negative":
            ba, ca = mb["activated"], mc["activated"]
            if ba is not None and ca is not None:
                if ca - ba > 0:
                    cats.append("false-activation")  # now over-triggers
                elif ba - ca > 0:
                    imps.append("false-activation fixed")

    # --- efficiency ---------------------------------------------------
    for key, thr_rel, label, floor in (
            ("tokens", thr.token_increase, "token usage", 0.0),
            # sub-second latencies (e.g. mock runs) make relative deltas
            # meaningless noise — only compare when baseline is >=0.5s
            ("latency", thr.latency_increase, "latency", 0.5)):
        b, c = mb[key], mc[key]
        if b and c and b >= floor:
            rel = (c - b) / b
            if rel > thr_rel:
                cats.append("efficiency")
                notes.append(f"{label} +{rel:.0%} (>{thr_rel:.0%} threshold)")
            elif rel < -thr_rel:
                imps.append(f"{label} improved ({rel:.0%})")

    # --- stability ----------------------------------------------------
    vb, vc = mb["variance"], mc["variance"]
    if vc - vb > thr.variance_increase:
        cats.append("stability")
    elif vb - vc > thr.variance_increase:
        imps.append("more stable")
    return cats, imps, notes


def _eval_evidence(rows: list[tuple[RunRecord, EvalResult | None]],
                   limit: int = 4) -> list[str]:
    """Short check-level evidence lines (failures/errors first)."""
    out = []
    for rec, ev in rows:
        if rec.status == "error":
            out.append(f"{rec.run_id}: run error — {rec.error}")
            continue
        if ev is None:
            out.append(f"{rec.run_id}: no eval.yaml")
            continue
        for c in ev.checks:
            if c.status in ("failed", "error"):
                out.append(f"{rec.run_id}: [{c.status}] {c.id} — "
                           f"{c.detail[:90]}")
            elif c.status == "pending":
                out.append(f"{rec.run_id}: [pending] {c.id} — human review")
        if len(out) >= limit:
            break
    return out[:limit]


def _artifact_diff(dir_b: Path | None, dir_c: Path | None) -> dict:
    """Workspace file differences between one representative run per arm."""
    out = {"only_baseline": [], "only_candidate": [], "changed": []}
    if not dir_b or not dir_c:
        return out

    def files(ws: Path) -> dict[str, bytes]:
        return {str(p.relative_to(ws)): p.read_bytes()
                for p in ws.rglob("*") if p.is_file()}

    fb, fc = files(dir_b), files(dir_c)
    out["only_baseline"] = sorted(set(fb) - set(fc))
    out["only_candidate"] = sorted(set(fc) - set(fb))
    out["changed"] = sorted(k for k in set(fb) & set(fc)
                            if fb[k] != fc[k])
    return out


def _first_ws(rows: list[tuple[RunRecord, EvalResult | None]],
              runs_dir: Path) -> Path | None:
    for rec, _ in rows:
        if rec.status == "ok":
            ws = runs_dir / rec.run_id / "workspace"
            if ws.is_dir():
                return ws
    return None


# ----------------------------------------------------------------- analyze --


def analyze(lab: Lab, reg_id: str) -> dict:
    """Recompute the full structured result from stored run data."""
    rdir = lab.d("regressions") / check_id("regression", reg_id)
    meta_file = rdir / "regression.yaml"
    if not meta_file.is_file():
        raise LabError(f"regression '{reg_id}' not found")
    meta = load_yaml(meta_file)
    exp = lab.experiment(meta["experiment"])
    thr = _thresholds(lab, meta.get("thresholds"))
    runs = load_runs(lab, meta["experiment"])
    sid = meta["skill"]
    mode = meta.get("injection_mode", "available")

    per_task = []
    counts: dict[str, int] = {c: 0 for c in CATEGORIES}
    n_improvements = 0
    n_insufficient = 0
    for tid in meta["tasks"]:
        try:
            task = lab.task(tid)
        except LabError:
            task = None
        rb = [(r, e) for r, e in runs
              if r.arm == "baseline" and r.task == tid]
        rc = [(r, e) for r, e in runs
              if r.arm == "candidate" and r.task == tid]
        mb = _side_metrics(sid, rb)
        mc = _side_metrics(sid, rc)
        cats, imps, notes = _classify(task, mb, mc, thr, mode)
        for c in cats:
            counts[c] += 1
        n_improvements += len(imps)
        if mb["n_runs"] < thr.min_runs or mc["n_runs"] < thr.min_runs:
            n_insufficient += 1
        per_task.append({
            "task": tid, "kind": task.kind if task else "missing",
            "baseline": mb, "candidate": mc,
            "categories": cats, "improvements": imps, "notes": notes,
            "runs_baseline": [r.run_id for r, _ in rb],
            "runs_candidate": [r.run_id for r, _ in rc],
            "evidence_baseline": _eval_evidence(rb),
            "evidence_candidate": _eval_evidence(rc),
            "artifacts": _artifact_diff(_first_ws(rb, lab.runs_dir),
                                        _first_ws(rc, lab.runs_dir)),
        })

    all_b = [(r, e) for r, e in runs if r.arm == "baseline"]
    all_c = [(r, e) for r, e in runs if r.arm == "candidate"]
    overview = {"baseline": _side_metrics(sid, all_b),
                "candidate": _side_metrics(sid, all_c)}
    # activation precision/recall across the whole suite (available mode)
    for name, rows in (("baseline", all_b), ("candidate", all_c)):
        pos = [r for r, _ in rows
               if r.status == "ok" and _task_kind(lab, r.task)
               == "activation-positive"]
        neg = [r for r, _ in rows
               if r.status == "ok" and _task_kind(lab, r.task)
               == "activation-negative"]
        tp = sum(1 for r in pos if r.activated(sid))
        fp = sum(1 for r in neg if r.activated(sid))
        overview[name]["activation_recall"] = (
            tp / len(pos)) if pos else None
        overview[name]["activation_precision"] = (
            tp / (tp + fp)) if (tp + fp) else None
        overview[name]["false_activation"] = (
            fp / len(neg)) if neg else None

    total_reg = sum(counts.values())
    if total_reg:
        verdict = "regressed"
    elif n_insufficient == len(per_task) and per_task:
        verdict = "inconclusive"
    else:
        verdict = "clean"
    return {"meta": meta, "exp": exp, "thresholds": thr,
            "tasks": per_task, "overview": overview,
            "counts": counts, "n_improvements": n_improvements,
            "verdict": verdict}


def _task_kind(lab: Lab, tid: str) -> str | None:
    try:
        return lab.task(tid).kind
    except LabError:
        return None


# ------------------------------------------------------------------ report --

def _fmt(x: float | None, pct: bool = False, unit: str = "") -> str:
    if x is None:
        return "—"
    return f"{x:.0%}" if pct else f"{x:.2f}{unit}"


def _delta(b: float | None, c: float | None,
           rel: bool = False) -> str:
    if b is None or c is None:
        return "—"
    d = c - b
    if rel and b:
        return f"{d / b:+.0%}"
    return f"{d:+.2f}"


def build_report(lab: Lab, res: dict) -> str:
    meta = res["meta"]
    ov = res["overview"]
    thr = res["thresholds"]
    skill, base, cand = meta["skill"], meta["baseline"], meta["candidate"]
    lines = [f"# Regression report: `{skill}` `{base}` → `{cand}`", "",
             f"- regression: `{meta['id']}` · experiment: "
             f"`{meta['experiment']}` · created {meta['created']}",
             f"- model: `{meta['model']}` · injection: "
             f"`{meta['injection_mode']}` · harness: `{meta['harness']}`"
             f" · rollouts/arm·task: {meta['rollouts_per_arm']}",
             f"- suite: `{meta['suite']}` ({len(meta['tasks'])} task(s))", ""]
    if str(meta["model"]).startswith("mock"):
        lines += ["> ⚠ **model is `mock` — results are simulated and do NOT"
                  " represent real-world model performance.**", ""]

    v = res["verdict"]
    badge = {"regressed": "🔴 REGRESSED", "clean": "🟢 CLEAN",
             "inconclusive": "🟡 INCONCLUSIVE"}[v]
    lines += [f"## Verdict: {badge}", ""]
    if res["counts"] and any(res["counts"].values()):
        lines += ["| category | tasks |", "|---|---|"]
        for c in CATEGORIES:
            if res["counts"][c]:
                lines.append(f"| {c} | {res['counts'][c]} |")
        lines.append("")
    if res["n_improvements"]:
        lines.append(f"Improvements found: {res['n_improvements']}")
        lines.append("")

    # ---- aggregate metrics ------------------------------------------
    b, c = ov["baseline"], ov["candidate"]
    lines += ["## Metrics overview", "",
              "| metric | baseline | candidate | Δ |", "|---|---|---|---|"]
    rows = [
        ("runs", f"{b['n_runs']}", f"{c['n_runs']}", "—"),
        ("error rate", _fmt(b["error_rate"], 1), _fmt(c["error_rate"], 1),
         _delta(b["error_rate"], c["error_rate"])),
        ("success rate", _fmt(b["success"], 1), _fmt(c["success"], 1),
         _delta(b["success"], c["success"])),
        ("rubric score", _fmt(b["score"]), _fmt(c["score"]),
         _delta(b["score"], c["score"])),
        ("outcome variance", _fmt(b["variance"]), _fmt(c["variance"]),
         _delta(b["variance"], c["variance"])),
        ("tokens/run", _fmt(b["tokens"]), _fmt(c["tokens"]),
         _delta(b["tokens"], c["tokens"], rel=True)),
        ("latency s/run", _fmt(b["latency"]), _fmt(c["latency"]),
         _delta(b["latency"], c["latency"], rel=True)),
        ("turns/run", _fmt(b["turns"]), _fmt(c["turns"]),
         _delta(b["turns"], c["turns"], rel=True)),
    ]
    if meta["injection_mode"] == "available":
        rows += [
            ("activation recall", _fmt(b["activation_recall"], 1),
             _fmt(c["activation_recall"], 1),
             _delta(b["activation_recall"], c["activation_recall"])),
            ("activation precision", _fmt(b["activation_precision"], 1),
             _fmt(c["activation_precision"], 1),
             _delta(b["activation_precision"], c["activation_precision"])),
            ("false-activation", _fmt(b["false_activation"], 1),
             _fmt(c["false_activation"], 1),
             _delta(b["false_activation"], c["false_activation"])),
        ]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    if meta["injection_mode"] != "available":
        lines += ["", "*activation metrics n/a in `injected` mode*"]
    lines.append("")

    # ---- per-task detail ---------------------------------------------
    lines += ["## Per-task results", ""]
    for t in res["tasks"]:
        mb, mc = t["baseline"], t["candidate"]
        flag = "🔴 " + ", ".join(t["categories"]) if t["categories"] \
            else ("🟢 improved: " + "; ".join(t["improvements"])
                  if t["improvements"] else "— no change")
        lines += [f"### `{t['task']}` ({t['kind']}) → {flag}", "",
                  "| | baseline | candidate | Δ |", "|---|---|---|---|",
                  "| runs "
                  f"| {mb['n_runs']} (err {mb['errors']}) "
                  f"| {mc['n_runs']} (err {mc['errors']}) | — |",
                  f"| success | {_fmt(mb['success'], 1)} "
                  f"| {_fmt(mc['success'], 1)} "
                  f"| {_delta(mb['success'], mc['success'])} |",
                  f"| score | {_fmt(mb['score'])} | {_fmt(mc['score'])} "
                  f"| {_delta(mb['score'], mc['score'])} |",
                  f"| activated | {_fmt(mb['activated'], 1)} "
                  f"| {_fmt(mc['activated'], 1)} "
                  f"| {_delta(mb['activated'], mc['activated'])} |",
                  f"| tokens | {_fmt(mb['tokens'])} | {_fmt(mc['tokens'])} "
                  f"| {_delta(mb['tokens'], mc['tokens'], rel=True)} |",
                  f"| latency s | {_fmt(mb['latency'])} "
                  f"| {_fmt(mc['latency'])} "
                  f"| {_delta(mb['latency'], mc['latency'], rel=True)} |",
                  f"| turns | {_fmt(mb['turns'])} | {_fmt(mc['turns'])} "
                  f"| {_delta(mb['turns'], mc['turns'], rel=True)} |",
                  f"| variance | {_fmt(mb['variance'])} "
                  f"| {_fmt(mc['variance'])} "
                  f"| {_delta(mb['variance'], mc['variance'])} |", ""]
        for side, key in (("baseline", "runs_baseline"),
                          ("candidate", "runs_candidate")):
            if t[key]:
                lines.append(f"- {side} runs: "
                             + ", ".join(f"`{r}`" for r in t[key]))
        if mb["incomplete"] or mc["incomplete"]:
            lines.append(f"- ⚠ incomplete evals: baseline "
                         f"{mb['incomplete']}, candidate {mc['incomplete']}"
                         " (not counted as failures)")
        for note in t["notes"]:
            lines.append(f"- ⚠ {note}")
        for side, evs in (("baseline", t["evidence_baseline"]),
                          ("candidate", t["evidence_candidate"])):
            for e in evs:
                lines.append(f"- {side} evidence: {e}")
        art = t["artifacts"]
        if any(art.values()):
            for label, key in (("files only in baseline", "only_baseline"),
                               ("files only in candidate",
                                "only_candidate"),
                               ("files changed", "changed")):
                if art[key]:
                    lines.append(f"- {label}: "
                                 + ", ".join(f"`{f}`" for f in art[key]))
        lines.append("")

    lines += ["## Reproduce", "",
              f"```\nlab regression report {meta['id']}\n"
              f"lab report {meta['experiment']}\n"
              f"lab compare {meta['experiment']}\n```", ""]
    return "\n".join(lines)


def write_report(lab: Lab, reg_id: str) -> Path:
    res = analyze(lab, reg_id)
    rdir = lab.d("regressions") / reg_id
    (rdir / "report.md").write_text(build_report(lab, res))
    dump_yaml({"id": reg_id, "verdict": res["verdict"],
               "counts": res["counts"],
               "tasks": [{k: t[k] for k in
                          ("task", "kind", "categories", "improvements",
                           "notes", "baseline", "candidate")}
                         for t in res["tasks"]]},
              rdir / "report.yaml")
    meta = load_yaml(rdir / "regression.yaml")
    meta["status"] = "analyzed"
    meta["verdict"] = res["verdict"]
    dump_yaml(meta, rdir / "regression.yaml")
    return rdir / "report.md"


def list_regressions(lab: Lab) -> list[dict]:
    rdir = lab.d("regressions")
    out = []
    if rdir.is_dir():
        for d in sorted(rdir.iterdir()):
            f = d / "regression.yaml"
            if f.is_file():
                out.append(load_yaml(f))
    return out
