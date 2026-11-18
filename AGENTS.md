# Skill Lab — repo notes

Experiment-first environment for researching AI agent skills. Design spec:
`SPEC.md`. Implementation: Python package `skilllab/` with `lab` CLI.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"          # core + pytest
.venv/bin/pip install -e ".[dev,llm]"      # + litellm for real models
```

## Verify

```bash
.venv/bin/python -m pytest tests/          # offline, uses model=mock
```

## Key concepts

- `model: mock` in lab.yaml = deterministic offline agent (no API key).
  Real rollouts need litellm + provider keys; set `model:` accordingly
  (e.g. `anthropic/claude-sonnet-4-5`, `gpt-4o`). `model: cmd:<shell>`
  runs an external driver once per turn — JSON `{messages, tools}` on
  stdin, `{content, tool_calls, input_tokens, output_tokens}` on stdout,
  cwd = run workspace. This is the agent-framework integration point.
- `lab eval <run> --score <crit>=<val>` fills `method: human` rubric
  criteria (value >1 = on criterion scale, <=1 = normalized 0..1) and
  recomputes rubric_score. `lab compare <exp>` = arm×task score matrix
  (mean±stdev). Report adds 95% CI on delta-vs-control and warns on
  arms without score data or tasks that don't discriminate.
- `lab experiment list`, `lab insight list --search <term>`,
  `lab insight refute <id>`; `insight new --evidence` validates the ref
  is a real experiment/run.
- `lab skill scan [--import]` discovers skills under ~/.agents/skills,
  ~/.claude/skills, ~/.config/devin/skills (+ repo-local equivalents).
  `lab skill add <git-url>[#subdir]` shallow-clones and imports.
- Two injection modes per experiment: `available` measures trigger quality
  (agent must call `read_skill`), `injected` measures content quality.
  Activation metrics are only counted for `available` runs.
- Skills referenced by any experiment arm are the independent variable and
  are hidden from arms with `skill: null` (control must not see them).
- `lab rerun <exp> --batch <name>` keeps run history append-only;
  `--model X` overrides model for drift probes (auto-batches).
  `lab run`/`rerun` refuse to overwrite existing run ids — pass `--force`
  to redo them. Concluded experiments are immutable (run is rejected).
- `lab run` validates the experiment first: tasks and skill@variant refs
  must resolve, and arms may only differ on the declared `independent_var`.
- LLM calls retry transient errors with backoff (`llm_retries`, `llm_timeout`
  in lab.yaml); a failed rollout/eval is recorded and doesn't kill the batch.
- `lab skill evaluate <id>` = graduation check (activation ≥80%, false ≤20%,
  delta>0 on ≥3 perf tasks; configurable via `graduation:` in lab.yaml).
- Principles (`principles/*.md`) can carry `lint:` rules in frontmatter —
  the knowledge feedback loop: confirmed insights lint new skills.
- `lab ui` generates a static HTML dashboard in `ui/` (index + experiment,
  skill, run-transcript, insight pages). `lab export <dir> [--tasks]` /
  `lab import <dir>` share packs (insights, principles, tasks) between labs.
- Report shows a "By model" section automatically when runs span >1 model
  (e.g. after `rerun --model`).
- `sandbox: bwrap` in lab.yaml isolates `run_command` (no network, ro
  system, rw workspace) for both agent tools and deterministic checks.
- `lab diff <runA> <runB>` diffs transcript + workspace; `lab status` is a
  health check; `lab experiment conclude` closes an experiment and links
  insights.
- `examples/demo-lab/` is a working lab: try `lab report exp-trigger-wording`
  from that dir.
