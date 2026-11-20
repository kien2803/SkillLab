"""Static analyzer: lint skills without running them.

Each check emits Finding(check, severity, message, file). Severities:
info < warn < error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .lab import Lab
from .models import est_tokens, parse_frontmatter
from .registry import skill_entry_file, skill_description


@dataclass
class Finding:
    check: str
    severity: str          # info | warn | error
    message: str
    file: str = ""

    def fmt(self) -> str:
        loc = f" [{self.file}]" if self.file else ""
        return f"{self.severity.upper():5} {self.check:24} {self.message}{loc}"


_TRIGGER_HINTS = re.compile(
    r"use when|when the user|if the user|khi nào|khi user|trigger|"
    r"asked to|requests? .*(commit|refactor|fix|review)|e\.g\.,",
    re.IGNORECASE,
)

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)|`([^`]+\.(?:md|py|sh|json|ya?ml|txt))`")


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zà-ỹ0-9]+", text.lower()) if len(t) > 2}


def _check_frontmatter(vdir: Path) -> list[Finding]:
    entry = skill_entry_file(vdir)
    if not entry:
        return [Finding("frontmatter-valid", "error", "no SKILL.md entry file",
                        str(vdir))]
    fm, _ = parse_frontmatter(entry.read_text())
    out = []
    if not fm:
        out.append(Finding("frontmatter-valid", "error",
                           "missing YAML frontmatter", entry.name))
    else:
        for key in ("name", "description"):
            if not fm.get(key):
                out.append(Finding("frontmatter-valid", "error",
                                   f"frontmatter missing '{key}'", entry.name))
    return out


def _check_description(vdir: Path, cfg: dict) -> list[Finding]:
    desc = skill_description(vdir)
    lo = cfg["description_min_chars"]
    hi = cfg["description_max_chars"]
    out = []
    if len(desc) < lo:
        out.append(Finding("description-quality", "warn",
                           f"description too short ({len(desc)} chars < {lo}) — "
                           "agents can't tell when to trigger"))
    elif len(desc) > hi:
        out.append(Finding("description-quality", "warn",
                           f"description too long ({len(desc)} chars > {hi}) — "
                           "wastes registry-listing tokens on every prompt"))
    if not _TRIGGER_HINTS.search(desc):
        out.append(Finding("description-quality", "info",
                           "no explicit trigger condition detected — consider "
                           "naming concrete situations ('use when …')"))
    if "TODO" in desc:
        out.append(Finding("description-quality", "error",
                           "description still contains scaffold TODO"))
    return out


def _check_budget(vdir: Path, cfg: dict) -> list[Finding]:
    entry = skill_entry_file(vdir)
    if not entry:
        return []
    text = entry.read_text()
    lines = text.count("\n") + 1
    toks = est_tokens(text)
    out = []
    if lines > cfg["skill_md_max_lines"]:
        out.append(Finding("token-budget", "warn",
                           f"entry file is {lines} lines (>{cfg['skill_md_max_lines']})",
                           entry.name))
    if toks > cfg["skill_md_token_warn"]:
        out.append(Finding("token-budget", "warn",
                           f"entry file ~{toks} tokens (>{cfg['skill_md_token_warn']})",
                           entry.name))
    has_resources = (vdir / "resources").is_dir() and any(
        (vdir / "resources").iterdir())
    if toks > cfg["skill_md_token_warn"] and not has_resources:
        out.append(Finding("progressive-disclosure", "warn",
                           "heavy content embedded in entry file — move detail "
                           "into resources/ and link to it", entry.name))
    return out


def _check_dead_links(vdir: Path) -> list[Finding]:
    out = []
    for f in vdir.rglob("*.md"):
        text = f.read_text()
        for m in _LINK_RE.finditer(text):
            ref = m.group(1) or m.group(2)
            if not ref or ref.startswith(("http://", "https://", "#", "mailto:")):
                continue
            ref = ref.split("#")[0]
            if not (f.parent / ref).exists() and not (vdir / ref).exists():
                out.append(Finding("dead-links", "error",
                                   f"reference to missing file '{ref}'",
                                   str(f.relative_to(vdir))))
    return out


_ABS_RE = re.compile(r"\b(ALWAYS|NEVER)\b")
_OBVIOUS_RE = re.compile(
    r"\b(write clean code|follow best practices|be helpful|use comments)\b",
    re.IGNORECASE)


def _check_antipatterns(vdir: Path) -> list[Finding]:
    entry = skill_entry_file(vdir)
    if not entry:
        return []
    text = entry.read_text()
    out = []
    n_abs = len(_ABS_RE.findall(text))
    if n_abs >= 3:
        out.append(Finding("anti-patterns", "info",
                           f"{n_abs} absolute directives (ALWAYS/NEVER) — "
                           "over-prescriptive skills can crowd out model judgment"))
    if _OBVIOUS_RE.search(text):
        out.append(Finding("anti-patterns", "info",
                           "restates default model knowledge ('write clean code' "
                           "etc.) — tokens spent teaching what the model already does"))
    return out


def _check_examples(vdir: Path) -> list[Finding]:
    entry = skill_entry_file(vdir)
    if not entry:
        return []
    if "```" not in entry.read_text():
        return [Finding("anti-patterns", "info",
                        "no code block / concrete example in entry file — "
                        "examples anchor agent behavior better than prose",
                        entry.name)]
    return []


def _check_resource_bloat(vdir: Path, cfg: dict) -> list[Finding]:
    rdir = vdir / "resources"
    if not rdir.is_dir():
        return []
    limit = cfg.get("resource_token_warn", 4000)
    out = []
    for f in sorted(rdir.rglob("*")):
        if f.is_file():
            try:
                toks = est_tokens(f.read_text())
            except (UnicodeDecodeError, OSError):
                continue   # binary resource — token cost n/a
            if toks > limit:
                out.append(Finding("progressive-disclosure", "warn",
                                   f"resource ~{toks} tokens (>{limit}) — "
                                   "consider splitting so agents load only "
                                   "what they need", str(f.relative_to(vdir))))
    return out


def _check_principles(lab: Lab, vdir: Path) -> list[Finding]:
    """Apply machine-checkable `lint` rules from promoted principles.

    Principle frontmatter may carry rules like:
        lint:
          - field: description        # description | body | entry
            pattern: 'use when'
            negate: true              # finding when pattern does NOT match
            severity: warn
            message: "..."
    This is the knowledge feedback loop: confirmed experiment insights lint
    new skills.
    """
    entry = skill_entry_file(vdir)
    out = []
    for p in sorted(lab.principles_dir.glob("*.md")):
        fm, _ = parse_frontmatter(p.read_text())
        pid = fm.get("id", p.stem)
        for rule in fm.get("lint") or []:
            field = rule.get("field", "entry")
            if field == "description":
                target = skill_description(vdir)
            elif field == "body":
                _, target = parse_frontmatter(
                    entry.read_text()) if entry else ("", "")
            else:
                target = entry.read_text() if entry else ""
            try:
                hit = bool(re.search(rule.get("pattern", "$^"), target,
                                     re.IGNORECASE))
            except re.error:
                continue   # malformed lint pattern — skip, don't crash
            if hit == bool(rule.get("negate")):
                continue  # no violation
            out.append(Finding(
                "principle-conformance",
                rule.get("severity", "warn"),
                f"{rule.get('message', 'violates principle')} "
                f"(principle: {pid})",
                entry.name if entry else ""))
    return out


def analyze_variant(lab: Lab, skill_id: str, vdir: Path) -> list[Finding]:
    cfg = lab.cfg["analysis"]
    findings: list[Finding] = []
    findings += _check_frontmatter(vdir)
    findings += _check_description(vdir, cfg)
    findings += _check_budget(vdir, cfg)
    findings += _check_dead_links(vdir)
    findings += _check_antipatterns(vdir)
    findings += _check_examples(vdir)
    findings += _check_resource_bloat(vdir, cfg)
    findings += _check_principles(lab, vdir)
    return findings


def analyze_skill(lab: Lab, skill_id: str) -> dict[str, list[Finding]]:
    meta = lab.skill(skill_id)
    return {
        v.id: analyze_variant(lab, skill_id, lab.variant_dir(skill_id, v.id))
        for v in meta.variants
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def analyze_registry_conflicts(lab: Lab) -> list[Finding]:
    """Cheap trigger-conflict proxy: jaccard overlap between descriptions."""
    threshold = lab.cfg["analysis"]["trigger_conflict_threshold"]
    seen: list[tuple[str, set[str]]] = []
    for meta in lab.skills():
        for v in meta.variants:
            vdir = lab.variant_dir(meta.id, v.id)
            seen.append((f"{meta.id}@{v.id}", _tokens(skill_description(vdir))))
    out = []
    for i in range(len(seen)):
        for j in range(i + 1, len(seen)):
            (id_a, ta), (id_b, tb) = seen[i], seen[j]
            if id_a.split("@")[0] == id_b.split("@")[0]:
                continue  # variants of same skill aren't contending in the wild
            sim = _jaccard(ta, tb)
            if sim >= threshold:
                out.append(Finding(
                    "trigger-conflict", "warn",
                    f"descriptions of '{id_a}' and '{id_b}' overlap "
                    f"(jaccard={sim:.2f}) — agents may mispick"))
    return out
