"""Deep Research engine — bounded, auditable research jobs.

A run: plan -> queries -> search -> fetch/read -> synthesize.
Hard limits everywhere. Sources cited = pages actually fetched.
Synthesis goes through the lab model; with `mock` the run still
executes the pipeline but the report is a deterministic digest of
real excerpts (clearly labelled, never fabricated claims).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from .lab import Lab, LabError
from .models import dump_yaml, load_yaml
from . import research, webio

LIMITS = {"queries": 6, "results_per_query": 5, "sources": 12,
          "excerpt_chars": 600, "seconds": 300}


def runs_dir(lab: Lab, pid: str) -> Path:
    d = research.project_dir(lab, pid) / "research-runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _next_id(d: Path) -> str:
    n = len([p for p in d.glob("dr-*") if p.is_dir()]) + 1
    return f"dr-{n:02d}"


def _save(rd: Path, state: dict) -> None:
    dump_yaml(state, rd / "run.yaml")


def plan(objective: str, max_q: int = LIMITS["queries"]) -> dict:
    """Deterministic plan draft — LLM refinement comes later; the user
    approves before searching."""
    qs = [s.strip() for s in re.split(r"[;?\n]+", objective) if s.strip()]
    return {"objective": objective,
            "queries": (qs or [objective])[:max_q],
            "limits": dict(LIMITS)}


def execute(lab: Lab, pid: str, rd: Path, log=print) -> dict:
    """Run the bounded pipeline. Resumable via run.yaml state."""
    st = load_yaml(rd / "run.yaml")
    st.update(status="running", updated=datetime.now().isoformat())
    _save(rd, st)
    t0 = time.time()
    plan_d = st["plan"]
    results, fetched = [], []
    try:
        for q in plan_d["queries"]:
            _budget(t0, st)
            hits = webio.search(lab, q, LIMITS["results_per_query"])
            st.setdefault("queries_done", []).append(q)
            results += hits
            _save(rd, st); log(f"searched: {q} ({len(hits)} hits)")
        seen = set()
        for r in results:
            _budget(t0, st)
            if len(fetched) >= LIMITS["sources"]:
                break
            u = r.get("url", "")
            if not u or u in seen:
                continue
            seen.add(u)
            try:
                page = webio.fetch(u)
            except LabError as e:
                log(f"skip {u}: {e}")
                continue
            page["query"] = r.get("query")
            fetched.append(page)
            st.setdefault("fetched", []).append(
                {"url": page["final_url"], "title": page["title"],
                 "hash": page["hash"]})
            _save(rd, st); log(f"read: {u}")
        rep = _report(st, fetched)
        (rd / "report.md").write_text(rep)
        st.update(status="completed", report="report.md",
                  updated=datetime.now().isoformat())
        _save(rd, st)
        return st
    except LabError as e:
        st.update(status="failed", error=str(e),
                  updated=datetime.now().isoformat())
        _save(rd, st)
        raise


def _budget(t0: float, st: dict) -> None:
    if time.time() - t0 > st["plan"]["limits"]["seconds"]:
        raise LabError("research budget exceeded (seconds)")


def _digest(fetched: list[dict]) -> str:
    """Deterministic digest for mock mode — real excerpts only."""
    out = []
    for i, p in enumerate(fetched, 1):
        out.append(f"{i}. **{p['title'] or p['final_url']}** "
                   f"({p['final_url']})\n   {p['text'][:LIMITS['excerpt_chars']]}")
    return "\n".join(out)


def _report(st: dict, fetched: list[dict]) -> str:
    srcs = "\n".join(f"- [{i}] {p['title'] or p['final_url']} — "
                     f"{p['final_url']} (hash {p['hash']})"
                     for i, p in enumerate(fetched, 1)) or "- none"
    return (f"# Deep Research: {st['objective']}\n\n"
            f"run: `{st['id']}` — model: {st.get('model','mock')}"
            f"{' (digest of real excerpts — no LLM synthesis)' if st.get('model','mock').startswith('mock') else ''}\n\n"
            f"## Queries\n" +
            "\n".join(f"- `{q}`" for q in st["plan"]["queries"]) +
            f"\n\n## Sources consulted\n{srcs}\n\n"
            f"## Extracted evidence\n\n{_digest(fetched)}\n")


def start(lab: Lab, pid: str, objective: str,
          approved_plan: dict | None = None) -> Path:
    """Create a research run. Pass approved_plan (edited plan()) to
    skip drafting; None = auto-approve the draft plan."""
    rd = runs_dir(lab, pid) / _next_id(runs_dir(lab, pid))
    rd.mkdir()
    p = approved_plan or plan(objective)
    p["queries"] = p["queries"][:LIMITS["queries"]]
    st = {"id": rd.name, "objective": objective, "plan": p,
          "status": "planned" if approved_plan is None else "approved",
          "model": lab.cfg.get("model", "mock"),
          "created": datetime.now().isoformat()}
    _save(rd, st)
    return rd


def approve(rd: Path) -> None:
    st = load_yaml(rd / "run.yaml")
    st["status"] = "approved"
    _save(rd, st)


def get(rd: Path) -> dict:
    return load_yaml(rd / "run.yaml")
