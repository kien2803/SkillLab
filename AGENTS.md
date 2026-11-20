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

- Research projects (`research/projects/<id>/`) are the top-level R&D
  container: `project.yaml` (lifecycle: draft→…→validating→completed→
  archived), `charter.md`, and entity dirs `questions/ sources/
  findings/ decisions/ notes/`. CLI: `lab project new|list|show|status|
  archive|delete`, `lab question add|list|status|link`,
  `lab source add|list|annotate`, `lab note add|list`,
  `lab finding add|list|status`, `lab decision add|list|status`.
  Finding `supported` is evidence-gated (≥1 project source or real
  exp/run ref; `kind: unverified` can never be supported). `project
  delete` only removes empty drafts — anything with research data must
  be archived instead. Entities validate refs: sources/questions must
  exist in-project, evidence must be a real experiment/run.
  `lab ui` adds a Research page + per-project pages.
- Skill blueprints (`research/projects/<pid>/blueprints/<bid>/`) bridge
  research → SKILL.md: 23 spec fields (see `blueprint.FIELDS`; `*` =
  required for generation), lifecycle draft→…→released, every edit bumps
  `rev` with a snapshot in `revisions/rNNN.yaml`. `blueprint status`
  beyond `designing` is gated on `blueprint validate` (required fields,
  in/out-of-scope contradictions, contract/verification warnings).
  `blueprint diff <p> <b> <r>` compares revisions; `from-question`
  prefills from research; `link --finding` ties to evidence.
- `lab blueprint generate <p> <b> --skill S --variant V [--format F]
  [--force]` (`skilllab/studio.py`) emits a skill artifact from a
  validated blueprint via `FORMATS` emitters (format abstraction —
  new targets register there). Refuses on validation errors and on
  existing variants (—force archives to `archive/skills/<s>/<v>-<ts>/`).
  Provenance: variant note `blueprint <pid>/<bid>@r<rev>` + comment in
  the file; blueprint records `generated_variants` and moves to
  `generated`.
- `lab failure analyze <run> [--write] | list | show <run>`
  (`skilllab/failure.py`) classifies a run's first observable failure
  deterministically — 11 spec categories + `infrastructure` /
  `evaluation-error` (never blamed on the skill). Signals: run/eval
  status, activation events vs task kind, failed checks by method,
  resource_read gaps, token outliers vs same task+arm median. Verdicts:
  clean | warning (soft signals) | failed | inconclusive. `--write`
  persists `failures/<run>.yaml` with evidence-linked causes +
  rule-based proposals (change / impact / side-effects).
- `lab release new|list|check|status` (`skilllab/release.py`) —
  `releases/<skill>/<version>.yaml`, lifecycle draft→…→released→
  deprecated. `released` is gated on a computed checklist: static
  analysis clean + ≥1 evaluated run on that variant + changelog
  (blueprint link optional). Static analysis alone never ships.
  `lab trace <skill@variant>` walks variant→blueprint→findings→
  questions→project→experiments→runs→insights.
- `lab ai suggest|list|show|approve|reject|apply`
  (`skilllab/architect.py`) — proposal workflow: analyzer findings →
  `proposals/prop-NNN.yaml` with explicit patch + unified-diff preview.
  `apply` refuses non-approved proposals and snapshots the original
  file inside the record for audit/rollback. Deterministic proposers
  today (unlink dead refs, description-trigger, extract-resources);
  LLM proposers plug into the same approval gate.
- `model: mock` in lab.yaml = deterministic offline agent (no API key).
  Real rollouts need litellm + provider keys; set `model:` accordingly
  (e.g. `anthropic/claude-sonnet-4-5`, `gpt-4o`). `model: cmd:<shell>`
  runs an external driver once per turn — JSON `{messages, tools}` on
  stdin, `{content, tool_calls, input_tokens, output_tokens}` on stdout.
  Inside rollouts/judge calls the driver runs through `run_in_workspace`,
  so the same `sandbox:` policy applies — it can't bypass execution
  security. This is the agent-framework integration point.
