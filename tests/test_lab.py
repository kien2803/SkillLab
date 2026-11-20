"""End-to-end test of the lab pipeline using the mock model (offline)."""

from pathlib import Path

import pytest

from skilllab.analyzer import analyze_skill
from skilllab.cli import main
from skilllab.engine import run_experiment
from skilllab.evaluate import evaluate_run
from skilllab.lab import Lab, LabError
from skilllab.models import Experiment
from skilllab.report import build_report, load_runs


SKILL_MD = """\
---
name: commit-helper
description: >-
  Use when the user asks to write or improve a git commit message, draft a
  changelog entry, or summarize staged changes for a commit.
---

# Commit Helper

Write commit messages in conventional-commit style. See `resources/style.md`.
"""

TASK_YAML = """\
id: write-commit-msg
kind: activation-positive
prompt: |
  Please write a git commit message for the staged changes in this repo.
fixtures: []
skill_relevance:
  expected: [commit-helper]
  unexpected: []
deterministic_checks:
  - type: file-exists
    path: OUTPUT.md
"""

NEG_TASK_YAML = """\
id: unrelated-refactor
kind: activation-negative
prompt: |
  Refactor the sorting function in this workspace for readability.
fixtures: []
skill_relevance:
  expected: []
  unexpected: [commit-helper]
deterministic_checks:
  - type: file-exists
    path: OUTPUT.md
"""

EXP_YAML = """\
id: exp-test-trigger
title: trigger test
hypothesis: commit-helper activates on commit tasks but not refactors
independent_var: skill_variant
fixed:
  model: mock
  temperature: 0.0
  seed_policy: varied
  harness: standard-tools-v1
  injection_mode: available
arms:
  - name: control
    skill: null
  - name: treatment
    skill: commit-helper@v1
tasks: [write-commit-msg, unrelated-refactor]
rollouts_per_arm: 3
"""


@pytest.fixture()
def lab(tmp_path: Path, monkeypatch) -> Lab:
    lab = Lab.init(tmp_path)
    sd = tmp_path / "skills" / "commit-helper" / "variants" / "v1"
    sd.mkdir(parents=True)
    (sd / "SKILL.md").write_text(SKILL_MD)
    (sd / "resources").mkdir()
    (sd / "resources" / "style.md").write_text("# Style\nBe terse.")
    (tmp_path / "skills" / "commit-helper" / "skill.yaml").write_text(
        "id: commit-helper\nkind: skill-md\nstatus: testing\n"
        "variants:\n  - id: v1\n    path: variants/v1\n")
    for name, content in (("write-commit-msg", TASK_YAML),
                          ("unrelated-refactor", NEG_TASK_YAML)):
        td = tmp_path / "tasks" / name
        td.mkdir()
        (td / "task.yaml").write_text(content)
    ed = tmp_path / "experiments" / "exp-test-trigger"
    ed.mkdir()
    (ed / "experiment.yaml").write_text(EXP_YAML)
    monkeypatch.chdir(tmp_path)
    return lab


def test_analyzer_clean_skill(lab):
    findings = analyze_skill(lab, "commit-helper")["v1"]
    assert not [f for f in findings if f.severity == "error"], findings


def test_mock_rollout_activates_and_evaluates(lab):
    exp = lab.experiment("exp-test-trigger")
    records = run_experiment(lab, exp.id, limit=1)
    assert len(records) == 4  # 2 arms x 2 tasks x 1 rollout
    treat = [r for r in records if r.arm == "treatment"
             and r.task == "write-commit-msg"][0]
    assert treat.status == "ok"
    assert treat.activated("commit-helper")
    run_dir = lab.runs_dir / treat.run_id
    assert (run_dir / "transcript.jsonl").exists()
    ev = evaluate_run(lab, treat, lab.task("write-commit-msg"), run_dir)
    assert ev.success  # mock wrote OUTPUT.md


def test_report_aggregates(lab):
    records = run_experiment(lab, "exp-test-trigger", limit=3)
    for rec in records:
        evaluate_run(lab, rec, lab.task(rec.task),
                     lab.runs_dir / rec.run_id)
    runs = load_runs(lab, "exp-test-trigger")
    assert len(runs) == 12
    text = build_report(lab, lab.experiment("exp-test-trigger"))
    assert "treatment" in text and "control" in text
    assert "activation" in text


def test_cli_end_to_end(lab, capsys):
    assert main(["run", "exp-test-trigger", "--limit", "1"]) == 0
    assert main(["report", "exp-test-trigger"]) == 0
    out = capsys.readouterr().out
    assert "Report: exp-test-trigger" in out
    assert main(["insight", "new", "Trigger wording matters",
                 "--evidence", "exp-test-trigger"]) == 0
    assert main(["insight", "list"]) == 0
    assert "trigger-wording-matters" in capsys.readouterr().out


def test_rerun_batch_keeps_history(lab):
    assert main(["run", "exp-test-trigger", "--limit", "1"]) == 0
    assert main(["rerun", "exp-test-trigger", "--limit", "1",
                 "--batch", "b2"]) == 0
    ids = {d.name for d in lab.runs_dir.iterdir()}
    assert any(i.endswith("--b2") for i in ids)
    assert any(not i.endswith("--b2") for i in ids)


def test_eval_and_transcript(lab, capsys):
    assert main(["run", "exp-test-trigger", "--limit", "1"]) == 0
    run_id = next(d.name for d in lab.runs_dir.iterdir())
    assert main(["eval", run_id]) == 0
    assert "success=" in capsys.readouterr().out
    assert main(["transcript", run_id]) == 0
    assert "read_skill" in capsys.readouterr().out or "write_file" \
        in capsys.readouterr().out


def test_principle_lint_feedback(lab):
    (lab.principles_dir / "p1.md").write_text("""\
---
id: needs-trigger-words
lint:
  - field: description
    pattern: 'use when'
    negate: true
    severity: warn
    message: no concrete trigger condition
---
body
""")
    bad = lab.skills_dir / "vague" / "variants" / "v1"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_text(
        "---\nname: vague\ndescription: Helps with stuff and things.\n---\n")
    (lab.skills_dir / "vague" / "skill.yaml").write_text(
        "id: vague\nvariants:\n  - id: v1\n    path: variants/v1\n")
    findings = analyze_skill(lab, "vague")["v1"]
    assert any(f.check == "principle-conformance" for f in findings)
    # existing good skill passes the principle (has 'Use when')
    good = analyze_skill(lab, "commit-helper")["v1"]
    assert not [f for f in good if f.check == "principle-conformance"]


def test_report_suggests_insights(lab):
    records = run_experiment(lab, "exp-test-trigger", limit=1)
    for rec in records:
        evaluate_run(lab, rec, lab.task(rec.task),
                     lab.runs_dir / rec.run_id)
    text = build_report(lab, lab.experiment("exp-test-trigger"))
    assert "Suggested insights" in text
    assert "Skill usage" in text


def test_export_import_pack(lab, tmp_path):
    main(["insight", "new", "Some insight", "--evidence", "exp-test-trigger"])
    pack = tmp_path / "pack"
    assert main(["export", str(pack), "--tasks"]) == 0
    assert (pack / "pack.yaml").is_file()
    assert (pack / "insights" / "some-insight.md").is_file()
    assert (pack / "tasks").is_dir()

    lab2 = Lab.init(tmp_path / "lab2")
    import os
    cwd = os.getcwd()
    os.chdir(tmp_path / "lab2")
    try:
        assert main(["import", str(pack)]) == 0
    finally:
        os.chdir(cwd)
    assert (tmp_path / "lab2" / "insights" / "some-insight.md").is_file()
    assert (tmp_path / "lab2" / "tasks" / "write-commit-msg"
            / "task.yaml").is_file()


def test_by_model_report_section(lab):
    records = run_experiment(lab, "exp-test-trigger", limit=1)
    for rec in records:
        evaluate_run(lab, rec, lab.task(rec.task),
                     lab.runs_dir / rec.run_id)
    # simulate a rerun batch on a different model
    for rec in run_experiment(lab, "exp-test-trigger", limit=1, batch="gpt"):
        evaluate_run(lab, rec, lab.task(rec.task),
                     lab.runs_dir / rec.run_id)
        ry = lab.runs_dir / rec.run_id / "run.yaml"
        data = rec.model_dump(mode="json")
        data["model"]["name"] = "gpt-4o"
        import yaml as _y
        ry.write_text(_y.safe_dump(data, sort_keys=False))
    text = build_report(lab, lab.experiment("exp-test-trigger"))
    assert "By model" in text and "gpt-4o" in text


