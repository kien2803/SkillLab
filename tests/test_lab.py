"""End-to-end test of the lab pipeline using the mock model (offline)."""

from pathlib import Path

import pytest

from skilllab.analyzer import analyze_skill
from skilllab.cli import main
from skilllab.engine import run_experiment
from skilllab.evaluate import evaluate_run
from skilllab.lab import Lab
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
    assert "commit-helper" in index
    assert "exp-test-trigger" in index
    assert (out / "skill-commit-helper.html").is_file()
    run_page = next(out.glob("run-*.html"))
    assert "transcript" in run_page.read_text()


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