- Eval lifecycle: every check and eval has `status` ∈
  `pending | passed | failed | error` (error = eval infra broke, NOT a
  task failure). eval.yaml carries `evaluated_at`; judge checks carry
  `judge_model`. `lab eval <run> --score <crit>=<val>
  [--comment crit=text]` fills `method: human` criteria (value >1 = on
  criterion scale, <=1 = normalized 0..1) and recomputes.
  `lab compare <exp>` = arm×task score matrix (mean±stdev). Report adds
  an `incomplete` eval column, 95% CI on delta-vs-control, and warns on
  arms without score data or tasks that don't discriminate.
- `lab experiment list`, `lab experiment validate <exp>` (dry-run the
  pre-flight checks: ids, dup tasks, task/skill/rubric/fixture refs,
  one-independent-variable, temperature range — invalid experiments never
  reach rollout), `lab insight list --search <term>`,
  `lab insight refute|confirm <id>` (confirm needs ≥1 valid evidence ref);
  `insight new --evidence` validates the ref is a real experiment/run.
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
  `lab run`/`rerun` AND direct `run_rollout` calls refuse existing run
  ids — `--force`/`overwrite=True` moves the old run to
  `archive/<run_id>/<timestamp>/` (auditable, nothing is deleted).
  Concluded experiments are immutable (run is rejected).
- `lab run` validates the experiment first (same checks as
  `lab experiment validate`).
- LLM calls retry transient errors with backoff (`llm_retries`, `llm_timeout`
  in lab.yaml); a failed rollout/eval is recorded and doesn't kill the batch.
- `lab skill evaluate <id>` = graduation check (activation ≥80%, false ≤20%,
  delta>0 on ≥3 perf tasks; configurable via `graduation:` in lab.yaml).
- `lab insight promote <id>` is gated: needs ≥2 independent experiments as
  evidence (runs from one experiment don't count), non-empty `scope`, no
  TODO placeholders, and never overwrites an existing principle
  (`promoted_at` is recorded).
- `lab regression run <skill> --baseline V --candidate V [--tasks SUITE]
  [--model M] [--mode available|injected] [--rollouts N]
  [--threshold k=v]` runs a two-arm controlled comparison and writes
  `regressions/<id>/{regression.yaml,report.yaml,report.md}` — verdict
  (clean/regressed/inconclusive), six categories (critical, quality,
  activation, false-activation, efficiency, stability), per-task metrics,
  evidence and artifact diffs. `--tasks` accepts `all`/`default` (whole
  bank), a `suites/<name>.yaml` file, or comma-separated ids. Thresholds
  live in `lab.yaml` under `regression:`; `lab regression list|report
  <id>`; results are mock-labelled when model is mock.
- Principles (`principles/*.md`) can carry `lint:` rules in frontmatter —
  the knowledge feedback loop: confirmed insights lint new skills.
- `lab ui` generates a static HTML dashboard in `ui/` (no deps, works
  offline): Overview (stat cards, regression alerts, recent runs), Skills
  (registry + per-skill variant comparison), Benchmarks (variant/model/
  task tables + arm×task score matrix), Regressions (category-grouped
  findings + per-regression task tables), Experiments (config, arm
  metrics, run history), Knowledge Base (insights/principles with
  evidence + scope), and per-run detail pages (eval checks, skill
  events, artifacts, filterable transcript). All user content is
  HTML-escaped; mock-model data is labelled simulated. Tables are
  click-to-sort, key lists have text filters. `lab export <dir> [--tasks]` /
  `lab import <dir>` share packs between labs; import validates the
  manifest (only insights/principles/tasks dirs, version <=1), refuses
  symlinks/traversal/bad task.yaml, and reports imported/skipped/rejected.
- Report shows a "By model" section automatically when runs span >1 model
  (e.g. after `rerun --model`).
- `sandbox:` in lab.yaml is the execution policy for `run_command`,
  deterministic command checks and `cmd:` drivers: `bwrap` (isolated:
  no network, ro system, rw workspace — missing bwrap = clear error),
  `unsafe` (explicit unrestricted shell), unset/other = commands DISABLED
  (fail closed, never silent fallback). `command_timeout` caps each call;
  tool output is truncated (~8k chars).
- `lab diff <runA> <runB>` diffs transcript + workspace; `lab status` is a
  health check; `lab experiment conclude` closes an experiment and links
  insights.
- `examples/demo-lab/` is a working lab: try `lab report exp-trigger-wording`
  from that dir.