def test_ui_generation(lab):
    run_experiment(lab, "exp-test-trigger", limit=1)
    from skilllab.ui import generate
    out = generate(lab)
    index = (out / "index.html").read_text()
    assert "exp-test-trigger" in index  # recent runs link to the experiment
    skills = (out / "skills.html").read_text()
    assert "commit-helper" in skills
    assert (out / "benchmarks.html").is_file()
    assert (out / "regressions.html").is_file()
    assert (out / "experiments.html").is_file()
    assert "exp-test-trigger" in (out / "experiments.html").read_text()
    assert (out / "skill-commit-helper.html").is_file()
    run_page = next(out.glob("run-*.html"))
    assert "ranscript" in run_page.read_text()


def test_ui_empty_states(tmp_path, monkeypatch):
    """A fresh lab renders every page with empty states, not crashes."""
    lab = Lab.init(tmp_path)
    monkeypatch.chdir(tmp_path)
    from skilllab.ui import generate
    out = generate(lab)
    for page in ("index", "skills", "benchmarks", "regressions",
                 "experiments", "insights"):
        text = (out / f"{page}.html").read_text()
        assert "empty" in text or "No " in text or "0" in text, page
    assert 'class="empty"' in (out / "skills.html").read_text()


def test_ui_escapes_untrusted_content(lab):
    """Insight text is HTML-escaped, never injected as markup."""
    (lab.insights_dir / "xss.md").write_text(
        "---\nid: xss\nstatus: candidate\n---\n<script>alert(1)</script>\n")
    from skilllab.ui import generate
    out = generate(lab)
    text = (out / "insights.html").read_text()
    assert "&lt;script&gt;alert" in text
    assert "<script>alert(1)" not in text


def test_diff_runs(lab, capsys):
    run_experiment(lab, "exp-test-trigger", limit=1)
    a = "exp-test-trigger--treatment--write-commit-msg--r0"
    b = "exp-test-trigger--control--write-commit-msg--r0"
    assert main(["diff", a, b]) == 0
    out = capsys.readouterr().out
    assert "read_skill" in out  # treatment reads skill, control doesn't


def test_insight_show_and_conclude(lab, capsys):
    main(["insight", "new", "Wording matters", "--evidence",
          "exp-test-trigger"])
    assert main(["insight", "show", "wording-matters"]) == 0
    assert "wording-matters" in capsys.readouterr().out
    assert main(["experiment", "conclude", "exp-test-trigger",
                 "--conclusion", "specific wording wins",
                 "--insight", "wording-matters"]) == 0
    exp = lab.experiment("exp-test-trigger")
    assert exp.status == "concluded"
    assert exp.insights_generated == ["wording-matters"]


def test_status(lab, capsys):
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "lab:" in out and "skills=" in out


def test_bwrap_sandbox(lab):
    import shutil
    if not shutil.which("bwrap"):
        pytest.skip("bwrap not available")
    lab.cfg["sandbox"] = "bwrap"
    from skilllab.engine import run_in_workspace
    ws = lab.runs_dir / "sws"
    ws.mkdir()
    r = run_in_workspace(lab, ws, "echo hi > out.txt && cat out.txt")
    assert r.returncode == 0 and "hi" in r.stdout
    assert (ws / "out.txt").is_file()      # workspace stays writable
    r2 = run_in_workspace(lab, ws, "echo x > /usr/evil")
    assert r2.returncode != 0              # system is read-only


def test_graduation_report(lab):
    records = run_experiment(lab, "exp-test-trigger", limit=1)
    for rec in records:
        evaluate_run(lab, rec, lab.task(rec.task),
                     lab.runs_dir / rec.run_id)
    from skilllab.graduation import evaluate_skill
    rep = evaluate_skill(lab, "commit-helper")
    assert rep.n_runs == 2  # 1 rollout x 2 tasks, treatment arm only
    assert rep.activation_rate == 1.0
    assert rep.false_activation_rate == 0.0


def test_workspace_path_traversal_blocked(lab):
    from skilllab.engine import _ToolEnv
    ws = lab.runs_dir / "ws"
    ws.mkdir()
    sib = lab.runs_dir / "ws2"          # shares the "ws" name prefix
    sib.mkdir()
    (sib / "secret.txt").write_text("nope")
    env = _ToolEnv(lab, ws, {})
    assert "error" in env.dispatch("read_file",
                                   {"path": "../ws2/secret.txt"})
    assert "error" in env.dispatch("read_file", {"path": "/etc/hostname"})
    assert "error" in env.dispatch("write_file",
                                   {"path": "../ws2/x", "content": "y"})


def test_run_refuses_to_overwrite(lab):
    assert main(["run", "exp-test-trigger", "--limit", "1"]) == 0
    assert main(["run", "exp-test-trigger", "--limit", "1"]) == 1
    assert main(["run", "exp-test-trigger", "--limit", "1",
                 "--force"]) == 0


def test_concluded_experiment_immutable(lab):
    main(["run", "exp-test-trigger", "--limit", "1"])
    main(["experiment", "conclude", "exp-test-trigger",
          "--conclusion", "done"])
    assert main(["run", "exp-test-trigger", "--limit", "1"]) == 1
    assert main(["rerun", "exp-test-trigger", "--limit", "1",
                 "--batch", "b2"]) == 1


def test_run_validates_experiment(lab):
    bad = lab.experiments_dir / "exp-bad-task"
    bad.mkdir()
    (bad / "experiment.yaml").write_text(EXP_YAML.replace(
        "exp-test-trigger", "exp-bad-task").replace(
        "tasks: [write-commit-msg, unrelated-refactor]",
        "tasks: [missing-task]"))
    assert main(["run", "exp-bad-task"]) == 1
    bad2 = lab.experiments_dir / "exp-bad-skill"
    bad2.mkdir()
    (bad2 / "experiment.yaml").write_text(EXP_YAML.replace(
        "exp-test-trigger", "exp-bad-skill").replace(
        "commit-helper@v1", "ghost-skill@v9"))
    assert main(["run", "exp-bad-skill"]) == 1


def test_run_validates_single_variable(lab):
    bad = lab.experiments_dir / "exp-two-vars"
    bad.mkdir()
    (bad / "experiment.yaml").write_text(EXP_YAML.replace(
        "exp-test-trigger", "exp-two-vars").replace(
        "    skill: commit-helper@v1",
        "    skill: commit-helper@v1\n    model: gpt-4o"))
    # treatment differs in skill AND model — two variables at once
    assert main(["run", "exp-two-vars"]) == 1


def test_report_time_to_activation(lab):
    records = run_experiment(lab, "exp-test-trigger", limit=1)
    for rec in records:
        evaluate_run(lab, rec, lab.task(rec.task),
                     lab.runs_dir / rec.run_id)
    text = build_report(lab, lab.experiment("exp-test-trigger"))
    assert "act@turn" in text and "load-cost" in text


def test_cmd_driver_backend(tmp_path):
    import sys
    drv = tmp_path / "drv.py"
    drv.write_text(
        "import sys, json\n"
        "payload = json.loads(sys.stdin.read())\n"
        "assert payload['messages'] and 'tools' in payload\n"
        "print(json.dumps({'content': 'done', 'tool_calls': [],"
        " 'input_tokens': 3, 'output_tokens': 2}))\n")
    from skilllab.llm import LLMClient
    c = LLMClient(f"cmd:{sys.executable} {drv}")
    r = c.complete([{"role": "user", "content": "x"}],
                   [{"type": "function", "function": {"name": "t"}}])
    assert r.content == "done" and r.input_tokens == 3
    import pytest as _pt
    with _pt.raises(RuntimeError):
        LLMClient("cmd:false").complete([{"role": "user", "content": "x"}])


def test_human_eval_scoring(lab, capsys):
    (lab.rubrics_dir / "with-human.yaml").write_text("""\
id: with-human
criteria:
  - id: det
    weight: 0.5
    method: deterministic
    check: OUTPUT.md
  - id: quality
    weight: 0.5
    method: human
    scale: 1-5
""")
    td = lab.tasks_dir / "write-commit-msg" / "task.yaml"
    td.write_text(td.read_text() + "rubric: with-human\n")
    assert main(["run", "exp-test-trigger", "--limit", "1"]) == 0
    rid = "exp-test-trigger--treatment--write-commit-msg--r0"
    assert main(["eval", rid, "--score", "quality=4"]) == 0
    out = capsys.readouterr().out
    assert "rubric_score=0.9" in out
    # scoring a deterministic criterion is rejected
    assert main(["eval", rid, "--score", "det=1"]) == 1


