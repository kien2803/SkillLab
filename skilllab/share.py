"""Pack export/import: share insights, principles and tasks between labs.

A pack is a plain directory with a manifest — git-friendly, reviewable,
importable by anyone running skilllab.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from .lab import Lab, LabError
from .models import dump_yaml, load_yaml

PACK_KIND = "skilllab-pack"


def export_pack(lab: Lab, out: Path, include_tasks: bool = False) -> Path:
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        raise LabError(f"{out} exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": PACK_KIND,
        "version": 1,
        "created": date.today().isoformat(),
        "contents": [],
    }
    for d in (["insights", "principles"]
              + (["tasks"] if include_tasks else [])):
        src = lab.d(d)
        if not src.is_dir():
            continue
        files = [p for p in src.rglob("*") if p.is_file()
                 and p.name != ".gitkeep"]
        if not files:
            continue
        shutil.copytree(src, out / d, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".gitkeep"))
        manifest["contents"].append(d)
    dump_yaml(manifest, out / "pack.yaml")
    return out


def import_pack(lab: Lab, src: Path, force: bool = False) -> dict[str, int]:
    src = src.resolve()
    manifest = load_yaml(src / "pack.yaml")
    if manifest.get("kind") != PACK_KIND:
        raise LabError(f"{src} is not a skilllab pack (no pack.yaml)")
    counts: dict[str, int] = {}
    skipped: list[str] = []
    for d in manifest.get("contents", []):
        n = 0
        for p in (src / d).rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(src / d)
            dest = lab.d(d) / rel
            if dest.exists() and not force:
                skipped.append(str(dest.relative_to(lab.root)))
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
            n += 1
        counts[d] = n
    if skipped:
        print(f"skipped {len(skipped)} existing file(s) (use --force to "
              "overwrite):")
        for s in skipped:
            print(f"  {s}")
    return counts
