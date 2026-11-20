# SkillLab → AI Agent Skill R&D Laboratory — implementation roadmap

Vision: turn an idea or unsolved agent-capability problem into a
well-designed, tested, reproducible, continuously improvable skill.

DISCOVER → RESEARCH → DESIGN → CREATE → EXPERIMENT → ANALYZE →
IMPROVE → VALIDATE → RELEASE → LEARN

Benchmarking stays a subsystem; the research lifecycle drives the
product. Work proceeds in independently testable vertical slices.

## Done

- **Phase 0 — audit** — 53-test baseline green; modules mapped:
  registry/analyzer/engine/evaluate/report/regression/insights/
  graduation/share/ui. Constraints preserved: file-based storage,
  append-only runs, fail-closed sandbox, mock labelling, HTML escaping.
- **Phase 1 — Research Project foundation** (`skilllab/research.py`)
  - `research/projects/<id>/`: project.yaml + charter.md +
    questions/ sources/ findings/ decisions/ notes/
  - Full lifecycle enum (draft→archived); archive-over-delete policy:
    deletion allowed only for empty drafts.
  - Research questions with status + links to findings/experiments.
  - Source library: url/doc/note/paper/other, author, access date,
    excerpt, annotations; `doc` paths verified on disk.
  - Findings: statement, kind (verified-source / observation /
    ai-hypothesis / unverified), confidence, limitations, refs to
    questions/sources/experiments/runs — all validated against real
    lab artifacts. `supported` is evidence-gated like insight promotion.
  - Decisions: decision/rationale/alternatives + status lifecycle.
  - CLI groups: `project`, `question`, `source`, `note`, `finding`,
    `decision` (~20 subcommands).
  - Dashboard: Research nav page (project index w/ entity counts) +
    per-project pages (objective/problem callouts, charter, all entity
    tables with status/kind/confidence badges).
  - 5 new tests; suite at 58.

- **Phase 2 — Skill Blueprint** (`skilllab/blueprint.py`)
  - `research/projects/<pid>/blueprints/<bid>/`: blueprint.yaml +
    `revisions/rNNN.yaml` snapshots — every save bumps `rev`
  - 23 spec fields with labels + required flags; lifecycle
    draft→…→released; statuses ≥ ready_for_generation gated on
    validation (required fields, in/out-of-scope contradiction,
    contract/trigger/verification warnings)
  - `blueprint new|list|show|set|from-question|link|status|validate|
    revisions|diff` — field edits via `--set f=v` / `--add f=v`
  - related_findings links validated against project findings;
    generated_variants reserved for Phase 3 studio
  - UI: blueprints table on project pages (status, rev, issue cell) +
    per-blueprint pages (validation table, all 23 fields, revisions)
  - 5 new tests; suite at 63.

- **Phase 3a — Blueprint → skill generation** (`skilllab/studio.py`)
  - `FORMATS` emitter registry (`skill-md` today) — new export formats
    plug in without touching registry/CLI
  - `blueprint generate --skill S --variant V`: refuses on validation
    errors; refuses silent variant overwrite (`--force` archives to
    `archive/skills/`); variant note + in-file comment carry
    `blueprint <pid>/<bid>@r<rev>` provenance; blueprint auto →
    `generated` + records `generated_variants`
  - demo-lab: `commit-helper-research` project → q01 → f01 (evidence-
    backed, supported) → `commit-helper-v2` blueprint r14 →
    `commit-helper@v3-bp` variant — full research→skill chain persisted
  - suite at 65.

- **Phase 5a — Failure analysis** (`skilllab/failure.py`)
  - deterministic classifier: first observable failure + ordered causes
    with artifact citations (run.yaml/eval.yaml/skill events)
  - 13 categories; infra + eval errors separated from task failures;
    verdicts clean/warning/failed/inconclusive
  - `failures/<run>.yaml` persists report + rule-based proposals
    (problem→change→impact→side-effects) — feeds the improvement loop
  - verified live: catches v2-bad activation regression on demo-lab runs
  - suite at 70.

- **Phase 6a — Release Center + trace** (`skilllab/release.py`)
  - releases/<skill>/<version>.yaml; `released` gated on computed
    checklist (static analysis, ≥1 evaluated run on the variant,
    changelog; blueprint-link optional)
  - `lab trace <ref>` reconstructs the full provenance chain —
    demo-lab `commit-helper@v3-bp` → blueprint r14 → f01 (supported)
    → q01 → project → runs
  - end-to-end demo: research → blueprint → generate → regression
    evidence → checklist PASS → released 1.0.0
  - suite at 71.

- **Phase 4a — AI Architect proposal gate** (`skilllab/architect.py`)
  - `proposals/prop-*.yaml`: finding → explicit patch + unified-diff
    preview; statuses pending/approved/rejected/applied
  - `apply` refuses unapproved proposals; original file content kept in
    the record for audit — no silent overwrites, no fabricated changes
  - deterministic patch types: unlink (dead refs), description-trigger,
    extract-resources (progressive disclosure); LLM proposers reuse the
    same gate later
  - verified: cleared code-review@v1 dead-link errors via approve→apply
  - suite at 73.

## Next slices (priority order)

- **Phase 3b — Skill Studio tools** — DONE: `skill preview` (frontmatter/
  sections/resources + token estimate), `skill check` (analyzer +
  frontmatter schema), `skill resource` (copy into `resources/`),
  `blueprint drift` (on-disk vs fresh emit, provenance-aware).
  `system-prompt` target added; more FORMATS pluggable.
- **Phase 4 — AI Skill Architect** — DONE (4a+4b): deterministic
  proposers + `--llm` rewrite proposals over `llm.py` (mock safely
  refused), `blueprint draft` research-grounded prefill, unified
  proposal/approval/apply gate with original-content snapshots.
  Rules honored: diffs shown, no fabricated evidence, user approves.
- **Phase 5 — Experiment + failure analysis** — DONE-lite: `blueprint experiment` scaffolds tasks+experiment from scope lists (draft tasks need authored checks); failure analyzer live. Remaining: experiment categories taxonomy, failure→candidate-variant loop. Original notes: experiment categories
  (capability/trigger/workflow/instruction/resource/tool-use/
  compatibility/reliability/efficiency), experiments creatable from
  blueprint criteria or failed runs; failure analyzer: first observable
  failure → categorized cause → evidence-linked proposal → approved
  candidate variant. Provenance: skill hash, blueprint revision, rubric
  version, judge info.
- **Phase 6 — Knowledge + Release** — evidence graph across
  project→question→source→finding→blueprint→variant→experiment→run→
  insight→principle; Release Center: checklist, validation evidence,
  version/changelog, export package, release history
  (draft→candidate→validated→released→deprecated).
- **Phase 7 — UX hardening** — dashboard reorganized into the 8-area
  lab navigation (Overview / Projects / Workspace / Studio / Architect /
  Experiment Lab / Knowledge / Release) once the domains exist.

## Data/migration notes

- `research/` is additive: `Lab.init` creates `research/projects/`;
  loaders tolerate its absence in older labs (lazy mkdir on write).
- All research entities are YAML/MD — same git-friendly, diffable
  storage as the rest of the lab. No database, stays offline-first.
- Schema evolution goes through pydantic literals + `load_yaml`
  defaults; breaking changes get explicit migrations, not silent rewrites.