def test_experiment_list_and_compare(lab, capsys):
    assert main(["experiment", "list"]) == 0
    assert "exp-test-trigger" in capsys.readouterr().out
    main(["run", "exp-test-trigger", "--limit", "2"])
    assert main(["compare", "exp-test-trigger"]) == 0
    out = capsys.readouterr().out
    assert "write-commit-msg" in out and "control" in out


def test_insight_refute_and_search(lab, capsys):
    assert main(["insight", "new", "Ghost evidence",
                 "--evidence", "no-such-exp"]) == 1
    assert main(["insight", "new", "Wording wins",
                 "--evidence", "exp-test-trigger"]) == 0
    assert main(["insight", "refute", "wording-wins"]) == 0
    assert main(["insight", "list"]) == 0
    assert "refuted" in capsys.readouterr().out
    assert main(["insight", "list", "--search", "wording"]) == 0
    assert "wording-wins" in capsys.readouterr().out
    assert main(["insight", "list", "--search", "nomatchzz"]) == 0
    assert "wording-wins" not in capsys.readouterr().out


def test_skill_scan(lab, capsys, monkeypatch):
    import skilllab.registry as reg
    ext = lab.root / "ext" / "scan-skill"
    ext.mkdir(parents=True)
    (ext / "SKILL.md").write_text(
        "---\nname: scan-skill\ndescription: Use when scanning for skills "
        "in known locations.\n---\n\nbody\n")
    monkeypatch.setattr(reg, "SCAN_DIRS", [str(lab.root / "ext")])
    assert main(["skill", "scan"]) == 0
    assert "scan-skill" in capsys.readouterr().out
    assert main(["skill", "scan", "--import"]) == 0
    assert (lab.skills_dir / "scan-skill" / "skill.yaml").is_file()


# ------------------------------------------------------- Phase 1 hardening --


def test_command_disabled_without_sandbox(lab):
    """Fail closed: unset sandbox means no shell commands, ever."""
    from skilllab.engine import run_in_workspace, _ToolEnv
    ws = lab.runs_dir / "ws"
    ws.mkdir()
    import pytest as _pt
    with _pt.raises(Exception, match="disabled"):
        run_in_workspace(lab, ws, "echo hi")
    env = _ToolEnv(lab, ws, {})
    assert "disabled" in env.dispatch("run_command",
                                      {"command": "echo hi"})


def test_command_unsafe_opt_in(lab):
    from skilllab.engine import run_in_workspace
    lab.cfg["sandbox"] = "unsafe"
    ws = lab.runs_dir / "ws"
    ws.mkdir()
    r = run_in_workspace(lab, ws, "echo hi")
    assert r.returncode == 0 and "hi" in r.stdout


def test_bwrap_missing_fails_closed(lab, monkeypatch):
    import shutil as sh
    from skilllab.engine import run_in_workspace
    lab.cfg["sandbox"] = "bwrap"
    monkeypatch.setattr(sh, "which", lambda _: None)
    ws = lab.runs_dir / "ws"
    ws.mkdir()
    with pytest.raises(Exception, match="bwrap"):
        run_in_workspace(lab, ws, "echo hi")


def test_command_timeout(lab):
    import subprocess
    from skilllab.engine import run_in_workspace
    lab.cfg["sandbox"] = "unsafe"
    lab.cfg["command_timeout"] = 1
    ws = lab.runs_dir / "ws"
    ws.mkdir()
    with pytest.raises(subprocess.TimeoutExpired):
        run_in_workspace(lab, ws, "sleep 5")


def test_cmd_driver_respects_sandbox(lab, tmp_path):
    """A `cmd:` rollout driver must not bypass the execution policy."""
    import sys
    from skilllab.engine import run_rollout
    drv = tmp_path / "drv.py"
    drv.write_text(
        "import sys, json\njson.loads(sys.stdin.read())\n"
        "print(json.dumps({'content': 'done', 'tool_calls': []}))\n")
    exp = lab.experiment("exp-test-trigger")
    exp.fixed.model = f"cmd:{sys.executable} {drv}"
    arm = exp.arms[0]
    # sandbox unset -> driver call fails closed, run records the error
    rec = run_rollout(lab, exp, arm, "write-commit-msg", 0)
    assert rec.status == "error" and "disabled" in (rec.error or "")
    # explicit unsafe opt-in -> driver executes
    lab.cfg["sandbox"] = "unsafe"
    rec2 = run_rollout(lab, exp, arm, "write-commit-msg", 1)
    assert rec2.status == "ok" and rec2.final_message == "done"


def test_engine_append_only_and_archive(lab):
    """Direct engine calls: existing run dirs are never silently replaced —
    an explicit overwrite archives the old run instead of deleting it."""
    from skilllab.engine import run_rollout
    exp = lab.experiment("exp-test-trigger")
    rec = run_rollout(lab, exp, exp.arms[0], "write-commit-msg", 0)
    run_dir = lab.runs_dir / rec.run_id
    marker = run_dir / "workspace" / "MARKER.txt"
    marker.write_text("original")
    with pytest.raises(Exception, match="append-only"):
        run_rollout(lab, exp, exp.arms[0], "write-commit-msg", 0)
    assert marker.is_file()  # untouched
    run_rollout(lab, exp, exp.arms[0], "write-commit-msg", 0, overwrite=True)
    assert not marker.exists()  # replaced in place...
    archived = list((lab.archive_dir / rec.run_id).glob("*/workspace/MARKER.txt"))
    assert archived and archived[0].read_text() == "original"


def test_deterministic_check_types(lab):
    from skilllab.engine import run_rollout
    lab.cfg["sandbox"] = "unsafe"
    td = lab.tasks_dir / "checks-task"
    td.mkdir()
    (td / "task.yaml").write_text("""\
id: checks-task
kind: performance
prompt: do it
deterministic_checks:
  - type: file-content
    path: OUTPUT.md
    contains: "commit"
  - type: json
    path: out.json
    keys: [status]
    field: status.code
    value: "0"
  - type: command
    command: "test -f OUTPUT.md"
""")
    exp = lab.experiment("exp-test-trigger")
    rec = run_rollout(lab, exp, exp.arms[0], "checks-task", 0)
    ws = lab.runs_dir / rec.run_id / "workspace"
    (ws / "OUTPUT.md").write_text("a commit message")
    (ws / "out.json").write_text('{"status": {"code": 0}}')
    ev = evaluate_run(lab, rec, lab.task("checks-task"),
                      lab.runs_dir / rec.run_id)
    assert ev.status == "passed"
    (ws / "out.json").write_text('{"status": {"code": 1}}')
    ev = evaluate_run(lab, rec, lab.task("checks-task"),
                      lab.runs_dir / rec.run_id)
    assert ev.status == "failed"


def test_check_path_traversal_is_error(lab):
    """A check path escaping the workspace is an eval error, not a pass."""
    from skilllab.engine import run_rollout
    td = lab.tasks_dir / "evil-task"
    td.mkdir()
    (td / "task.yaml").write_text("""\
id: evil-task
kind: performance
prompt: do it
deterministic_checks:
  - type: file-exists
    path: ../runs/evil-task/../../lab.yaml
""")
    exp = lab.experiment("exp-test-trigger")
    rec = run_rollout(lab, exp, exp.arms[0], "evil-task", 0)
    ev = evaluate_run(lab, rec, lab.task("evil-task"),
                      lab.runs_dir / rec.run_id)
    assert ev.status == "error"
    assert "escapes" in ev.checks[0].detail


def test_judge_error_and_malformed_output(lab):
    """Judge outages and garbage replies -> error status, never a pass."""
    lab.cfg["sandbox"] = "unsafe"
    (lab.rubrics_dir / "judge-rubric.yaml").write_text("""\
id: judge-rubric
criteria:
  - id: quality
    weight: 1
    method: llm-judge
    scale: 1-5
    judge_prompt: is it good?
""")
    td = lab.tasks_dir / "write-commit-msg" / "task.yaml"
    td.write_text(td.read_text() + "rubric: judge-rubric\n")
    exp = lab.experiment("exp-test-trigger")
    from skilllab.engine import run_rollout
    rec = run_rollout(lab, exp, exp.arms[0], "write-commit-msg", 0)
    # judge crashes -> error
    lab.cfg["judge_model"] = "cmd:false"
    ev = evaluate_run(lab, rec, lab.task("write-commit-msg"),
                      lab.runs_dir / rec.run_id)
    assert ev.status == "error" and ev.checks[0].status == "error"
    # judge replies valid JSON but no SCORE line -> error
    lab.cfg["judge_model"] = "cmd:echo '{\"content\": \"no score here\"}'"
    ev = evaluate_run(lab, rec, lab.task("write-commit-msg"),
                      lab.runs_dir / rec.run_id)
    assert ev.status == "error" and "SCORE" in ev.checks[0].detail
    # judge works -> passed, provenance recorded
    lab.cfg["judge_model"] = \
        "cmd:echo '{\"content\": \"verdict ok SCORE: 5\"}'"
    ev = evaluate_run(lab, rec, lab.task("write-commit-msg"),
                      lab.runs_dir / rec.run_id)
    assert ev.status == "passed"
    assert ev.checks[0].judge_model and ev.checks[0].score == 1.0
    assert ev.evaluated_at


