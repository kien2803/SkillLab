"""`lab` CLI — the user-facing entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .lab import Lab, LabError
from .models import (Arm, Check, Experiment, FixedConfig, RunRecord,
                     SkillRelevance, TaskSpec, dump_yaml, load_yaml)

TASK_TEMPLATE = """\
id: {tid}
kind: performance            # performance | activation-positive | activation-negative
prompt: |
  TODO: describe the task the agent must complete.
fixtures: []                 # dirs under this task dir copied into the workspace
skill_relevance:
  expected: []               # activation-positive: skills that SHOULD trigger
  unexpected: []             # activation-negative: skills that should NOT trigger
rubric: null
deterministic_checks: []
  # - type: file-exists
  #   path: OUTPUT.md
  # - type: command
  #   command: "pytest -q"
"""

EXP_TEMPLATE = """\
id: {eid}
title: ""
hypothesis: "TODO: a falsifiable claim about the independent variable"
independent_var: skill_variant
created: "{today}"
status: designed
fixed:
  model: {model}
  temperature: 0.0
  seed_policy: varied
  harness: standard-tools-v1
  injection_mode: available   # available = measure trigger | injected = measure content
arms:
  - name: control
    skill: null
  - name: treatment
    skill: "TODO@variant"     # skill-id@variant-id
tasks: []                     # task ids from the task bank
rollouts_per_arm: {n}
metrics: [activation_rate, false_activation, rubric_score, token_cost, turns]
conclusion: null
insights_generated: []
"""

RUBRIC_TEMPLATE = """\
id: {rid}
criteria:
  - id: success
    weight: 0.6
    method: deterministic
    check: file-exists        # must match a deterministic_check id/name on the task
  - id: quality
    weight: 0.4
    method: llm-judge
    judge_prompt: |
      Rate the overall quality of the agent's output for this task.
    scale: 1-5
