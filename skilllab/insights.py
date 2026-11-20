"""Insight store: structured knowledge with evidence links."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml

from .lab import Lab, LabError, check_id
from .models import load_yaml, parse_frontmatter

TEMPLATE = """---
id: {iid}
confidence: candidate
evidence: [{evidence}]
scope: []
status: candidate        # candidate | confirmed | refuted | promoted
---
## Phát biểu / Statement

TODO: one precise, falsifiable claim.

## Điều kiện áp dụng / Conditions

TODO: when does this hold? (model class, task type, skill kind…)

## Phản ví dụ / Counter-evidence

TODO: known exceptions or refuting runs.
"""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-") or "insight"


def new_insight(lab: Lab, title: str, evidence: str = "") -> Path:
    iid = _slug(title)
    p = lab.insights_dir / f"{iid}.md"
    if p.exists():
        raise LabError(f"Insight '{iid}' already exists.")
    if evidence and not _evidence_exists(lab, evidence):
        raise LabError(f"evidence '{evidence}' is not an experiment or run "
                       "in this lab — insights must link real evidence")
    ev = f'"{evidence}"' if evidence else ""
    p.write_text(TEMPLATE.format(iid=iid, evidence=ev))
    return p


def _evidence_exists(lab: Lab, ref: str) -> bool:
    return ((lab.experiments_dir / ref / "experiment.yaml").is_file()
            or (lab.runs_dir / ref / "run.yaml").is_file())


def list_insights(lab: Lab) -> list[dict]:
    out = []
    for d in (lab.insights_dir, lab.principles_dir):
        for p in sorted(d.glob("*.md")):
            fm, _ = parse_frontmatter(p.read_text())
            out.append({
                "id": fm.get("id", p.stem),
                "status": fm.get("status", "?"),
                "confidence": fm.get("confidence", "?"),
                "evidence": fm.get("evidence", []),
                "path": str(p),
                "kind": "principle" if d == lab.principles_dir else "insight",
            })
    return out


def _set_status(lab: Lab, insight_id: str, status: str) -> Path:
    check_id("insight", insight_id)
    for d in (lab.insights_dir, lab.principles_dir):
        p = d / f"{insight_id}.md"
        if p.is_file():
            fm, body = parse_frontmatter(p.read_text())
            fm["status"] = status
            p.write_text("---\n" + yaml.safe_dump(
                fm, sort_keys=False, allow_unicode=True) + "---\n" + body)
            return p
    raise LabError(f"Insight '{insight_id}' not found.")


def confirm(lab: Lab, insight_id: str) -> Path:
    """Mark an insight confirmed — requires at least one valid evidence ref."""
    check_id("insight", insight_id)
    for d in (lab.insights_dir, lab.principles_dir):
        p = d / f"{insight_id}.md"
        if p.is_file():
            fm, _ = parse_frontmatter(p.read_text())
            ev = fm.get("evidence") or []
            if isinstance(ev, str):
                ev = [ev]
            if not _evidence_experiments(lab, ev):
                raise LabError(f"insight '{insight_id}' has no valid "
                               "experiment/run evidence to confirm")
            return _set_status(lab, insight_id, "confirmed")
    raise LabError(f"Insight '{insight_id}' not found.")


def refute(lab: Lab, insight_id: str) -> Path:
    """Mark an insight refuted — refuted insights are kept, not deleted."""
    return _set_status(lab, insight_id, "refuted")


def _evidence_experiments(lab: Lab, evidence: list) -> set[str]:
    """Distinct experiment ids referenced by the evidence list.

    Run ids resolve to their parent experiment — repeats of the same
    experiment never count as independent evidence.
    """
    exps = set()
    for ref in evidence:
        ref = str(ref)
        if (lab.experiments_dir / ref / "experiment.yaml").is_file():
            exps.add(ref)
        else:
            ry = lab.runs_dir / ref / "run.yaml"
            if ry.is_file():
                exp = load_yaml(ry).get("experiment")
                if exp:
                    exps.add(str(exp))
    return exps


def promote(lab: Lab, insight_id: str) -> Path:
    """Promote an insight to a principle — gated on evidence.

    Requires: >=2 independent experiments as evidence, non-empty scope,
    and a completed writeup (no TODO placeholders). Existing principles
    are never overwritten.
    """
    src = lab.insights_dir / f"{check_id('insight', insight_id)}.md"
    if not src.is_file():
        raise LabError(f"Insight '{insight_id}' not found.")
    fm, body = parse_frontmatter(src.read_text())
    ev = fm.get("evidence") or []
    if isinstance(ev, str):
        ev = [ev]
    exps = _evidence_experiments(lab, ev)
    if len(exps) < 2:
        raise LabError(
            f"promotion requires evidence from >=2 independent experiments "
            f"(found {len(exps)}: {', '.join(sorted(exps)) or 'none'})")
    if not fm.get("scope"):
        raise LabError("insight needs a non-empty 'scope' before promotion "
                       "— where does this finding apply?")
    if "TODO" in body:
        raise LabError("insight still contains TODO placeholders — finish "
                       "the statement/conditions/counter-evidence sections")
    dest = lab.principles_dir / src.name
    if dest.exists():
        raise LabError(f"principle '{dest.stem}' already exists — refusing "
                       "to overwrite")
    fm["status"] = "promoted"
    fm["promoted_at"] = date.today().isoformat()
    dest.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False,
                                             allow_unicode=True) + "---\n" + body)
    src.unlink()
    return dest