def test_human_eval_pending_then_scored(lab):
    (lab.rubrics_dir / "with-human.yaml").write_text("""\
id: with-human
criteria:
  - id: det
    weight: 0.5
    method: deterministic
    check: OUTPUT.md
  - id: quality
    weight: 0.5
    method: human
    scale: 1-5
""")
    td = lab.tasks_dir / "write-commit-msg" / "task.yaml"
    td.write_text(td.read_text() + "rubric: with-human\n")
    from skilllab.engine import run_rollout
    exp = lab.experiment("exp-test-trigger")
    rec = run_rollout(lab, exp, exp.arms[0], "write-commit-msg", 0)
    run_dir = lab.runs_dir / rec.run_id
    ev = evaluate_run(lab, rec, lab.task("write-commit-msg"), run_dir)
    # pending human criterion -> eval is pending, NOT passed
    assert ev.status == "pending" and not ev.success
    assert main(["eval", rec.run_id, "--score", "quality=4",
                 "--comment", "quality=looks fine"]) == 0
    from skilllab.models import EvalResult, load_yaml
    ev = EvalResult(**load_yaml(run_dir / "eval.yaml"))
    assert ev.status == "passed"
    q = [c for c in ev.checks if c.id == "quality"][0]
    assert "looks fine" in q.detail


def test_report_distinguishes_incomplete_evals(lab):
    (lab.rubrics_dir / "with-human.yaml").write_text("""\
id: with-human
criteria:
  - id: det
    weight: 0.5
    method: deterministic
    check: OUTPUT.md
  - id: quality
    weight: 0.5
    method: human
    scale: 1-5
""")
    td = lab.tasks_dir / "write-commit-msg" / "task.yaml"
    td.write_text(td.read_text() + "rubric: with-human\n")
    records = run_experiment(lab, "exp-test-trigger", limit=1)
    for rec in records:
        evaluate_run(lab, rec, lab.task(rec.task),
                     lab.runs_dir / rec.run_id)
    text = build_report(lab, lab.experiment("exp-test-trigger"))
    assert "incomplete" in text
    assert "eval=pending" in text


def test_experiment_validate_command(lab, capsys):
    assert main(["experiment", "validate", "exp-test-trigger"]) == 0
    assert "is valid" in capsys.readouterr().out
    bad = lab.experiments_dir / "exp-bad"
    bad.mkdir()
    (bad / "experiment.yaml").write_text(EXP_YAML.replace(
        "exp-test-trigger", "exp bad").replace(
        "tasks: [write-commit-msg, unrelated-refactor]",
        "tasks: [write-commit-msg, write-commit-msg]"))
    assert main(["experiment", "validate", "exp-bad"]) == 1
    err = capsys.readouterr().err
    assert "duplicate" in err and "invalid experiment id" in err
    # invalid experiment must never start a rollout
    assert main(["run", "exp-bad"]) == 1
    assert not [d for d in lab.runs_dir.iterdir()
                if (d / "run.yaml").exists()]


def test_validate_rubric_and_fixture_refs(lab):
    bad = lab.experiments_dir / "exp-bad-rubric"
    bad.mkdir()
    td = lab.tasks_dir / "write-commit-msg" / "task.yaml"
    orig = td.read_text()
    td.write_text(orig + "rubric: no-such-rubric\n")
    (bad / "experiment.yaml").write_text(EXP_YAML.replace(
        "exp-test-trigger", "exp-bad-rubric"))
    assert main(["experiment", "validate", "exp-bad-rubric"]) == 1
    td.write_text(orig)


def test_import_pack_hardening(lab, tmp_path):
    """Manifest entries, symlinks, traversal and bad schemas are rejected."""
    import os
    from skilllab.models import dump_yaml, load_yaml
    from skilllab.share import import_pack
    pack = tmp_path / "evil-pack"
    (pack / "tasks" / "t1").mkdir(parents=True)
    (pack / "insights").mkdir(parents=True)
    (pack / "tasks" / "t1" / "task.yaml").write_text("id: t1\nkind: bogus\n")
    (pack / "insights" / "ok.md").write_text("hi")
    # symlink escape attempt
    os.symlink("/etc/hostname", pack / "insights" / "link.md")
    dump_yaml({"kind": "skilllab-pack", "version": 1,
               "contents": ["tasks", "insights"]}, pack / "pack.yaml")
    res = import_pack(lab, pack)
    assert res["rejected"]  # bad task.yaml + symlink
    assert not (lab.insights_dir / "link.md").exists()
    # unsupported manifest entry -> whole pack refused
    dump_yaml({"kind": "skilllab-pack", "version": 1,
               "contents": ["../../etc"]}, pack / "pack.yaml")
    with pytest.raises(Exception, match="unsupported"):
        import_pack(lab, pack)
    # newer pack version -> refused
    dump_yaml({"kind": "skilllab-pack", "version": 99, "contents": []},
              pack / "pack.yaml")
    with pytest.raises(Exception, match="newer"):
        import_pack(lab, pack)


def test_insight_promotion_gating(lab, tmp_path):
    from skilllab.insights import promote
    # no evidence -> rejected
    (lab.insights_dir / "i1.md").write_text("""\
---
id: i1
scope: trigger wording
---
Statement. Conditions. Evidence section complete, no placeholders.
""")
    with pytest.raises(Exception, match="2 independent"):
        promote(lab, "i1")
    # two runs from the SAME experiment are not independent evidence
    recs = run_experiment(lab, "exp-test-trigger", limit=2)
    (lab.insights_dir / "i2.md").write_text(f"""\
---
id: i2
evidence: [{recs[0].run_id}, {recs[1].run_id}]
scope: trigger wording
---
Statement. Conditions. Complete.
""")
    with pytest.raises(Exception, match="2 independent"):
        promote(lab, "i2")
    # second experiment dir -> now promotes
    (lab.experiments_dir / "exp-two").mkdir()
    (lab.experiments_dir / "exp-two" / "experiment.yaml").write_text(
        EXP_YAML.replace("exp-test-trigger", "exp-two"))
    (lab.insights_dir / "i3.md").write_text(f"""\
---
id: i3
evidence: [exp-test-trigger, exp-two]
scope: trigger wording
---
Statement. Conditions. Complete.
""")
    dest = promote(lab, "i3")
    assert dest.parent == lab.principles_dir
    assert "promoted_at" in dest.read_text()
    # existing principle is never overwritten
    (lab.insights_dir / "i3.md").write_text(dest.read_text().replace(
        "id: i3", "id: i3"))
    with pytest.raises(Exception, match="already exists"):
        promote(lab, "i3")
    # TODO placeholders block promotion
    (lab.insights_dir / "i4.md").write_text("""\
---
id: i4
evidence: [exp-test-trigger, exp-two]
scope: x
---
TODO: write the actual statement
""")
    with pytest.raises(Exception, match="TODO"):
        promote(lab, "i4")


def test_insight_confirm_requires_evidence(lab):
    from skilllab.insights import confirm
    (lab.insights_dir / "c1.md").write_text("---\nid: c1\n---\nbody\n")
    with pytest.raises(Exception, match="no valid"):
        confirm(lab, "c1")
    (lab.insights_dir / "c1.md").write_text(
        "---\nid: c1\nevidence: [exp-test-trigger]\n---\nbody\n")
    p = confirm(lab, "c1")
    assert "confirmed" in p.read_text()


def test_legacy_eval_yaml_status_sync():
    """Old eval.yaml (passed/success only) still maps onto the lifecycle."""
    from skilllab.models import CheckResult, EvalResult
    c = CheckResult(id="x", method="deterministic", passed=True)
    assert c.status == "passed" and c.passed is True
    c = CheckResult(id="x", method="deterministic", passed=None)
    assert c.status == "pending" and c.passed is None
    ev = EvalResult(checks=[], rubric_score=0.9, success=True)
    assert ev.status == "passed"  # legacy success is trusted
    ev = EvalResult(checks=[], success=False)
    assert ev.status == "error"   # no checks and no success -> error
    ev = EvalResult(checks=[CheckResult(id="x", method="deterministic",
                                        passed=True)],
                    success=True)
    assert ev.status == "passed"


# -------------------------------------------------------- regression tests --