"""


def _lab(args) -> Lab:
    return Lab.find()


def _err(e: Exception) -> int:
    print(f"error: {e}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------- commands --

def cmd_init(args) -> int:
    lab = Lab.init(Path(args.dir or ".").resolve())
    print(f"initialized lab at {lab.root}")
    return 0


def cmd_skill_new(args) -> int:
    from .registry import new_skill
    d = new_skill(_lab(args), args.id, args.kind)
    print(f"created {d}")
    return 0


def cmd_skill_add(args) -> int:
    from .registry import add_skill
    d = add_skill(_lab(args), args.path, args.variant, args.id)
    print(f"imported into {d}")
    return 0


def cmd_skill_scan(args) -> int:
    """Discover skills in well-known locations (~/.agents/skills, .claude/…)."""
    from .registry import scan_skill_dirs, skill_entry_file
    from .models import parse_frontmatter
    lab = _lab(args)
    found = scan_skill_dirs()
    if not found:
        print("no skills found in known locations")
        return 0
    if not args.do_import:
        for d in found:
            entry = skill_entry_file(d)
            fm, _ = parse_frontmatter(entry.read_text()) if entry else ({}, "")
            print(f"{d}  ({fm.get('name') or d.name})")
        print(f"{len(found)} skill(s) found — `lab skill scan --import` "
              "to import all")
        return 0
    from .registry import add_skill
    n = 0
    for d in found:
        try:
            add_skill(lab, d)
            n += 1
            print(f"imported {d}")
        except LabError as e:
            print(f"skipped {d}: {e}", file=sys.stderr)
    print(f"{n} skill(s) imported")
    return 0


def cmd_skill_list(args) -> int:
    lab = _lab(args)
    for m in lab.skills():
        vs = ", ".join(v.id for v in m.variants) or "(no variants)"
        print(f"{m.id:30} {m.kind:15} {m.status:10} variants: {vs}")
    return 0


def cmd_skill_evaluate(args) -> int:
    from .graduation import evaluate_skill
    rep = evaluate_skill(_lab(args), args.id)
    print(f"graduation check: {rep.skill_id} ({rep.n_runs} runs)")
    if rep.activation_rate is not None:
        print(f"  activation rate:      {rep.activation_rate:.0%}")
    if rep.false_activation_rate is not None:
        print(f"  false activation:     {rep.false_activation_rate:.0%}")
    for ref, r in sorted(rep.by_ref.items()):
        a = f"{sum(r['act'])/len(r['act']):.0%}" if r["act"] else "—"
        f_ = f"{sum(r['false'])/len(r['false']):.0%}" if r["false"] else "—"
        print(f"    {ref:30} act={a} false={f_}")
    for tid, d in rep.task_deltas.items():
        print(f"  delta on {tid:25} {d:+.2f}")
    print()
    ok = True
    for name, passed, detail in rep.verdicts:
        mark = "?" if passed is None else ("PASS" if passed else "FAIL")
        if passed is False:
            ok = False
        print(f"  [{mark:4}] {name:18} {detail}")
    print(f"\nverdict: {'GRADUATED' if ok else 'not yet'}")
    return 0


def cmd_skill_show(args) -> int:
    from .registry import skill_description
    lab = _lab(args)
    meta = lab.skill(args.id)
    print(yaml.safe_dump(meta.model_dump(mode="json"), sort_keys=False,
                         allow_unicode=True))
    for v in meta.variants:
        vdir = lab.skills_dir / meta.id / v.path
        print(f"  {v.id}: {vdir}")
        print(f"    desc: {skill_description(vdir)[:100]}")
    return 0


def cmd_analyze(args) -> int:
    from .analyzer import analyze_registry_conflicts, analyze_skill
    lab = _lab(args)
    n = 0
    ids = [args.id] if args.id else [m.id for m in lab.skills()]
    for sid in ids:
        for vid, findings in analyze_skill(lab, sid).items():
            for f in findings:
                print(f"{sid}@{vid}: {f.fmt()}")
                n += 1
    for f in analyze_registry_conflicts(lab):
        print(f"registry: {f.fmt()}")
        n += 1
    if not n:
        print("no findings")
    return 0


def cmd_task_new(args) -> int:
    lab = _lab(args)
    d = lab.tasks_dir / args.id
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.yaml").write_text(TASK_TEMPLATE.format(tid=args.id))
    print(f"created {d/'task.yaml'} — edit prompt/checks, add fixtures/")
    return 0


def cmd_task_list(args) -> int:
    for t in _lab(args).tasks():
        print(f"{t.id:30} {t.kind}")
    return 0


def cmd_rubric_new(args) -> int:
    lab = _lab(args)
    p = lab.rubrics_dir / f"{args.id}.yaml"
    p.write_text(RUBRIC_TEMPLATE.format(rid=args.id))
    print(f"created {p}")
    return 0


def cmd_experiment_new(args) -> int:
    import datetime
    lab = _lab(args)
    d = lab.experiments_dir / args.id
    d.mkdir(parents=True, exist_ok=True)
    (d / "experiment.yaml").write_text(EXP_TEMPLATE.format(
        eid=args.id, model=lab.cfg["model"], n=lab.cfg["rollouts_per_arm"],
        today=datetime.date.today().isoformat()))
    print(f"created {d/'experiment.yaml'} — fill in arms/tasks/hypothesis")
    return 0


def cmd_experiment_list(args) -> int:
    lab = _lab(args)
    from .report import load_runs
    if not lab.experiments_dir.is_dir():
        return 0
    for d in sorted(lab.experiments_dir.iterdir()):
        if not (d / "experiment.yaml").is_file():
            continue
        exp = lab.experiment(d.name)
        n = len(load_runs(lab, exp.id))
        print(f"{exp.id:35} {exp.status:10} arms={len(exp.arms):2} "
              f"runs={n:3} {exp.title or exp.hypothesis[:50]}")
    return 0


def _run_and_eval(lab: Lab, exp: Experiment, arm_filter: str | None,
                  limit: int | None, batch: str | None,
                  model_override: str | None, force: bool = False) -> int:
    from .engine import planned_run_ids, run_rollout, validate_experiment
    from .evaluate import evaluate_run
    if exp.status == "concluded":
        raise LabError(f"experiment '{exp.id}' is concluded (immutable) — "
                       "start a new experiment instead of overwriting history")
    errors, warns = validate_experiment(lab, exp)
    for w in warns:
        print(f"warn: {w}", file=sys.stderr)
    if errors:
        raise LabError("experiment invalid:\n  - " + "\n  - ".join(errors))
    if model_override:
        exp.fixed.model = model_override  # in-memory only — config unchanged
    planned = planned_run_ids(exp, arm_filter, limit, batch)
    existing = [r for r in planned
                if (lab.runs_dir / r / "run.yaml").is_file()]
    if existing and not force:
        raise LabError(
            f"{len(existing)}/{len(planned)} planned run(s) already exist "
            f"(e.g. {existing[0]}) — refusing to overwrite. Use `lab rerun "
            "--batch <name>` for a new batch, or --force to overwrite.")
    exp.status = "running"
    exp.save(lab.exp_dir(exp.id))
    done = 0
    for arm in exp.arms:
        if arm_filter and arm.name != arm_filter:
            continue
        for tid in exp.tasks:
            n = exp.rollouts_per_arm if not limit else min(
                limit, exp.rollouts_per_arm)
            for i in range(n):
                rec = run_rollout(lab, exp, arm, tid, i, batch,
                                  overwrite=force)
                try:
                    ev = evaluate_run(lab, rec, lab.task(tid),
                                      lab.runs_dir / rec.run_id)
                    tag = "ERR " if rec.status == "error" else "ok  "
                    print(f"{tag}{rec.run_id} eval={ev.status}"
                          f" score={ev.rubric_score}")
                except Exception as e:  # noqa: BLE001 - don't kill the batch
                    print(f"warn eval failed for {rec.run_id}: "
                          f"{type(e).__name__}: {e}", file=sys.stderr)
                done += 1
    print(f"{done} rollout(s) completed")
    return 0


def cmd_run(args) -> int:
    lab = _lab(args)
    return _run_and_eval(lab, lab.experiment(args.exp), args.arm,
                         args.limit, args.batch, None, args.force)


def cmd_rerun(args) -> int:
    """Re-run an experiment; --model overrides the fixed model (drift probe).

    Records land under a new --batch suffix so history is append-only.
    """
    import re
    lab = _lab(args)
    exp = lab.experiment(args.exp)
    batch = args.batch
    if args.model and args.model != exp.fixed.model and not batch:
        batch = re.sub(r"[^a-z0-9-]+", "-", args.model.lower())[:40]
        print(f"note: model override without --batch → batch '{batch}'")
    if batch is None:
        print("warning: rerun without --batch reuses base run ids",
              file=sys.stderr)
    return _run_and_eval(lab, exp, args.arm, args.limit, batch, args.model,
                         args.force)


def cmd_eval(args) -> int:
    """Re-evaluate a run, or enter human scores (--score crit=val)."""
    from .evaluate import apply_human_scores, evaluate_run
    lab = _lab(args)
    run_dir = lab.runs_dir / args.run_id
    if not (run_dir / "run.yaml").is_file():
        raise LabError(f"run '{args.run_id}' not found")
    rec = RunRecord(**load_yaml(run_dir / "run.yaml"))
    task = lab.task(rec.task)
    if args.score:
        scores: dict[str, float] = {}
        for kv in args.score:
            k, sep, v = kv.partition("=")
            if not sep or not k:
                raise LabError(f"--score expects 'criterion=value', got '{kv}'")
            try:
                scores[k] = float(v)
            except ValueError as e:
                raise LabError(f"--score value must be a number: '{kv}'") from e
        comments: dict[str, str] = {}
        for kv in args.comment or []:
            k, sep, v = kv.partition("=")
            if not sep or not k:
                raise LabError("--comment expects 'criterion=text', "
                               f"got '{kv}'")
            comments[k] = v
        ev = apply_human_scores(lab, rec, task, run_dir, scores, comments)
        print(f"applied human score(s): {', '.join(sorted(scores))}")
    else:
        ev = evaluate_run(lab, rec, task, run_dir)
    print(f"eval={ev.status} success={ev.success} "
          f"rubric_score={ev.rubric_score}")
    for c in ev.checks:
        print(f"  {c.id:20} {c.method:14} {c.status:8} score={c.score}")
    return 0


def cmd_transcript(args) -> int:
    lab = _lab(args)
    p = lab.runs_dir / args.run_id / "transcript.jsonl"
    if not p.is_file():
        raise LabError(f"no transcript for run '{args.run_id}'")
    import json
    limit = None if args.full else 300
    for line in p.read_text().splitlines():
        m = json.loads(line)
        role = m.get("role", "?")
        if role == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                print(f"assistant→{tc['function']['name']}"
                      f"({tc['function']['arguments'][:200]})")
        else:
            name = f" [{m['name']}]" if m.get("name") else ""
            content = m.get("content") or ""
            if limit and len(content) > limit:
                content = content[:limit] + "…"
            print(f"{role}{name}: {content}")
    return 0


def cmd_diff(args) -> int:
    """Unified diff of two runs: transcript flow + workspace outputs."""
    import difflib
    import json
    lab = _lab(args)
    dirs = [lab.runs_dir / r for r in (args.run_a, args.run_b)]
    for d, rid in zip(dirs, (args.run_a, args.run_b)):
        if not (d / "run.yaml").is_file():
            raise LabError(f"run '{rid}' not found")

    def norm(run_dir: Path) -> list[str]:
        out = []
        tp = run_dir / "transcript.jsonl"
        if tp.is_file():
            for line in tp.read_text().splitlines():
                m = json.loads(line)
                if m.get("role") == "assistant" and m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        out.append(f"assistant→{tc['function']['name']}"
                                   f" {tc['function']['arguments'][:200]}")
                else:
                    nm = f"[{m['name']}] " if m.get("name") else ""
                    out.append(f"{m.get('role','?')} {nm}"
                               f"{(m.get('content') or '')[:300]}")
        return out

    print(f"--- transcript diff: {args.run_a} vs {args.run_b}")
    tdiff = list(difflib.unified_diff(
        norm(dirs[0]), norm(dirs[1]),
        fromfile=args.run_a, tofile=args.run_b, lineterm="", n=2))
    print("\n".join(tdiff) if tdiff else "(transcripts identical)")

    ws_a, ws_b = (d / "workspace" for d in dirs)
    files_a = {p.relative_to(ws_a) for p in ws_a.rglob("*") if p.is_file()}
    files_b = {p.relative_to(ws_b) for p in ws_b.rglob("*") if p.is_file()}
    added, removed = files_b - files_a, files_a - files_b
    if added or removed:
        print("\n--- workspace files")
        for f in sorted(added):
            print(f"+ {f}")
        for f in sorted(removed):
            print(f"- {f}")
    for f in sorted(files_a & files_b):
        ta, tb = (ws_a / f).read_text(errors="replace").splitlines(), \
                 (ws_b / f).read_text(errors="replace").splitlines()
        if ta != tb:
            print(f"\n--- diff {f}")
            print("\n".join(difflib.unified_diff(
                ta, tb, fromfile=f"a/{f}", tofile=f"b/{f}", lineterm="")))
    return 0


def cmd_status(args) -> int:
    lab = _lab(args)
    print(f"lab:   {lab.root}")
    print(f"model: {lab.cfg['model']} (judge: {lab.cfg['judge_model']})"
          f" · sandbox: {lab.cfg.get('sandbox') or 'off'}")
    counts = {d: sum(1 for p in lab.d(d).rglob("*") if p.is_file()
                     and p.name != ".gitkeep") for d in
              ("skills", "tasks", "rubrics", "experiments",
               "insights", "principles")}
    n_runs = sum(1 for d in lab.runs_dir.iterdir()
                 if (d / "run.yaml").is_file()) \
        if lab.runs_dir.is_dir() else 0
    print("files: " + "  ".join(f"{k}={v}" for k, v in counts.items())
          + f"  runs={n_runs}")
    warns = []
    for m in lab.skills():
        if not m.variants:
            warns.append(f"skill '{m.id}' has no variants")
    for t in lab.tasks():
        for fx in t.fixtures:
            if not (lab.task_dir(t.id) / fx).exists():
                warns.append(f"task '{t.id}': missing fixture '{fx}'")
    n_noeval = sum(1 for d in lab.runs_dir.iterdir()
                   if (d / "run.yaml").is_file()
                   and not (d / "eval.yaml").is_file()) \
        if lab.runs_dir.is_dir() else 0
    if n_noeval:
        warns.append(f"{n_noeval} run(s) missing eval.yaml — run `lab eval`")
    for w in warns:
        print(f"  warn: {w}")
    return 0


def cmd_insight_show(args) -> int:
    lab = _lab(args)
    for d in (lab.insights_dir, lab.principles_dir):
        p = d / f"{args.id}.md"
        if p.is_file():
            print(p.read_text())
            return 0
    raise LabError(f"insight '{args.id}' not found")


def cmd_experiment_conclude(args) -> int:
    lab = _lab(args)
    exp = lab.experiment(args.exp)
    exp.status = "concluded"
    exp.conclusion = args.conclusion
    for i in args.insight or []:
        if i not in exp.insights_generated:
            exp.insights_generated.append(i)
    exp.save(lab.exp_dir(exp.id))
    print(f"{exp.id} → concluded")
    if exp.insights_generated:
        print(f"  insights: {', '.join(exp.insights_generated)}")
    return 0


def cmd_report(args) -> int:
    from .report import write_report
    p = write_report(_lab(args), args.exp)
    print(p.read_text())
    print(f"written to {p}", file=sys.stderr)
    return 0


def cmd_runs(args) -> int:
    from .report import load_runs
    for rec, ev in load_runs(_lab(args), args.exp):
        s = f" score={ev.rubric_score:.2f}" if ev and ev.rubric_score is not None else ""
        print(f"{rec.arm:15} {rec.task:25} {rec.status:5} "
              f"turns={rec.usage.turns} tok={rec.usage.input_tokens}{s}")
    return 0


def cmd_ui(args) -> int:
    from .ui import generate
    out = generate(_lab(args))
    print(f"dashboard written to {out}/index.html")
    if args.open:
        import webbrowser
        webbrowser.open((out / "index.html").as_uri())
    return 0


def cmd_export(args) -> int:
    from .share import export_pack
    out = export_pack(_lab(args), Path(args.out), args.tasks)
    print(f"pack written to {out} ({out / 'pack.yaml'})")
    return 0


def cmd_import(args) -> int:
    from .share import import_pack
    res = import_pack(_lab(args), Path(args.src), args.force)
    for d, n in res["imported"].items():
        print(f"imported {n} file(s) into {d}/")
    for s in res["skipped"]:
        print(f"skipped existing {s} (use --force to overwrite)")
    for s in res["rejected"]:
        print(f"rejected {s}", file=sys.stderr)
    if res["rejected"]:
        print(f"{len(res['rejected'])} file(s) rejected",
              file=sys.stderr)
    return 0


def cmd_insight_new(args) -> int:
    from .insights import new_insight
    p = new_insight(_lab(args), args.title, args.evidence or "")
    print(f"created {p}")
    return 0


def cmd_insight_list(args) -> int:
    from .insights import list_insights
    term = (args.search or "").lower()
    for i in list_insights(_lab(args)):
        if term:
            hay = f"{i['id']} {i['status']} {i['confidence']} " \
                  f"{Path(i['path']).read_text()}"
            if term not in hay.lower():
                continue
        print(f"{i['kind']:10} {i['status']:10} {i['confidence']:10} {i['id']}")
    return 0


def cmd_insight_promote(args) -> int:
    from .insights import promote
    p = promote(_lab(args), args.id)
    print(f"promoted -> {p}")
    return 0


def cmd_insight_refute(args) -> int:
    from .insights import refute
    p = refute(_lab(args), args.id)
    print(f"refuted -> {p}")
    return 0


def cmd_insight_confirm(args) -> int:
    from .insights import confirm
    p = confirm(_lab(args), args.id)
    print(f"confirmed -> {p}")
    return 0


def cmd_experiment_validate(args) -> int:
    """Dry-run the pre-flight checks — no run dirs, no LLM calls."""
    from .engine import validate_experiment
    lab = _lab(args)
    exp = lab.experiment(args.exp)
    errors, warnings = validate_experiment(lab, exp)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    if errors:
        print(f"experiment '{exp.id}' is INVALID ({len(errors)} error(s))",
              file=sys.stderr)
        return 1
    print(f"experiment '{exp.id}' is valid"
          + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 0


def cmd_compare(args) -> int:
    from .report import compare_table
    print(compare_table(_lab(args), args.exp))
    return 0


def cmd_regression_run(args) -> int:
    from .regression import run_regression
    lab = _lab(args)
    overrides: dict[str, float] = {}
    for kv in args.threshold or []:
        k, sep, v = kv.partition("=")
        if not sep or not k:
            raise LabError(f"--threshold expects 'key=value', got '{kv}'")
        try:
            overrides[k] = float(v)
        except ValueError as e:
            raise LabError(f"--threshold value must be a number: '{kv}'") from e
    reg_id = run_regression(
        lab, args.skill, args.baseline, args.candidate, args.tasks,
        model=args.model, mode=args.mode, rollouts=args.rollouts,
        overrides=overrides or None)
    report = lab.d("regressions") / reg_id / "report.md"
    print(f"regression '{reg_id}' complete — report: {report}")
    return 0


def cmd_regression_report(args) -> int:
    from .regression import write_report
    lab = _lab(args)
    p = write_report(lab, args.id)
    print(p.read_text())
    print(f"(written to {p})")
    return 0


def cmd_regression_list(args) -> int:
    from .regression import list_regressions
    regs = list_regressions(_lab(args))
    if not regs:
        print("no regressions recorded yet")
        return 0
    for r in regs:
        verdict = r.get("verdict") or "—"
        print(f"{r['id']:44} {r.get('skill','?'):20} "
              f"{r.get('baseline','?')}→{r.get('candidate','?'):12} "
              f"{r.get('status','?'):9} {verdict}")
    return 0


# ------------------------------------------------------------------- parser --

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lab", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.add_argument("dir", nargs="?"); s.set_defaults(f=cmd_init)

    s = sub.add_parser("skill"); ss = s.add_subparsers(dest="sub", required=True)
    x = ss.add_parser("new"); x.add_argument("id"); x.add_argument("--kind", default="skill-md"); x.set_defaults(f=cmd_skill_new)
    x = ss.add_parser("add"); x.add_argument("path"); x.add_argument("--variant"); x.add_argument("--id"); x.set_defaults(f=cmd_skill_add)
    x = ss.add_parser("scan"); x.add_argument("--import", dest="do_import", action="store_true"); x.set_defaults(f=cmd_skill_scan)
    x = ss.add_parser("list"); x.set_defaults(f=cmd_skill_list)
    x = ss.add_parser("show"); x.add_argument("id"); x.set_defaults(f=cmd_skill_show)
    x = ss.add_parser("evaluate"); x.add_argument("id"); x.set_defaults(f=cmd_skill_evaluate)

    s = sub.add_parser("analyze"); s.add_argument("id", nargs="?"); s.set_defaults(f=cmd_analyze)

    s = sub.add_parser("task"); ss = s.add_subparsers(dest="sub", required=True)
    x = ss.add_parser("new"); x.add_argument("id"); x.set_defaults(f=cmd_task_new)
    x = ss.add_parser("list"); x.set_defaults(f=cmd_task_list)

    s = sub.add_parser("rubric"); ss = s.add_subparsers(dest="sub", required=True)
    x = ss.add_parser("new"); x.add_argument("id"); x.set_defaults(f=cmd_rubric_new)

    s = sub.add_parser("experiment"); ss = s.add_subparsers(dest="sub", required=True)
    x = ss.add_parser("new"); x.add_argument("id"); x.set_defaults(f=cmd_experiment_new)
    x = ss.add_parser("list"); x.set_defaults(f=cmd_experiment_list)
    x = ss.add_parser("conclude"); x.add_argument("exp"); x.add_argument("--conclusion", required=True); x.add_argument("--insight", action="append"); x.set_defaults(f=cmd_experiment_conclude)
    x = ss.add_parser("validate"); x.add_argument("exp"); x.set_defaults(f=cmd_experiment_validate)

    s = sub.add_parser("run"); s.add_argument("exp"); s.add_argument("--arm"); s.add_argument("--limit", type=int); s.add_argument("--batch"); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_run)
    s = sub.add_parser("rerun"); s.add_argument("exp"); s.add_argument("--arm"); s.add_argument("--limit", type=int); s.add_argument("--model"); s.add_argument("--batch"); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_rerun)
    s = sub.add_parser("eval"); s.add_argument("run_id"); s.add_argument("--score", action="append"); s.add_argument("--comment", action="append"); s.set_defaults(f=cmd_eval)
    s = sub.add_parser("compare"); s.add_argument("exp"); s.set_defaults(f=cmd_compare)

    s = sub.add_parser("regression"); ss = s.add_subparsers(dest="sub", required=True)
    x = ss.add_parser("run"); x.add_argument("skill"); x.add_argument("--baseline", required=True); x.add_argument("--candidate", required=True); x.add_argument("--tasks", default="default"); x.add_argument("--model"); x.add_argument("--mode", choices=["available", "injected"]); x.add_argument("--rollouts", type=int); x.add_argument("--threshold", action="append"); x.set_defaults(f=cmd_regression_run)
    x = ss.add_parser("report"); x.add_argument("id"); x.set_defaults(f=cmd_regression_report)
    x = ss.add_parser("list"); x.set_defaults(f=cmd_regression_list)
    s = sub.add_parser("transcript"); s.add_argument("run_id"); s.add_argument("--full", action="store_true"); s.set_defaults(f=cmd_transcript)
    s = sub.add_parser("diff"); s.add_argument("run_a"); s.add_argument("run_b"); s.set_defaults(f=cmd_diff)
    s = sub.add_parser("status"); s.set_defaults(f=cmd_status)
    s = sub.add_parser("report"); s.add_argument("exp"); s.set_defaults(f=cmd_report)
    s = sub.add_parser("runs"); s.add_argument("exp"); s.set_defaults(f=cmd_runs)

    s = sub.add_parser("ui"); s.add_argument("--open", action="store_true"); s.set_defaults(f=cmd_ui)
    s = sub.add_parser("export"); s.add_argument("out"); s.add_argument("--tasks", action="store_true"); s.set_defaults(f=cmd_export)
    s = sub.add_parser("import"); s.add_argument("src"); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_import)

    s = sub.add_parser("insight"); ss = s.add_subparsers(dest="sub", required=True)
    x = ss.add_parser("new"); x.add_argument("title"); x.add_argument("--evidence"); x.set_defaults(f=cmd_insight_new)
    x = ss.add_parser("list"); x.add_argument("--search"); x.set_defaults(f=cmd_insight_list)
    x = ss.add_parser("show"); x.add_argument("id"); x.set_defaults(f=cmd_insight_show)
    x = ss.add_parser("promote"); x.add_argument("id"); x.set_defaults(f=cmd_insight_promote)
    x = ss.add_parser("refute"); x.add_argument("id"); x.set_defaults(f=cmd_insight_refute)
    x = ss.add_parser("confirm"); x.add_argument("id"); x.set_defaults(f=cmd_insight_confirm)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.f(args)
    except (LabError, ValueError, FileNotFoundError) as e:
        return _err(e)


if __name__ == "__main__":
    sys.exit(main())
