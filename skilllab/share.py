"""Pack export/import: share insights, principles and tasks between labs.

A pack is a plain directory with a manifest — git-friendly, reviewable,
importable by anyone running skilllab.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from .lab import Lab, LabError
from .models import TaskSpec, dump_yaml, load_yaml

PACK_KIND = "skilllab-pack"
PACK_VERSION = 1

# Only these directories may travel inside a pack — anything else in a
# manifest is rejected outright (a manifest is untrusted input).
ALLOWED_DIRS = ("insights", "principles", "tasks")


def export_pack(lab: Lab, out: Path, include_tasks: bool = False) -> Path:
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        raise LabError(f"{out} exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": PACK_KIND,
        "version": PACK_VERSION,
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


def import_pack(lab: Lab, src: Path, force: bool = False) -> dict:
    """Import a pack. Returns {"imported": {dir: n}, "skipped": [...],
    "rejected": [...]} — nothing is written unless it passes validation."""
    src = src.resolve()
    manifest = load_yaml(src / "pack.yaml")
    if manifest.get("kind") != PACK_KIND:
        raise LabError(f"{src} is not a skilllab pack (no pack.yaml)")
    if not isinstance(manifest.get("version"), int):
        raise LabError("pack.yaml has no integer 'version'")
    if manifest["version"] > PACK_VERSION:
        raise LabError(f"pack version {manifest['version']} is newer than "
                       f"supported ({PACK_VERSION})")
    contents = manifest.get("contents")
    if not isinstance(contents, list) \
            or not all(isinstance(c, str) for c in contents):
        raise LabError("pack.yaml 'contents' must be a list of dir names")
    bad = [c for c in contents
           if c not in ALLOWED_DIRS or c != Path(c).name]
    if bad:
        raise LabError(f"pack lists unsupported/unsafe entries: "
                       f"{', '.join(bad)}")

    # phase 1 — validate everything, build the apply plan. Nothing is
    # written until every entry has passed its checks.
    res: dict = {"imported": {}, "skipped": [], "rejected": []}
    plan: list[tuple[Path, Path, str]] = []   # (src, dest, dir)
    for d in contents:
        base = src / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(base)
            if p.is_symlink():
                res["rejected"].append(f"{d}/{rel} (symlink)")
                continue
            if not p.is_file():
                continue
            dest = lab.d(d) / rel
            try:
                inside = dest.resolve().is_relative_to(
                    lab.d(d).resolve())
            except OSError:
                inside = False
            if not inside:
                res["rejected"].append(f"{d}/{rel} (path escapes)")
                continue
            if d == "tasks" and p.name == "task.yaml":
                try:
                    TaskSpec(**load_yaml(p))
                except Exception as e:  # noqa: BLE001 - report, don't crash
                    res["rejected"].append(
                        f"{d}/{rel} (invalid task.yaml: {e})")
                    continue
            if dest.exists() and not force:
                res["skipped"].append(str(dest.relative_to(lab.root)))
                continue
            plan.append((p, dest, d))

    # phase 2 — stage every file under a temp name, then commit with
    # os.replace; a mid-apply failure rolls back what was written.
    import os
    staged: list[tuple[Path, Path]] = []       # (tmp, dest)
    applied: list[tuple[Path, bytes | None]] = []  # (dest, old bytes)
    try:
        for p, dest, _d in plan:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".packtmp")
            shutil.copy2(p, tmp)
            staged.append((tmp, dest))
        for tmp, dest in staged:
            old = dest.read_bytes() if dest.exists() else None
            os.replace(tmp, dest)
            applied.append((dest, old))
    except Exception as e:
        for dest, old in applied:
            if old is None:
                dest.unlink(missing_ok=True)
            else:
                dest.write_bytes(old)
        for tmp, _dest in staged:
            tmp.unlink(missing_ok=True)
        raise LabError(f"import failed mid-apply, rolled back: {e}")
    for _p, _dest, d in plan:
        res["imported"][d] = res["imported"].get(d, 0) + 1
    return res