VAGUE_SKILL_MD = """\
---
name: commit-helper
description: Helps with stuff and things, quite generic.
---

# Commit Helper v2

Vague body.
"""


def _add_variant_v2(lab):
    sd = lab.skills_dir / "commit-helper" / "variants" / "v2"
    sd.mkdir(parents=True)
    (sd / "SKILL.md").write_text(VAGUE_SKILL_MD)
    meta = (lab.skills_dir / "commit-helper" / "skill.yaml").read_text()
    (lab.skills_dir / "commit-helper" / "skill.yaml").write_text(
        meta + "  - id: v2\n    path: variants/v2\n")


def test_regression_run_detects_activation_regression(lab, capsys):
    """v2 has a vague description -> mock never activates it -> the
    regression report must flag an activation regression vs v1."""
    _add_variant_v2(lab)
    assert main(["regression", "run", "commit-helper",
                 "--baseline", "v1", "--candidate", "v2",
                 "--tasks", "default", "--rollouts", "3"]) == 0
    reg_dir = lab.d("regressions") / "reg-commit-helper-v1-v2-01"
    assert (reg_dir / "regression.yaml").is_file()
    assert (reg_dir / "report.yaml").is_file()
    report = (reg_dir / "report.md").read_text()
    assert "REGRESSED" in report
    assert "activation" in report
    assert "simulated" in report  # mock warning present
    assert "reg-commit-helper-v1-v2-01--baseline--write-commit-msg--r0" \
        in report  # transcript links / run ids
    from skilllab.models import load_yaml
    res = load_yaml(reg_dir / "report.yaml")
    assert res["verdict"] == "regressed"
    assert res["counts"]["activation"] == 1
    pos = [t for t in res["tasks"] if t["task"] == "write-commit-msg"][0]
    assert pos["baseline"]["activated"] == 1.0
    assert pos["candidate"]["activated"] == 0.0


def test_regression_list_and_report_commands(lab, capsys):
    _add_variant_v2(lab)
    main(["regression", "run", "commit-helper", "--baseline", "v1",
          "--candidate", "v2", "--rollouts", "1"])
    assert main(["regression", "list"]) == 0
    out = capsys.readouterr().out
    assert "reg-commit-helper-v1-v2-01" in out and "regressed" in out
    assert main(["regression", "report",
                 "reg-commit-helper-v1-v2-01"]) == 0
    assert "Regression report: `commit-helper` `v1` → `v2`" in \
        capsys.readouterr().out


def test_regression_rerun_preserves_history(lab):
    """A second regression of the same pair gets a new id — baseline run
    data is never overwritten."""
    _add_variant_v2(lab)
    r1 = main(["regression", "run", "commit-helper", "--baseline", "v1",
               "--candidate", "v2", "--rollouts", "1"])
    r2 = main(["regression", "run", "commit-helper", "--baseline", "v1",
               "--candidate", "v2", "--rollouts", "1"])
    assert r1 == r2 == 0
    ids = {d.name for d in lab.d("regressions").iterdir()}
    assert "reg-commit-helper-v1-v2-01" in ids
    assert "reg-commit-helper-v1-v2-02" in ids
    rid1 = "reg-commit-helper-v1-v2-01--baseline--write-commit-msg--r0"
    rid2 = "reg-commit-helper-v1-v2-02--baseline--write-commit-msg--r0"
    assert (lab.runs_dir / rid1 / "run.yaml").is_file()
    assert (lab.runs_dir / rid2 / "run.yaml").is_file()


def test_regression_validates_inputs(lab):
    _add_variant_v2(lab)
    # same variant twice -> pointless, rejected
    assert main(["regression", "run", "commit-helper", "--baseline", "v1",
                 "--candidate", "v1"]) == 1
    # unknown variant -> rejected before any run dir is created
    assert main(["regression", "run", "commit-helper", "--baseline", "v1",
                 "--candidate", "v9"]) == 1
    # unknown skill
    assert main(["regression", "run", "ghost", "--baseline", "v1",
                 "--candidate", "v2"]) == 1
    # unknown task in the suite
    assert main(["regression", "run", "commit-helper", "--baseline", "v1",
                 "--candidate", "v2", "--tasks", "nope-task"]) == 1
    assert not [d for d in lab.runs_dir.iterdir()
                if (d / "run.yaml").exists()]


def test_regression_suite_file(lab):
    _add_variant_v2(lab)
    (lab.suites_dir / "pos-only.yaml").write_text(
        "tasks: [write-commit-msg]\n")
    assert main(["regression", "run", "commit-helper", "--baseline", "v1",
                 "--candidate", "v2", "--tasks", "pos-only",
                 "--rollouts", "1"]) == 0
    from skilllab.models import load_yaml
    meta = load_yaml(lab.d("regressions")
                     / "reg-commit-helper-v1-v2-01" / "regression.yaml")
    assert meta["tasks"] == ["write-commit-msg"]


def test_regression_classify_categories(lab):
    """Unit-test the category rules directly (no runs needed)."""
    from skilllab.regression import Thresholds, _classify
    thr = Thresholds(min_runs=1)

    def m(**kw):
        base = dict(n_runs=3, errors=0, error_rate=0.0, n_final=3,
                    incomplete=0, success=1.0, score=0.9, activated=1.0,
                    tokens=100.0, latency=2.0, turns=3.0, variance=0.05)
        base.update(kw)
        return base

    task_pos = lab.task("write-commit-msg")
    task_neg = lab.task("unrelated-refactor")
    task_perf = lab.task("unrelated-refactor")
    task_perf = task_perf.model_copy(update={"kind": "performance"})

    cats, imps, notes = _classify(task_pos, m(), m(success=0.0, score=0.0),
                                  thr, "available")
    assert "critical" in cats and "quality" in cats
    cats, _, _ = _classify(task_pos, m(), m(activated=0.0), thr, "available")
    assert "activation" in cats
    cats, _, _ = _classify(task_neg, m(activated=0.0), m(activated=1.0),
                           thr, "available")
    assert "false-activation" in cats
    cats, imps, notes = _classify(task_perf, m(), m(tokens=150.0),
                                  thr, "available")
    assert "efficiency" in cats and any("token" in n for n in notes)
    cats, _, _ = _classify(task_perf, m(), m(variance=0.4), thr,
                           "available")
    assert "stability" in cats
    # insufficient data -> notes, still no crash
    _, _, notes = _classify(task_perf, m(n_runs=1), m(n_runs=1),
                            Thresholds(min_runs=3), "available")
    assert any("insufficient" in n for n in notes)
    # injected mode -> activation checks skipped entirely
    cats, _, _ = _classify(task_pos, m(), m(activated=0.0), thr, "injected")
    assert "activation" not in cats
    # missing finals -> inconclusive note, no outcome verdicts
    _, _, notes = _classify(task_perf, m(n_final=0), m(n_final=0), thr,
                            "available")
    assert any("no final evaluations" in n for n in notes)


def test_regression_handles_missing_evals(lab):
    """Runs with no eval.yaml are reported as data gaps, not failures."""
    _add_variant_v2(lab)
    main(["regression", "run", "commit-helper", "--baseline", "v1",
          "--candidate", "v2", "--rollouts", "1"])
    # delete one eval -> report must show incomplete, not crash
    rid = "reg-commit-helper-v1-v2-01--candidate--write-commit-msg--r0"
    (lab.runs_dir / rid / "eval.yaml").unlink()
    assert main(["regression", "report",
                 "reg-commit-helper-v1-v2-01"]) == 0
    from skilllab.regression import analyze
    res = analyze(lab, "reg-commit-helper-v1-v2-01")
    task = [t for t in res["tasks"] if t["task"] == "write-commit-msg"][0]
    assert task["candidate"]["incomplete"] >= 1


# ------------------------------------------------------------- research --


def test_research_project_lifecycle(lab, capsys):
    assert main(["project", "new", "cap-research",
                 "--title", "Capability research",
                 "--objective", "Study activation"]) == 0
    assert (lab.research_dir / "cap-research" / "project.yaml").is_file()
    assert (lab.research_dir / "cap-research" / "charter.md").is_file()
    assert main(["project", "list"]) == 0
    assert main(["project", "status", "cap-research",
                 "researching"]) == 0
    from skilllab.research import get_project
    assert get_project(lab, "cap-research").status == "researching"
    assert main(["project", "archive", "cap-research"]) == 0
    assert get_project(lab, "cap-research").status == "archived"
    # invalid status rejected by argparse
    with pytest.raises(SystemExit):
        main(["project", "status", "cap-research", "bogus"])
    capsys.readouterr()


