# Next Milestone — SkillLab R&D Workbench

## Current architecture

- `skilllab/` — domain + execution engine (lab config, engine,
  evaluate, graduation, release, deep research, share/registry,
  regression). Filesystem-only persistence (YAML/MD/JSONL).
- `web/backend/` — FastAPI (`app.py` single file) + `jobs.py`
  (SQLite store, bounded ThreadPoolExecutor, cancel/timeout/
  interrupted-recovery, schema migration).
- `web/frontend/` — React 18 + vite. `App.jsx` (pages/shell) +
  extracted `features/` modules: `skills/SkillEditor.jsx`,
  `experiments/ExperimentBuilder.jsx`; shared client `api.js`.
- Auth: bearer token on all `/api/*` (middleware); sign-in gate UI.
- Persistence: `<lab>/jobs/jobs.sqlite` for job metadata only.

## Milestone status (this pass)

DONE
- CI: frontend job creates venv + installs `.[web]` (uvicorn found).
- `pypdf` in `web` extras; malformed/empty PDF handled.
- jobs: bounded pool, WAL, `interrupted` recovery, cooperative
  timeout, cancel checkpoints, dedupe by key, legacy schema migrate.
- release: canonical `dir_hash` everywhere; evidence must match
  skill+variant+content-hash+ok-run+completed-eval; legacy/unverifiable
  bucket reported separately; gates configurable + validated.
- graduation: usable-vs-total sample accounting + exclusion reasons.
- Skill Editor: 3-pane workspace (tree/editor/validate+revisions),
  base_sha optimistic concurrency (409 UI), snapshot-on-write,
  restore, delete guard, create (PUT), rename (POST /rename),
  upload resource, auto-open SKILL.md, Ctrl+S, beforeunload.
- Experiment Builder: structured forms (general/model/arms/tasks),
  save→server validate, concluded=read-only, run→job w/ live
  progress+logs, detail runs list. Endpoints: GET detail,
  PUT /config, POST /duplicate, run/rerun→job.
- Executions (experiment run/rerun, regression) are jobs —
  `{job,status,planned}` returned; regression loop reports real
  progress + honours cancel (stops cleanly, resumable via rerun).
- Tests: `tests/test_web.py` (11 TestClient tests: auth, editor
  tree/write-409/revisions/restore/delete/rename guards, experiment
  detail/config/duplicate/job, regression job, jobs API);
  e2e 24/24 (auth gates via isolated request contexts, editor flow,
  builder flow); e2e uses a disposable lab copy at
  `/tmp/skilllab-e2e-lab` — demo-lab is never mutated.
- demo-lab: release 1.0.0 has real exact-hash evidence (v3-bp
  rollout + passed eval); older-content runs stay `unverifiable`.

REMAINING LIMITATIONS
- Editor: plain textarea (no syntax highlight); no token-estimate
  panel inside editor (exists in preview).
- Builder: no dedicated experiment dashboard page (Compare/Report/
  Runs panels exist on the list view); rubric is per-task, not a
  per-experiment selector.
- Regression card shows "job queued" only — no live progress bar
  (polling exists in the builder; a shared `RunMonitor` component
  is the next extraction).
- `app.py` remains one file — `routers/` split deferred (routes
  already delegate to `skilllab/*`).
- No TypeScript / state-library migration (out of scope).

## Next milestone candidates

1. `features/jobs/JobMonitor.jsx` — global job bar (poll /jobs,
   cancel buttons, log drawer) shared by experiments, regressions,
   deep research.
2. Editor: create-folder UX, drag-reorder, binary badge, token
   estimate + analysis panel consolidation.
3. Builder: task detail drawer (rubric/kind/fixtures), arm-level
   overrides table, experiment history view.
4. Backend `routers/` split when app.py next grows.
5. Docker e2e check on a host with a daemon (CI covers build).

## Tests performed

- `pytest tests/` → 107/107
- `npx playwright test` → 24/24 (incl. editor save + builder
  create/validate/save flows, isolated disposable lab)
- TestClient flows: auth 401/200, editor write→409→revision→
  restore→rename guards, experiment config/duplicate/job-run,
  regression job completion.
