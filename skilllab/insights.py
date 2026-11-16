"""Insight store: structured knowledge with evidence links."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .lab import Lab, LabError
from .models import parse_frontmatter

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
    ev = f'"{evidence}"' if evidence else ""
    p.write_text(TEMPLATE.format(iid=iid, evidence=ev))
    return p


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


def promote(lab: Lab, insight_id: str) -> Path:
    src = lab.insights_dir / f"{insight_id}.md"
    if not src.is_file():
        raise LabError(f"Insight '{insight_id}' not found.")
    fm, body = parse_frontmatter(src.read_text())
    fm["status"] = "promoted"
    dest = lab.principles_dir / src.name
    dest.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False,
                                             allow_unicode=True) + "---\n" + body)
    src.unlink()
    return dest