def test_research_entities_and_links(lab):
    main(["project", "new", "p1"])
    assert main(["question", "add", "p1", "Does X help?"]) == 0
    assert main(["source", "add", "p1", "--type", "url",
                 "--title", "Doc", "--url", "https://example.com"]) == 0
    assert main(["note", "add", "p1", "first log"]) == 0
    assert main(["decision", "add", "p1",
                 "--decision", "Use variant A"]) == 0
    # finding needs a real question + source ref
    assert main(["finding", "add", "p1", "--statement", "X helps",
                 "--question", "q01", "--source", "s01"]) == 0
    # link question to the real experiment in this lab
    assert main(["question", "link", "p1", "q01",
                 "--experiment", "exp-test-trigger"]) == 0
    # bogus refs are refused
    assert main(["finding", "add", "p1", "--statement", "bad ref",
                 "--source", "s99"]) == 1
    assert main(["question", "link", "p1", "q01",
                 "--experiment", "exp-nope"]) == 1
    assert main(["project", "show", "p1"]) == 0


def test_finding_supported_requires_evidence(lab):
    main(["project", "new", "p1"])
    main(["finding", "add", "p1", "--statement", "unsupported claim"])
    # no sources/evidence -> cannot be supported
    assert main(["finding", "status", "p1", "f01", "supported"]) == 1
    # unverified kind can never be supported, even with a source
    main(["source", "add", "p1", "--type", "other", "--title", "x"])
    main(["finding", "add", "p1", "--statement", "unverified claim",
          "--kind", "unverified", "--source", "s01"])
    assert main(["finding", "status", "p1", "f02", "supported"]) == 1
    # observation + real experiment evidence -> ok
    main(["finding", "add", "p1", "--statement", "backed",
          "--kind", "observation",
          "--evidence", "exp-test-trigger"])
    assert main(["finding", "status", "p1", "f03", "supported"]) == 0


def test_project_delete_protection(lab):
    main(["project", "new", "p1"])
    main(["question", "add", "p1", "q?"])
    # holds data -> delete refused even with --confirm
    assert main(["project", "delete", "p1", "--confirm"]) == 1
    # empty draft + --confirm -> deleted
    main(["project", "new", "p2"])
    assert main(["project", "delete", "p2", "--confirm"]) == 0
    assert not (lab.research_dir / "p2").exists()


def test_research_pages_in_ui(lab, capsys):
    main(["project", "new", "p1", "--title", "Research"])
    main(["question", "add", "p1", "Q?"])
    main(["finding", "add", "p1", "--statement", "F"])
    main(["ui"])
    assert (lab.d("ui") / "research.html").is_file()
    assert (lab.d("ui") / "project-p1.html").is_file()
    html = (lab.d("ui") / "project-p1.html").read_text()
    assert "Research questions" in html and "Findings" in html
    assert "Research" in (lab.d("ui") / "index.html").read_text()
    capsys.readouterr()


# ------------------------------------------------------------ blueprint --


def _fill_required(lab, pid, bid):
    from skilllab import blueprint as bp
    for k in ("name", "description", "problem_statement",
              "target_capability", "output_contract"):
        bp.set_field(lab, pid, bid, k, "x" * 50 if k == "description" else "x")
    for k in ("in_scope_tasks", "trigger_conditions",
              "execution_workflow", "evaluation_criteria"):
        bp.set_field(lab, pid, bid, k, ["a"])


def test_blueprint_lifecycle_and_gate(lab):
    main(["project", "new", "p1"])
    assert main(["blueprint", "new", "p1", "bp1"]) == 0
    from skilllab import blueprint as bp
    # empty blueprint cannot reach gated statuses
    assert main(["blueprint", "status", "p1", "bp1",
                 "ready_for_generation"]) == 1
    issues = bp.validate(lab, "p1", "bp1")
    assert sum(1 for i in issues if i["severity"] == "error") == 9
    _fill_required(lab, "p1", "bp1")
    # warnings don't block; errors do
    assert bp.validate(lab, "p1", "bp1") == [] or all(
        i["severity"] != "error" for i in bp.validate(lab, "p1", "bp1"))
    assert main(["blueprint", "status", "p1", "bp1",
                 "ready_for_generation"]) == 0
    assert bp.get_blueprint(lab, "p1", "bp1").status == \
        "ready_for_generation"


def test_blueprint_contradiction_and_warn(lab):
    main(["project", "new", "p1"])
    main(["blueprint", "new", "p1", "bp1"])
    from skilllab import blueprint as bp
    bp.set_field(lab, "p1", "bp1", "in_scope_tasks", ["t1"])
    bp.set_field(lab, "p1", "bp1", "out_of_scope_tasks", ["t1"])
    issues = bp.validate(lab, "p1", "bp1")
    assert any(i["check"] == "contradiction" and i["severity"] == "error"
               for i in issues)


def test_blueprint_revisions_and_diff(lab):
    main(["project", "new", "p1"])
    main(["blueprint", "new", "p1", "bp1"])
    from skilllab import blueprint as bp
    assert bp.get_blueprint(lab, "p1", "bp1").rev == 1
    bp.set_field(lab, "p1", "bp1", "name", "first")
    bp.set_field(lab, "p1", "bp1", "name", "second")
    b = bp.get_blueprint(lab, "p1", "bp1")
    assert b.rev == 3
    revs = bp.revisions(lab, "p1", "bp1")
    assert [r.rev for r in revs] == [1, 2, 3]
    assert revs[0].fields.get("name") in (None, "")
    diffs = bp.diff_revisions(lab, "p1", "bp1", 1)
    assert any(d["field"] == "name" and d["to"] == "second"
               for d in diffs)
    assert main(["blueprint", "diff", "p1", "bp1", "1"]) == 0


def test_blueprint_from_question_and_links(lab):
    main(["project", "new", "p1"])
    main(["question", "add", "p1", "Does X work?",
          "--hypothesis", "X halves tokens"])
    main(["finding", "add", "p1", "--statement", "F",
          "--evidence", "exp-test-trigger"])
    main(["blueprint", "new", "p1", "bp1"])
    assert main(["blueprint", "from-question", "p1", "bp1", "q01"]) == 0
    from skilllab import blueprint as bp
    b = bp.get_blueprint(lab, "p1", "bp1")
    assert "X halves tokens" in b.fields["research_motivation"]
    assert b.fields["problem_statement"] == "Does X work?"
    assert main(["blueprint", "link", "p1", "bp1",
                 "--finding", "f01"]) == 0
    # bogus refs refused
    assert main(["blueprint", "from-question", "p1", "bp1", "q99"]) == 1
    assert main(["blueprint", "link", "p1", "bp1",
                 "--finding", "f99"]) == 1


def test_blueprint_page_in_ui(lab, capsys):
    main(["project", "new", "p1"])
    main(["blueprint", "new", "p1", "bp1"])
    main(["ui"])
    page = lab.d("ui") / "blueprint-p1-bp1.html"
    assert page.is_file()
    html = page.read_text()
    assert "output_contract" in html and "Validation" in html
    capsys.readouterr()


# ---------------------------------------------------------------- studio --


def test_blueprint_generate_skill(lab):
    main(["project", "new", "p1"])
    main(["blueprint", "new", "p1", "bp1"])
    from skilllab import blueprint as bp
    _fill_required(lab, "p1", "bp1")
    # unvalidated blueprint refused? no — but errors block: fill ok now
    assert main(["blueprint", "generate", "p1", "bp1",
                 "--skill", "new-skill", "--variant", "v1"]) == 0
    md = lab.skills_dir / "new-skill" / "variants" / "v1" / "SKILL.md"
    assert md.is_file()
    text = md.read_text()
    assert "name:" in text and "blueprint bp1" in text
    meta = lab.skill("new-skill")
    assert meta.variants[0].note.startswith("blueprint p1/bp1")
    b = bp.get_blueprint(lab, "p1", "bp1")
    assert b.status == "generated"
    assert b.generated_variants == ["new-skill@v1"]
    # second generate on same variant refused without --force
    assert main(["blueprint", "generate", "p1", "bp1",
                 "--skill", "new-skill", "--variant", "v1"]) == 1
    # --force archives the old variant
    assert main(["blueprint", "generate", "p1", "bp1",
                 "--skill", "new-skill", "--variant", "v1",
                 "--force"]) == 0
    assert list((lab.archive_dir / "skills" / "new-skill").iterdir())


def test_generate_blocks_on_invalid_blueprint(lab):
    main(["project", "new", "p1"])
    main(["blueprint", "new", "p1", "bp1"])
    # missing required fields -> generate refuses
    assert main(["blueprint", "generate", "p1", "bp1",
                 "--skill", "s", "--variant", "v"]) == 1
    assert not (lab.skills_dir / "s").exists()


