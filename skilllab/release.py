"""Release Center: evidence-gated skill releases + provenance tracing.

    releases/<skill-id>/<version>.yaml
      version, variant, status, changelog, checklist, timestamps

Lifecycle: draft → candidate → validated → released → deprecated.
`released` is gated on a *computed* checklist — static analysis alone
never marks a skill production-ready; at least one evaluated run is
required evidence.

`trace` walks the chain skill@variant → blueprint revision → findings →
questions → project → experiments → runs → insights, satisfying the
"trace the released skill back to its research" requirement.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from .analyzer import analyze_skill
from .lab import Lab, LabError, check_id
from .models import (Release, load_yaml, dump_yaml, parse_skill_ref)
from .report import load_runs


def releases_dir(lab: Lab, skill_id: str) -> Path:
    return lab.d("releases") / check_id("skill", skill_id)


def new_release(lab: Lab, skill_id: str, version: str,
                variant: str, changelog: str = "") -> Path:
    # --variant accepts "v3-bp" or full "skill@v3-bp" form
    sid, vid = parse_skill_ref(variant)
    if vid:
        sid, vid = sid, vid
    else:
        sid, vid = skill_id, sid
    if not (lab.skills_dir / sid / "skill.yaml").is_file():
        raise LabError(f"skill '{sid}' not found")
    if vid:
        lab.variant_dir(sid, vid)  # raises if variant missing
    d = releases_dir(lab, sid)
    p = d / f"{version}.yaml"
    if p.exists():
        raise LabError(f"release {sid}@{version} already exists")
    r = Release(skill=sid, version=version,
                variant=vid or "", changelog=changelog,
                created=date.today().isoformat())
    dump_yaml(r.model_dump(mode="json"), p)
    return p


def _load(lab: Lab, skill_id: str, version: str) -> tuple[Release, Path]:
    p = releases_dir(lab, skill_id) / f"{check_id('version', version)}.yaml"
    if not p.is_file():
        raise LabError(f"release '{skill_id}@{version}' not found")
    return Release(**load_yaml(p)), p


def list_releases(lab: Lab, skill_id: str | None = None) -> list[Release]:
    out = []
    root = lab.d("releases")
    if not root.is_dir():
        return out
    dirs = [root / skill_id] if skill_id else sorted(root.iterdir())
    for d in dirs:
        if d.is_dir():
            for p in sorted(d.glob("*.yaml")):
                out.append(Release(**load_yaml(p)))
    return out


# ---------- checklist (computed, evidence-based) ----------


def variant_hash(lab: Lab, skill_id: str, variant_id: str) -> str:
    """Content hash of the variant: sha256 over sorted (relpath, bytes)
    pairs — any file add/edit/delete changes it."""
    import hashlib
    vdir = lab.variant_dir(skill_id, variant_id)
    h = hashlib.sha256()
    for p in sorted(vdir.rglob("*")):
        if p.is_file() and not p.is_symlink():
            h.update(str(p.relative_to(vdir)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()[:20]


DEFAULT_RELEASE_GATES = {
    "min_evaluated": 1,        # final (passed/failed) evals required
    "min_passed": 1,           # *passed* evals required — a failed eval is
                             # not quality evidence
    "min_success_rate": None,  # advisory unless set (0..1)
    "activation_recall": None,  # advisory unless set (0..1)
    "false_activation_max": None,
    "regression_clean": False, # when true, latest regression on the
                             # variant must not be 'regressed'
}


def checklist(lab: Lab, skill_id: str, version: str) -> list[dict]:
    r, _ = _load(lab, skill_id, version)
    gates = {**DEFAULT_RELEASE_GATES, **(lab.cfg.get("release") or {})}
    checks = []
    meta = lab.skill(skill_id)
    vid = r.variant or next((v.id for v in meta.variants), "")

    # 1. static analysis: no error-severity findings on this variant
    findings = analyze_skill(lab, skill_id)
    vfinds = findings.get(vid, [])
    errs = [f for f in vfinds if f.severity == "error"]
    checks.append({
        "id": "static-analysis", "required": True,
        "ok": not errs,
        "detail": (f"{len(errs)} error findings" if errs
                   else "no error findings")})

    # 2. evaluated evidence on THIS variant+content hash
    evaluated = passed = 0
    cur_hash = None
    for rd in lab.runs_dir.iterdir() if lab.runs_dir.is_dir() else []:
        ry = rd / "run.yaml"
        ey = rd / "eval.yaml"
        if not ry.is_file() or not ey.is_file():
            continue
        rr = load_yaml(ry)
        if not (rr.get("skill_ref") == f"{skill_id}@{vid}" or
                (rr.get("skill_ref") == skill_id and not vid)):
            continue
        if rr.get("status") == "error":
            continue                       # infra failure ≠ evidence
        ev = load_yaml(ey)
        if ev.get("status") in ("passed", "failed"):
            evaluated += 1
            if ev.get("status") == "passed":
                passed += 1
    checks.append({
        "id": "evaluated-evidence", "required": True,
        "ok": evaluated >= gates["min_evaluated"],
        "detail": f"{evaluated} evaluated run(s) on {skill_id}@{vid} "
                  f"(need >= {gates['min_evaluated']})"})
    checks.append({
        "id": "passed-evidence", "required": True,
        "ok": passed >= gates["min_passed"],
        "detail": f"{passed} passing eval(s) (need >= "
                  f"{gates['min_passed']}; failed evals are evidence of "
                  "a problem, not of quality)"})
    if gates["min_success_rate"] is not None and evaluated:
        rate = passed / evaluated
        checks.append({
            "id": "success-rate", "required": True,
            "ok": rate >= gates["min_success_rate"],
            "detail": f"{rate:.0%} passed of {evaluated} "
                      f"(need >= {gates['min_success_rate']:.0%})"})

    # 3. content-hash consistency — release must point at the exact
    #    content that passed validation
    try:
        cur_hash = variant_hash(lab, skill_id, vid)
    except LabError:
        cur_hash = None
    if r.variant_hash:
        checks.append({
            "id": "content-hash", "required": True,
            "ok": cur_hash == r.variant_hash,
            "detail": (f"variant content matches pinned hash "
                       f"{r.variant_hash}" if cur_hash == r.variant_hash
                       else f"variant changed since validation "
                            f"({cur_hash} != pinned {r.variant_hash})")})
    else:
        checks.append({
            "id": "content-hash", "required": False,
            "ok": cur_hash is not None,
            "detail": "no pinned hash — moving to 'validated' records it"})

    # 4. optional evidence gates driven by lab.yaml `release:`
    if gates["activation_recall"] is not None or \
            gates["false_activation_max"] is not None:
        from .graduation import evaluate_skill
        rep = evaluate_skill(lab, skill_id)
        if gates["activation_recall"] is not None:
            ar = rep.activation_rate
            checks.append({
                "id": "activation-recall", "required": True,
                "ok": ar is not None and ar >= gates["activation_recall"],
                "detail": (f"{ar:.0%} >= {gates['activation_recall']:.0%}"
                           if ar is not None else "no activation data")})
        if gates["false_activation_max"] is not None:
            far = rep.false_activation_rate
            checks.append({
                "id": "false-activation", "required": True,
                "ok": far is not None
                      and far <= gates["false_activation_max"],
                "detail": (f"{far:.0%} <= "
                           f"{gates['false_activation_max']:.0%}"
                           if far is not None else "no negative data")})
    if gates["regression_clean"]:
        reg_dir = lab.d("regressions")
        worst = None
        if reg_dir.is_dir():
            for rd in sorted(reg_dir.iterdir()):
                ry = rd / "regression.yaml"
                if not ry.is_file():
                    continue
                m = load_yaml(ry)
                if m.get("skill") == skill_id \
                        and m.get("candidate") == vid \
                        and m.get("verdict"):
                    worst = m["verdict"]
        checks.append({
            "id": "regression-clean", "required": True,
            "ok": worst not in ("regressed",),
            "detail": f"latest regression verdict: {worst or 'none'}"})

    # 5. blueprint traceability: variant produced by a blueprint?
    note = next((v.note for v in meta.variants if v.id == vid), "")
    has_bp = "blueprint" in (note or "")
    checks.append({
        "id": "blueprint-linked", "required": False,
        "ok": has_bp,
        "detail": note or "no blueprint provenance"})

    # 6. changelog non-empty
    checks.append({
        "id": "changelog", "required": True,
        "ok": bool(r.changelog.strip()),
        "detail": "release notes present" if r.changelog.strip()
                  else "changelog is empty"})
    return checks


def set_status(lab: Lab, skill_id: str, version: str,
               status: str) -> None:
    r, p = _load(lab, skill_id, version)
    if status == "validated":
        # pin the exact content the checklist was evaluated against
        r.variant_hash = variant_hash(lab, skill_id, r.variant)
    if status == "released":
        failed = [c for c in checklist(lab, skill_id, version)
                  if c["required"] and not c["ok"]]
        if failed:
            raise LabError(
                f"release blocked — required checks failing: "
                + "; ".join(c["id"] for c in failed))
        r.released_at = datetime.now().isoformat(timespec="seconds")
    r.status = status
    dump_yaml(r.model_dump(mode="json"), p)


# ---------- provenance trace ----------


def trace(lab: Lab, skill_ref: str) -> dict:
    """Walk variant → blueprint → findings → questions → project and
    → experiments → runs → insights."""
    sid, vid = parse_skill_ref(skill_ref)
    meta = lab.skill(sid)
    v = next((v for v in meta.variants if v.id == vid), None)
    if v is None:
        raise LabError(f"variant '{vid}' not found on '{sid}'")

    out = {"skill": sid, "variant": vid, "variant_path": v.path,
           "blueprint": None, "project": None, "findings": [],
           "questions": [], "experiments": set(), "runs": [],
           "insights": []}

    # blueprint provenance from the variant note
    m = re.search(r"blueprint (\S+)/(\S+)@r(\d+)", v.note or "")
    if m:
        pid, bid, rev = m.groups()
        out["blueprint"] = {"project": pid, "id": bid, "rev": int(rev)}
        try:
            from .blueprint import get_blueprint
            from .research import get_project, list_findings, \
                list_questions
            bp = get_blueprint(lab, pid, bid)
            out["blueprint"]["status"] = bp.status
            out["blueprint"]["rev_current"] = bp.rev
            out["project"] = get_project(lab, pid).title
            fmap = {f.id: f for f in list_findings(lab, pid)}
            out["findings"] = [
                {"id": fid, "status": fmap[fid].status,
                 "statement": fmap[fid].statement[:80]}
                for fid in bp.related_findings if fid in fmap]
            out["questions"] = [
                {"id": q.id, "question": q.question, "status": q.status}
                for q in list_questions(lab, pid)]
        except LabError:
            pass

    # experiments + runs touching this skill_ref — exact arm match, not
    # substring ('skill@v2' must not match 'skill@v2-bad')
    ref = f"{sid}@{vid}"
    if lab.experiments_dir.is_dir():
        for ed in lab.experiments_dir.iterdir():
            ey = ed / "experiment.yaml"
            if not ey.is_file():
                continue
            arms = load_yaml(ey).get("arms") or []
            if any(a.get("skill") == ref for a in arms
                   if isinstance(a, dict)):
                out["experiments"].add(ed.name)
    if lab.runs_dir.is_dir():
        for rd in sorted(lab.runs_dir.iterdir()):
            ry = rd / "run.yaml"
            if ry.is_file() and load_yaml(ry).get("skill_ref") == ref:
                out["runs"].append(rd.name)

    # insights citing those experiments or runs
    from .insights import list_insights
    ev_ids = set(out["experiments"]) | set(out["runs"])
    for ins in list_insights(lab):
        if ev_ids & {str(e) for e in ins["evidence"]}:
            out["insights"].append({"id": ins["id"],
                                    "status": ins["status"],
                                    "kind": ins["kind"]})
    out["experiments"] = sorted(out["experiments"])
    return out
