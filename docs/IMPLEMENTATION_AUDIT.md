# Implementation Audit — Stage 0→2 findings

Severity: Critical / High / Medium / Low. All entries fixed and
verified (tests listed); see commits `e4dcab1`, `c2c7790`.

## Security — path traversal (Critical)

| File | Issue | Fix | Test |
|---|---|---|---|
| skilllab/lab.py | user-controlled ids reached filesystem paths | `check_id()` validates every id segment; applied to all loaders + API params | test_skill_traversal, test_variant_path_escape |
| engine.py | task `fixtures`/`prompt` could read outside task dir | resolved-path containment checks | test_task_fixture_traversal |
| architect.py | proposal patch `file` could escape variant dir | containment in preview + apply | test_architect_* |
| studio.py | skill_id/variant_id unsanitized → SKILL.md written outside skills/ | `_ID_RE` + containment | tests/test_lab.py |
| web/backend/app.py | `/api/v1/import`, `/skills/import` accepted arbitrary server paths | restricted to `<lab>/exports|imports/` or git URLs | TestClient (import /etc → 400) |
| upload endpoints | filename traversal | basename strip + ext allowlist + 2MB cap | manual TestClient |

## Security — web/API (Critical→High)

| File | Issue | Fix |
|---|---|---|
| webio.py | redirect targets validated after urlopen already followed them | `_SafeRedirect` validates every hop pre-follow; DNS resolved + global-address check; ports 80/443; size/type/timeout budgets |
| app.py | GET endpoints + SSE stream unauthenticated; EventSource can't send bearer | global auth middleware on /api/*; fetch-streaming reader in App.jsx |
| app.py | GET stream spawned background work (violates read-only GET) | POST `/research/{p}/{r}/run` via job queue; stream observes only |
| app.py | no token requirement in prod | `SKILLLAB_ENV=production` without token = startup failure |
| app.py | no security headers/CORS/rate limit | headers middleware; explicit CORS origins; fixed-window limiter |

## Correctness (High)

| File | Issue | Fix | Test |
|---|---|---|---|
| architect.py | preview wrote resources/detail.md (side effects); stale proposals could apply over changed files | pure `_patched_files()` (multi-file), base SHA-256 recorded at suggest, stale rejected, rollback() restores | test_architect_* |
| evaluate.py | missing rubric silently fell back | explicit `status=error`, `evaluator=missing-rubric`; provenance fields (rubric/evaluator/evaluated_at) | test_legacy_eval_yaml_status_sync + eval tests |
| graduation.py | infra-error runs counted; unrelated control runs pooled | error runs excluded; equivalence key (experiment, model, mode, temperature); n_total vs n_runs | graduation tests |
| release.py | failed evals counted as evidence; no content pinning | variant content hash pinned at validate; checklist requires *passed* evidence; `released` refused on failed gates | release tests |
| insights.py | promotion before confirmation; unconfirmed evidence | confirm needs completed evals; promote needs confirmed + ≥2 independent experiments; existing principle check first | test_insight_* |
| deep.py | non-resumable; no LLM synthesis; sources never saved | resumable per-step state; LLM synth (labelled; mock = deterministic digest); sources persisted; `candidate_findings` | pytest suite |
| share.py | partial import on failure | validate-all → stage → atomic apply + rollback | pack tests |
| studio.py | system-prompt format wrote to SKILL.md | FORMATS records w/ filename; SKILL.md stub keeps variant loadable | studio tests |
| registry.py | any URL scheme; credential prompts; symlink escape | protocol allowlist; GIT_TERMINAL_PROMPT=0; subdir containment; symlink reject | — |

## Infra

| File | Issue | Fix |
|---|---|---|
| pyproject.toml | CI installed missing `web` extra | explicit `web`/`dev` extras |
| Dockerfile | dev-mode only, no SPA, ran as root | multi-stage build, non-root, healthcheck |
| docker-compose.yml | vite dev server in "prod" | prod image only + restart policy |
| .gitignore | dist/ tracked | untracked; jobs/exports/packtmp ignored |

## Remaining (next phases)

- Backend split into routers (app.py ~1.7k lines) — structure holds,
  refactor deferred: all routes already delegate to skilllab/*
- Frontend: feature-folder split; Skill Editor UI needs wiring to the
  new /file endpoints (API ready); Blueprint/Experiment visual builders
- Job queue: only deep-research wired so far; experiment/regression
  runs still spawn threads
- TypeScript migration; annotations UI; PDF reading; Monaco editor