# --------------------------------------------------------------- failure --


def _mkrun(lab, rid, task="write-commit-msg", arm="a", status="ok",
           activated=True, mode="available", tokens=100):
    from skilllab.models import dump_yaml
    d = lab.runs_dir / rid
    d.mkdir(parents=True, exist_ok=True)
    events = [{"t": 1, "event": "offered", "skill": "commit-helper"}]
    if activated:
        events.append({"t": 2, "event": "activated",
                       "skill": "commit-helper"})
    dump_yaml({"run_id": rid, "experiment": "exp-test-trigger",
               "arm": arm, "task": task, "injection_mode": mode,
               "skill_ref": "commit-helper@v1", "status": status,
               "skill_events": events,
               "usage": {"input_tokens": tokens, "output_tokens": 10,
                         "turns": 3}}, d / "run.yaml")
    return d


def test_failure_incorrect_activation(lab):
    from skilllab import failure
    _mkrun(lab, "r-neg", task="unrelated-refactor", activated=True)
    rep = failure.analyze_run(lab, "r-neg")
    assert rep["verdict"] == "failed"
    assert rep["first_failure"]["category"] == "incorrect-activation"
    _mkrun(lab, "r-pos", task="write-commit-msg", activated=False)
    rep = failure.analyze_run(lab, "r-pos")
    assert rep["first_failure"]["category"] == "incorrect-activation"


def test_failure_eval_check_categories(lab):
    from skilllab import failure
    from skilllab.models import dump_yaml
    d = _mkrun(lab, "r-fmt")
    dump_yaml({"checks": [{"id": "output-format", "method": "deterministic",
                           "status": "failed",
                           "detail": "missing key"}],
               "status": "failed", "success": False}, d / "eval.yaml")
    rep = failure.analyze_run(lab, "r-fmt")
    assert any(c["category"] == "output-format-violation"
               for c in rep["causes"])
    d2 = _mkrun(lab, "r-judge")
    dump_yaml({"checks": [{"id": "quality", "method": "llm-judge",
                           "status": "failed", "detail": "vague"}],
               "status": "failed", "success": False}, d2 / "eval.yaml")
    rep2 = failure.analyze_run(lab, "r-judge")
    assert any(c["category"] == "ambiguous-instructions"
               for c in rep2["causes"])


def test_failure_infra_vs_task_failure(lab):
    from skilllab import failure
    from skilllab.models import dump_yaml
    _mkrun(lab, "r-err", status="error")
    rep = failure.analyze_run(lab, "r-err")
    assert rep["first_failure"]["category"] == "infrastructure"
    assert rep["verdict"] == "inconclusive"
    # missing eval on an ok run = data gap, not a task failure
    _mkrun(lab, "r-noeval", activated=False)
    rep = failure.analyze_run(lab, "r-noeval")
    # not-activated on a positive task IS a task failure, plus the
    # missing-eval note must not mask it
    assert rep["first_failure"]["category"] == "incorrect-activation"
    assert rep["verdict"] == "failed"
    # a clean passing run reports clean
    d = _mkrun(lab, "r-ok")
    dump_yaml({"checks": [{"id": "x", "method": "deterministic",
                           "status": "passed"}],
               "status": "passed", "success": True}, d / "eval.yaml")
    rep = failure.analyze_run(lab, "r-ok")
    assert rep["verdict"] == "warning" or rep["verdict"] == "clean"


def test_failure_excessive_tokens(lab):
    from skilllab import failure
    for i in range(3):
        _mkrun(lab, f"r-sib{i}", tokens=100)
    _mkrun(lab, "r-fat", tokens=400)
    rep = failure.analyze_run(lab, "r-fat")
    assert any(c["category"] == "excessive-tokens"
               for c in rep["causes"])


def test_failure_report_and_proposals(lab):
    from skilllab import failure
    _mkrun(lab, "r-f", task="write-commit-msg", activated=False)
    rep = failure.analyze_run(lab, "r-f")
    props = failure.proposals(rep)
    assert props and props[0]["change"] and props[0]["evidence"]
    p = failure.write_report(lab, rep)
    assert p.is_file()
    assert main(["failure", "list"]) == 0
    assert main(["failure", "show", "r-f"]) == 0
    # missing report -> error
    assert main(["failure", "show", "r-nope"]) == 1


# ------------------------------------------------------------ release ----


def test_release_gate_and_trace(lab):
    from skilllab import release
    from skilllab.models import load_yaml
    main(["project", "new", "p1"])
    main(["blueprint", "new", "p1", "bp1"])
    _fill_required(lab, "p1", "bp1")
    main(["blueprint", "generate", "p1", "bp1",
          "--skill", "rel-skill", "--variant", "v1"])
    # release blocked: no evaluated runs yet, empty changelog
    assert main(["release", "new", "rel-skill", "1.0.0",
                 "--variant", "v1"]) == 0
    assert main(["release", "status", "rel-skill", "1.0.0",
                 "released"]) == 1
    # add an evaluated run for this variant
    from skilllab.models import dump_yaml
    d = _mkrun(lab, "r-rel")
    ry = load_yaml(d / "run.yaml"); ry["skill_ref"] = "rel-skill@v1"
    dump_yaml(ry, d / "run.yaml")
    dump_yaml({"checks": [{"id": "x", "method": "deterministic",
                           "status": "passed"}],
               "status": "passed", "success": True}, d / "eval.yaml")
    # still blocked: empty changelog
    assert main(["release", "status", "rel-skill", "1.0.0",
                 "released"]) == 1
    rp = lab.d("releases") / "rel-skill" / "1.0.0.yaml"
    r = load_yaml(rp); r["changelog"] = "first release"
    dump_yaml(r, rp)
    assert main(["release", "check", "rel-skill", "1.0.0"]) == 0
    assert main(["release", "status", "rel-skill", "1.0.0",
                 "released"]) == 0
    assert release.list_releases(lab)[0].released_at
    # trace: generated variant walks back to blueprint+project
    t = release.trace(lab, "rel-skill@v1")
    assert t["blueprint"]["id"] == "bp1" and t["blueprint"]["rev"] >= 1
    assert t["runs"] == ["r-rel"]


# ----------------------------------------------------------- architect ---


def test_ai_proposal_approval_flow(lab):
    # craft a variant with a dead link + missing trigger
    d = lab.skills_dir / "commit-helper" / "variants" / "v1"
    md = d / "SKILL.md"
    md.write_text(md.read_text() + "\nSee `MISSING.md`.\n"
                  .replace("description:", "description:"))
    from skilllab import architect
    props = architect.suggest(lab, "commit-helper@v1")
    assert any("MISSING.md" in p.finding for p in props)
    p = [p for p in props if "MISSING.md" in p.finding][0]
    assert p.status == "pending" and p.diff_preview
    # cannot apply before approval
    assert main(["ai", "apply", p.id]) == 1
    main(["ai", "approve", p.id])
    before = md.read_text()
    assert main(["ai", "apply", p.id]) == 0
    assert "`MISSING.md`" not in md.read_text()
    prop, _ = architect.get(lab, p.id)
    assert prop.status == "applied" and prop.original_content == before


def test_ai_no_actionable_no_proposal(lab):
    from skilllab import architect
    props = architect.suggest(lab, "commit-helper@v1")
    # v1 is clean -> nothing proposed (or only already-applied states)
    assert all(p.finding for p in props)



# ---------- phase 3b: studio tools ----------

def test_preview_tokens_sections(lab):
    from skilllab.studio import preview
    info = preview(lab, "commit-helper@v1")
    assert info["entry"] == "SKILL.md"
    assert info["tokens"] > 0
    assert info["fm"]["name"] == "commit-helper"
    assert info["sections"]
    assert "resources/style.md" in info["resources"]


def test_skill_check_frontmatter(lab):
    from skilllab.studio import validate_skill
    issues = validate_skill(lab, "commit-helper@v1")
    assert isinstance(issues, list)
    entry = lab.variant_dir("commit-helper", "v1") / "SKILL.md"
    entry.write_text("---\nname: commit-helper\n---\n\n# T\n\nDo it.\n")
    issues = validate_skill(lab, "commit-helper@v1")
    assert any(i["check"] == "frontmatter" and i["severity"] == "error"
               and "description" in i["message"] for i in issues)


def test_skill_check_name_mismatch(lab):
    from skilllab.studio import validate_skill
    entry = lab.variant_dir("commit-helper", "v1") / "SKILL.md"
    text = entry.read_text()
    entry.write_text(text.replace("name: commit-helper",
                                  "name: other", 1))
    issues = validate_skill(lab, "commit-helper@v1")
    assert any("!= registry id" in i["message"] for i in issues)


