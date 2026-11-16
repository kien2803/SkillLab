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
- **Tasks** form a shared task bank (activation-positive/negative, performance).
- **Experiments** vary exactly one independent variable across arms; every
  rollout records a full transcript and `skill_events` (offered → activated →
  resource_read).
- **Insights** link claims to evidence; confirmed insights promote to
  **principles** whose `lint:` rules feed back into the analyzer.

See `SPEC.md` for the full design spec and `examples/demo-lab/` for a
working lab (`lab report exp-trigger-wording`).

## Tests

```bash
.venv/bin/python -m pytest tests/          # offline, uses the mock model
```
