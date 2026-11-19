# SkillLab

Experiment-first environment for researching and crafting AI agent skills.
Skill Lab turns skill design from personal intuition into a measurable,
reproducible practice: hypothesis → experiment → observe → principle → improve.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"          # core + pytest
.venv/bin/pip install -e ".[dev,llm]"      # + litellm for real models

.venv/bin/lab init my-lab                  # scaffold a lab directory
cd my-lab
lab skill new my-first-skill
lab analyze my-first-skill                 # static lint
lab experiment new exp-001                 # then edit experiment.yaml
lab run exp-001                            # model: mock runs offline
lab report exp-001
lab ui                                     # static HTML dashboard
```

## Concepts

- **Skills** are instruction artifacts with variants — SKILL.md is one kind.
- **Tasks** form a shared task bank (activation-positive/negative, performance)
  with deterministic checks (file-exists, file-content, json, command,
  script), LLM-judge and human rubric criteria.
- **Experiments** vary exactly one independent variable across arms
  (`lab experiment validate` pre-flights them); every rollout records a
  full transcript and `skill_events` (offered → activated → resource_read).
- **Evaluation** has an explicit lifecycle — `pending | passed | failed |
  error` — so judge outages and unscored human criteria never masquerade
  as task failures.
- **Execution policy** is explicit in `lab.yaml`: `sandbox: bwrap`
  isolates agent commands/checks/drivers (no network, read-only system),
  `sandbox: unsafe` is an opt-in unrestricted shell, and unset means
  commands are disabled — the lab fails closed, never silently.
- **Run history is append-only**: rerun ids never overwrite existing runs;
  `--force` archives the old run under `archive/` instead of deleting it.
- **Insights** link claims to evidence; promotion to **principles**
  requires ≥2 independent experiments — then `lint:` rules feed back into
  the analyzer.
- **Regression testing**: `lab regression run <skill> --baseline v1
  --candidate v2` benchmarks a new variant against a baseline on an
  equivalent task suite and reports categorized regressions (critical,
  quality, activation, false-activation, efficiency, stability) with
  per-task evidence — see `regressions/<id>/report.md`.

See `SPEC.md` for the full design spec and `examples/demo-lab/` for a
working lab (`lab report exp-trigger-wording`).

## Tests

```bash
.venv/bin/python -m pytest tests/          # offline, uses the mock model
```
