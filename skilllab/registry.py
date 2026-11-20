"""Skill registry operations: add/import skills, manage variants, read metadata."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .lab import Lab, LabError
from .models import SkillMeta, Variant, parse_frontmatter

SKILL_MD_TEMPLATE = """---
name: {skill_id}
description: >-
  TODO: when should an agent use this skill? Be specific about trigger
  conditions — name concrete situations, file types, or user phrasings.
---

# {skill_id}

TODO: core instructions go here. Keep this file lean — move reference
material into `resources/` and link to it (progressive disclosure).
"""

_RESOURCES_README = (
    "Put heavyweight reference material here (docs, examples, schemas).\n"
    "SKILL.md should point agents at these files instead of embedding them.\n"
)


def skill_entry_file(variant_dir: Path) -> Path | None:
    """Entry file for a variant (SKILL.md for skill-md kind)."""
    for name in ("SKILL.md", "skill.md", "prompt.md"):
        p = variant_dir / name
        if p.is_file():
            return p
    return None


def skill_description(variant_dir: Path) -> str:
    """Description shown in registry listing — from frontmatter or first line."""
    entry = skill_entry_file(variant_dir)
    if not entry:
        return "(no entry file)"
    fm, body = parse_frontmatter(entry.read_text())
    desc = fm.get("description") or fm.get("desc")
    if desc:
        return " ".join(str(desc).split())
    for line in body.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:200]
    return "(empty description)"


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return s or "skill"


def new_skill(lab: Lab, skill_id: str, kind: str = "skill-md") -> Path:
    skill_id = _slugify(skill_id)
    skill_dir = lab.skills_dir / skill_id
    if skill_dir.exists():
        raise LabError(f"Skill '{skill_id}' already exists.")
    vdir = skill_dir / "variants" / "v1"
    (vdir / "resources").mkdir(parents=True)
    (vdir / "SKILL.md").write_text(SKILL_MD_TEMPLATE.format(skill_id=skill_id))
    (vdir / "resources" / "README.md").write_text(_RESOURCES_README)
    meta = SkillMeta(
        id=skill_id,
        kind=kind,  # type: ignore[arg-type]
        variants=[Variant(id="v1", path="variants/v1", note="initial scaffold")],
    )
    meta.save(skill_dir)
    return skill_dir


GIT_URL_RE = re.compile(r"^(https://|ssh://|git@|git://)")
GIT_TIMEOUT = 180        # seconds; clone is shallow but still capped

# Well-known locations other agents/tools install skills into.
SCAN_DIRS = ("~/.agents/skills", "~/.claude/skills",
             "~/.config/devin/skills", ".agents/skills", ".claude/skills",
             ".config/devin/skills")


def scan_skill_dirs() -> list[Path]:
    """Discover dirs containing a skill entry file in known locations."""
    found = []
    for pat in SCAN_DIRS:
        base = Path(pat).expanduser()
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir() and skill_entry_file(d):
                found.append(d)
    return found


def _fetch_git(url_ref: str) -> tuple[Path, Path]:
    """Shallow-clone `url[#subdir]` into a tempdir. Returns (root, subdir).
    Only approved protocols; credential prompts are disabled and the
    clone is time-boxed; a #subdir must stay inside the clone."""
    url, _, frag = url_ref.partition("#")
    if not GIT_URL_RE.match(url):
        raise LabError(f"git url '{url[:60]}' uses an unapproved protocol "
                       "(allowed: https://, ssh://, git@, git://)")
    tmp = Path(tempfile.mkdtemp(prefix="skilllab-git-"))
    env = {"GIT_TERMINAL_PROMPT": "0", "PATH": __import__("os").environ
           .get("PATH", "")}
    try:
        r = subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch",
             url, str(tmp)],
            capture_output=True, text=True, timeout=GIT_TIMEOUT, env=env)
    except FileNotFoundError as e:
        raise LabError("git is not on PATH — needed for URL imports") from e
    except subprocess.TimeoutExpired as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise LabError(f"git clone timed out for {url}") from e
    if r.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise LabError(f"git clone failed: {r.stderr.strip()[:300]}")
    sub = (tmp / frag).resolve() if frag else tmp
    if frag and (not sub.is_relative_to(tmp.resolve())
                 or not sub.is_dir()):
        shutil.rmtree(tmp, ignore_errors=True)
        raise LabError(f"#subdir '{frag}' escapes the cloned repo")
    return tmp, sub


def _reject_symlinks(src: Path) -> None:
    for p in src.rglob("*"):
        if p.is_symlink():
            raise LabError(f"source contains symlink '{p.name}' — "
                           "refusing to import (could point outside)")


def add_skill(lab: Lab, src: str | Path, variant_id: str | None = None,
              skill_id: str | None = None) -> Path:
    """Import a skill dir (containing SKILL.md) as a new variant.

    `src` may be a local path or a git URL, optionally with `#subdir` to
    import a skill nested inside a repo.
    """
    tmpdir: Path | None = None
    try:
        s = str(src)
        if GIT_URL_RE.match(s):
            tmpdir, src = _fetch_git(s)
        else:
            src = Path(s)
        src = src.resolve()
        entry = skill_entry_file(src)
        if not entry:
            raise LabError(f"No SKILL.md found in {src}")
        _reject_symlinks(src)
        fm, _ = parse_frontmatter(entry.read_text())
        sid = _slugify(skill_id or str(fm.get("name") or src.name))
        skill_dir = lab.skills_dir / sid

        if skill_dir.exists():
            meta = SkillMeta.load(skill_dir)
        else:
            meta = SkillMeta(id=sid)

        vid = variant_id or f"v{len(meta.variants) + 1}"
        if any(v.id == vid for v in meta.variants):
            raise LabError(f"Variant '{vid}' already exists on skill '{sid}'.")
        dest = skill_dir / "variants" / vid
        shutil.copytree(src, dest)
        meta.variants.append(Variant(id=vid, path=f"variants/{vid}",
                                     note="imported"))
        meta.save(skill_dir)
        return skill_dir
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)