def test_skill_resource_add(lab, tmp_path):
    from skilllab.studio import add_resource
    src = tmp_path / "extra.md"
    src.write_text("# extra")
    dest = add_resource(lab, "commit-helper@v1", str(src))
    assert dest.name == "extra.md"
    assert dest.parent.name == "resources"
    with pytest.raises(LabError):
        add_resource(lab, "commit-helper@v1",
                     str(tmp_path / "nope.md"))


def test_artifact_drift(lab):
    from skilllab import blueprint as bp
    from skilllab.studio import generate_skill, artifact_diff
    main(["project", "new", "proj-1"])
    bp.new_blueprint(lab, "proj-1", "bp-drift", "T")
    for k in ("name", "description", "problem_statement",
              "target_capability", "output_contract"):
        bp.set_field(lab, "proj-1", "bp-drift", k,
                     "x" * 50 if k == "description" else "x")
    for k in ("in_scope_tasks", "trigger_conditions",
              "execution_workflow", "evaluation_criteria"):
        bp.set_field(lab, "proj-1", "bp-drift", k, ["a"])
    bp.set_field(lab, "proj-1", "bp-drift", "name", "drift-skill")
    generate_skill(lab, "proj-1", "bp-drift", "drift-skill", "v1")
    d = artifact_diff(lab, "proj-1", "bp-drift", "drift-skill@v1")
    assert d["status"] == "synced"
    prev_rev = bp.get_blueprint(lab, "proj-1", "bp-drift").rev
    bp.set_field(lab, "proj-1", "bp-drift", "output_contract",
                 "new contract")
    d = artifact_diff(lab, "proj-1", "bp-drift", "drift-skill@v1")
    assert d["status"] == "drifted"
    assert d["gen_rev"] <= prev_rev
    assert d["bp_rev"] == prev_rev + 1
    assert "new contract" in d["diff"]


def test_studio_cli(lab, capsys):
    from skilllab import cli
    assert cli.main(["skill", "preview", "commit-helper@v1"]) == 0
    out = capsys.readouterr().out
    assert "tokens" in out and "resources/style.md" in out
    rc = cli.main(["skill", "check", "commit-helper@v1"])
    assert rc in (0, 1)


# ---------- phase 4b: llm architect + research draft ----------

def test_llm_suggest_mock_rejected(lab):
    from skilllab.studio import validate_skill  # noqa
    from skilllab import architect
    with pytest.raises(LabError):
        architect.suggest(lab, "commit-helper@v1", use_llm=True)


def test_rewrite_patch_apply(lab, tmp_path):
    from skilllab import architect
    from skilllab.models import Proposal
    entry = lab.variant_dir("commit-helper", "v1") / "SKILL.md"
    new_text = entry.read_text() + "\n## Added section\nstuff\n"
    p = Proposal(id="prop-999", skill="commit-helper", variant="v1",
                 finding="llm-review (test)",
                 patch={"type": "rewrite", "summary": "add section",
                        "file": "SKILL.md", "content": new_text},
                 status="approved", created="2025-01-01")
    from skilllab.release import dump_yaml
    dump_yaml(p.model_dump(mode="json"),
              lab.d("proposals") / "prop-999.yaml")
    architect.apply(lab, "prop-999")
    assert "Added section" in entry.read_text()


def test_draft_from_research(lab):
    from skilllab import blueprint as bp
    main(["project", "new", "rp"])
    main(["question", "add", "rp", "Does X work?"])
    main(["finding", "add", "rp", "--statement", "finding A"])
    bp.new_blueprint(lab, "rp", "bp-d", "T")
    touched = bp.draft_from_research(lab, "rp", "bp-d")
    got = bp.get_blueprint(lab, "rp", "bp-d")
    assert "problem_statement" in touched
    assert "Does X work?" in got.fields["problem_statement"]
    assert "decision_rules" in touched
    # second call fills nothing (no overwrite)
    assert bp.draft_from_research(lab, "rp", "bp-d") == []


def test_system_prompt_format(lab):
    from skilllab import blueprint as bp
    from skilllab.studio import generate_skill
    main(["project", "new", "sp-proj"])
    bp.new_blueprint(lab, "sp-proj", "sp-bp", "T")
    for k in ("name", "description", "problem_statement",
              "target_capability", "output_contract"):
        bp.set_field(lab, "sp-proj", "sp-bp", k,
                     "x" * 50 if k == "description" else "x")
    for k in ("in_scope_tasks", "trigger_conditions",
              "execution_workflow", "evaluation_criteria"):
        bp.set_field(lab, "sp-proj", "sp-bp", k, ["a"])
    out = generate_skill(lab, "sp-proj", "sp-bp", "sp-skill", "v1",
                         fmt="system-prompt")
    text = out.read_text()
    assert not text.startswith("---")
    assert "name:" not in text.splitlines()[0]


def test_experiment_from_blueprint(lab):
    from skilllab import blueprint as bp
    main(["project", "new", "pe"])
    bp.new_blueprint(lab, "pe", "bp-e", "T")
    for k in ("name", "description", "problem_statement",
              "target_capability", "output_contract"):
        bp.set_field(lab, "pe", "bp-e", k,
                     "x" * 50 if k == "description" else "x")
    for k in ("trigger_conditions", "execution_workflow",
              "evaluation_criteria"):
        bp.set_field(lab, "pe", "bp-e", k, ["a"])
    bp.set_field(lab, "pe", "bp-e", "in_scope_tasks",
                 ["Write a commit message"])
    bp.set_field(lab, "pe", "bp-e", "out_of_scope_tasks",
                 ["Refactor a module"])
    eid, created, skipped = bp.experiment_from_blueprint(
        lab, "pe", "bp-e", "commit-helper", "v1")
    assert eid == "exp-bp-e"
    assert len(created) == 2 and not skipped
    exp = lab.experiment(eid)
    assert exp.arms[0].skill is None
    assert exp.arms[1].skill == "commit-helper@v1"
    assert len(exp.tasks) == 2
    kinds = {lab.task(t).kind for t in exp.tasks}
    assert kinds == {"activation-positive", "activation-negative"}
    # rerun: experiment exists → error; tasks reused, not dup
    with pytest.raises(LabError):
        bp.experiment_from_blueprint(lab, "pe", "bp-e",
                                     "commit-helper", "v1")


def test_experiment_from_blueprint_cli(lab):
    from skilllab import blueprint as bp
    main(["project", "new", "pc"])
    bp.new_blueprint(lab, "pc", "bp-c", "T")
    bp.set_field(lab, "pc", "bp-c", "in_scope_tasks", ["Do the thing"])
    rc = main(["blueprint", "experiment", "pc", "bp-c",
               "--skill", "commit-helper", "--variant", "v1"])
    assert rc == 0
    assert (lab.experiments_dir / "exp-bp-c" /
            "experiment.yaml").is_file()


def test_failure_candidate(lab):
    from skilllab import failure
    from skilllab.models import load_yaml, dump_yaml
    d = _mkrun(lab, "r-fail")
    ry = load_yaml(d / "run.yaml"); ry["skill_ref"] = "commit-helper@v1"
    dump_yaml(ry, d / "run.yaml")
    dump_yaml({"checks": [{"id": "x", "method": "deterministic",
                           "status": "failed"}],
               "status": "failed", "success": False}, d / "eval.yaml")
    rep = failure.analyze_run(lab, "r-fail")
    rep["proposals"] = failure.proposals(rep)
    failure.write_report(lab, rep)
    dest = failure.candidate(lab, "r-fail", "v2-cand")
    assert (dest / "SKILL.md").is_file()
    md = (dest / "PROPOSALS.md").read_text()
    assert "Improvement proposals" in md and "r-fail" in md
    meta = lab.skill("commit-helper")
    assert any(v.id == "v2-cand" for v in meta.variants)
    with pytest.raises(LabError):
        failure.candidate(lab, "r-fail", "v2-cand")


# ---------- webio: ssrf guard ----------

def test_webio_blocks_private():
    from skilllab.webio import _check_url, fetch
    for bad in ["file:///etc/passwd", "gopher://x",
                "http://127.0.0.1:8080/x", "http://10.0.0.5/",
                "http://192.168.1.1/", "http://169.254.169.254/meta",
                "http://172.16.5.5/"]:
        with pytest.raises(LabError):
            _check_url(bad)
    # double-check tuple isn't exhausted on repeated calls
    for bad in ["http://10.1.2.3/", "http://192.168.0.9/"]:
        with pytest.raises(LabError):
            _check_url(bad)


def test_webio_search_no_provider(lab):
    from skilllab.webio import search
    with pytest.raises(LabError, match="no search provider"):
        search(lab, "test query")
