# Next Milestone — SkillLab R&D Workbench

## Current architecture

- `skilllab/` — domain + execution engine (lab config, engine,
  evaluate, graduation, release, deep research, share/registry).
  Filesystem-only persistence (YAML/MD/JSONL).
- `web/backend/` — FastAPI (`app.py` ~1.8k lines single file) +
  `jobs.py` (SQLite job store + daemon threads).
- `web/frontend/` — React 18 + vite, single `App.jsx` (~1.65k lines),
  `data-terminal` visual system.
- Auth: bearer token on all `/api/*` (middleware); sign-in gate.
- Persistence: `<lab>/jobs/jobs.sqlite` for job metadata only.

## Confirmed issues (this milestone)

- CI frontend job: playwright `webServer` calls `.venv/bin/uvicorn`
  but no venv is created → `.venv/bin/uvicorn: not found`.
- `pypdf` imported by `webio.extract_doc` but not in `web` extras.
- `jobs.py`: daemon threads lost on restart (running jobs look alive
  forever), no worker bound, no timeout, `submit` races.
- `release.py`: variant hash pinned at validate but run evidence not
  required to hash-match the released content.
- `graduation.py`: usable-vs-total accounting exists but exclusion
  reasons are not surfaced.
- Skill Editor UI missing (API exists).
- Experiment Builder UI missing (scaffold + run only).
- Experiment runs execute synchronously inside POST handlers.

## Implementation stages

1. CI/deps/docker (this file's stage 1).
2. Jobs hardening; release hash evidence; graduation accounting.
3. Skill Editor (tree/editor/save/revisions/validate).
4. Experiment Builder (config forms, arms/tasks/model/rubric).
5. Experiment execution via jobs.
6. Tests; 7. extraction + docs.

## Files changed / tests — see git log + final report.
