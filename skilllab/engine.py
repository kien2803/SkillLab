"""Rollout engine: run an agent on a task under one experiment arm.

Controlled comparison: everything fixed except the independent variable.
Two injection modes (see SPEC §4.2):
- available: only skill name+description appear in the prompt; the agent must
  call read_skill() to load it -> measures trigger quality.
- injected: full skill content in the system prompt -> measures content quality.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .lab import Lab, LabError
from .llm import LLMClient
from .models import (Arm, Experiment, RunRecord, SkillEvent, Usage, dump_yaml,
                     est_tokens, dir_hash, parse_skill_ref)
from .registry import skill_description, skill_entry_file

HARNESS_V1 = """You are an autonomous agent completing a task inside a workspace directory.
Use the provided tools to inspect and modify files. Paths are relative to the
workspace root.

{skills_block}

When the task is complete, reply with a short summary of what you did."""

TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file in the workspace.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Write content to a file in the workspace (overwrites).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List files under a workspace directory.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "default": "."}}}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Run a shell command inside the workspace.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "read_skill",
        "description": "Load a skill's entry file. Use when a listed skill seems relevant to the task.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "read_skill_file",
        "description": "Read a resource file belonging to a skill (e.g. resources/…).",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "path": {"type": "string"}}, "required": ["name", "path"]}}},
]

_CMD_TIMEOUT = 60
_MAX_TOOL_OUTPUT = 8000


def run_in_workspace(lab: Lab, ws: Path, command: str,
                     timeout: int | None = None,
                     stdin_text: str | None = None
                     ) -> subprocess.CompletedProcess:
    """Run a shell command under the lab's execution policy.

    sandbox: bwrap  →  isolated: no network, read-only system, rw workspace.
    sandbox: unsafe →  unrestricted shell in the workspace (explicit opt-in,
                       cwd alone is NOT a security boundary).
    unset/other   →  disabled: fail closed, never silently run unrestricted.
    """
    timeout = timeout or int(lab.cfg.get("command_timeout", _CMD_TIMEOUT))
    mode = lab.cfg.get("sandbox")
    if mode == "bwrap":
        if not shutil.which("bwrap"):
            raise LabError("sandbox=bwrap configured but bwrap not on PATH")
        return subprocess.run(
            ["bwrap", "--unshare-all", "--die-with-parent",
             "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin",
             "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
             "--ro-bind", "/etc", "/etc", "--proc", "/proc", "--dev", "/dev",
             "--tmpfs", "/tmp", "--tmpfs", "/ws",
             "--bind", str(ws), "/ws", "--chdir", "/ws",
             "--", "bash", "-lc", command],
            input=stdin_text, capture_output=True, text=True,
            timeout=timeout)
    if mode == "unsafe":
        return subprocess.run(command, shell=True, cwd=ws, input=stdin_text,
                              capture_output=True, text=True, timeout=timeout)
    raise LabError(
        f"command execution disabled (sandbox={mode!r}) — set "
        "'sandbox: bwrap' for isolated execution or 'sandbox: unsafe' to "
        "explicitly allow unrestricted shell commands")


class _ToolEnv:
    """Executes tool calls sandboxed to the run workspace."""

    def __init__(self, lab: Lab, workspace: Path,
                 offered: dict[str, Path]):
        self.lab = lab
        self.ws = workspace
        self._ws_root = workspace.resolve()
        self.offered = offered            # skill name -> variant dir
        self.events: list[SkillEvent] = []
        self.turn = 0

    def _resolve(self, rel: str) -> Path:
        p = (self.ws / rel).resolve()
        if not p.is_relative_to(self._ws_root):
            raise LabError(f"path escapes workspace: {rel}")
        return p

    def dispatch(self, name: str, args: dict) -> str:
        try:
            return getattr(self, "_tool_" + name)(args)
        except AttributeError:
            return f"error: unknown tool '{name}'"
        except Exception as e:  # noqa: BLE001 - tool errors go back to the agent
            return f"error: {e}"

    # -- tools -------------------------------------------------------------

    def _tool_read_file(self, a: dict) -> str:
        p = self._resolve(a["path"])
        return p.read_text()[:_MAX_TOOL_OUTPUT]

    def _tool_write_file(self, a: dict) -> str:
        p = self._resolve(a["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["content"])
        return f"wrote {a['path']} ({len(a['content'])} bytes)"

    def _tool_list_dir(self, a: dict) -> str:
        p = self._resolve(a.get("path", "."))
        entries = sorted(x.name + ("/" if x.is_dir() else "")
                         for x in p.iterdir())
        return "\n".join(entries) or "(empty)"

    def _tool_run_command(self, a: dict) -> str:
        try:
            r = run_in_workspace(self.lab, self.ws, a["command"])
        except LabError as e:
            return f"error: {e}"
        out = (r.stdout + r.stderr)[:_MAX_TOOL_OUTPUT]
        return f"exit={r.returncode}\n{out}"

    def _tool_read_skill(self, a: dict) -> str:
        name = a["name"]
        vdir = self.offered.get(name)
        if not vdir:
            return f"error: no skill named '{name}' is offered"
        entry = skill_entry_file(vdir)
        self.events.append(SkillEvent(t=self.turn, event="activated",
                                      skill=name))
        return entry.read_text()[:_MAX_TOOL_OUTPUT]

    def _tool_read_skill_file(self, a: dict) -> str:
        name, rel = a["name"], a["path"]
        vdir = self.offered.get(name)
        if not vdir:
            return f"error: no skill named '{name}' is offered"
        p = (vdir / rel).resolve()
        if not p.is_relative_to(vdir.resolve()) or not p.is_file():
            return f"error: resource '{rel}' not found for skill '{name}'"
        self.events.append(SkillEvent(t=self.turn, event="resource_read",
                                      skill=name, path=rel))
        return p.read_text()[:_MAX_TOOL_OUTPUT]


# ------------------------------------------------------------------ engine --

def _skills_block(lab: Lab, exp: Experiment, arm: Arm,
                  mode: str) -> tuple[str, dict[str, Path]]:
    """Return (prompt block, offered skills {name: variant_dir}).

    Skills referenced by ANY arm are the experiment's independent variable —
    an arm with skill=None must not see them, otherwise the control arm
    silently offers the very skill being tested.
    """
    variable_sids = {parse_skill_ref(a.skill)[0] for a in exp.arms if a.skill}
    offered: dict[str, Path] = {}
    arm_sid: Optional[str] = None

    if arm.skill:
        sid, vid = parse_skill_ref(arm.skill)
        offered[sid] = lab.variant_dir(sid, vid)
        arm_sid = sid

    # Non-variable registry skills stay listed at their default variant so
    # the context is realistic.
    if mode == "available":
        for meta in lab.skills():
            if meta.id in variable_sids and meta.id != arm_sid:
                continue
            if meta.id == arm_sid:
                continue  # already offered at the arm's variant
            offered[meta.id] = lab.variant_dir(meta.id, None)
        lines = ["## Available skills",
                 "If a skill below is relevant, load it with `read_skill` "
                 "before relying on it.", ""]
        for sid, vdir in sorted(offered.items()):
            lines.append(f"- {sid}: {skill_description(vdir)}")
        if not offered:
            lines.append("(none)")
        return "\n".join(lines), offered

    # injected mode: arm skill content embedded; others still listed
    lines = []
    if arm_sid:
        entry = skill_entry_file(offered[arm_sid])
        lines += [f"## Active skill: {arm_sid}", "",
                  entry.read_text(), ""]
    others = [(m.id, lab.variant_dir(m.id, None)) for m in lab.skills()
              if m.id != arm_sid and m.id not in variable_sids]
    if others:
        lines.append("## Available skills")
        for sid, vdir in sorted(others):
            lines.append(f"- {sid}: {skill_description(vdir)}")
            offered[sid] = vdir
    return "\n".join(lines) or "(no skills)", offered


def _seed_for(policy: str, *parts: str) -> int:
    if policy == "fixed":
        return 0
    return zlib.crc32("|".join(parts).encode()) % (2**31)


def run_rollout(lab: Lab, exp: Experiment, arm: Arm, task_id: str,
                idx: int, batch: str | None = None,
                overwrite: bool = False) -> RunRecord:
    task = lab.task(task_id)
    task_dir = lab.task_dir(task_id)
    run_id = f"{exp.id}--{arm.name}--{task_id}--r{idx}"
    if batch:
        run_id += f"--{batch}"
    run_dir = lab.runs_dir / run_id
    ws = run_dir / "workspace"
    if run_dir.exists():
        if not overwrite:
            raise LabError(
                f"run '{run_id}' already exists — run history is "
                "append-only (use `lab rerun --batch` for new history or "
                "--force to archive and overwrite)")
        # auditable overwrite: move the old run to archive/, never delete
        dest = (lab.archive_dir / run_id
                / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(run_dir), str(dest))
    ws.mkdir(parents=True)

    for fx in task.fixtures:
        src = task_dir / fx
        if src.is_dir():
            shutil.copytree(src, ws, dirs_exist_ok=True)

    mode = arm.injection_mode or exp.fixed.injection_mode
    model_name = arm.model or exp.fixed.model
    seed = _seed_for(exp.fixed.seed_policy, exp.id, arm.name, task_id,
                     str(idx), batch or "")
    skill_block, offered = _skills_block(lab, exp, arm, mode)
    system = HARNESS_V1.format(skills_block=skill_block)
    prompt = task.resolve_prompt(task_dir)

    rec = RunRecord(
        run_id=run_id, experiment=exp.id, arm=arm.name, task=task_id,
        model={"name": model_name, "temperature": exp.fixed.temperature},
        seed=seed, injection_mode=mode, skill_ref=arm.skill,
        started=datetime.now(timezone.utc).isoformat())
    for sid in offered:
        rec.skill_events.append(SkillEvent(t=0, event="offered", skill=sid))
    if arm.skill:
        sid, vid = parse_skill_ref(arm.skill)
        rec.skill_hash = dir_hash(lab.variant_dir(sid, vid))

    client = LLMClient(
        model_name, exp.fixed.temperature,
        seed if not client_is_mock(model_name) else None,
        timeout=float(lab.cfg.get("llm_timeout", 120)),
        max_retries=int(lab.cfg.get("llm_retries", 3)),
        cwd=str(ws),
        # external `cmd:` drivers run under the SAME sandbox policy —
        # they cannot bypass the configured execution security
        cmd_runner=lambda c, t, i: run_in_workspace(
            lab, ws, c, timeout=t, stdin_text=i))
    env = _ToolEnv(lab, ws, offered)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    transcript = run_dir / "transcript.jsonl"

    def log(m: dict) -> None:
        with transcript.open("a") as f:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    for m in messages:
        log(m)
    try:
        max_turns = int(lab.cfg.get("max_turns", 15))
        for turn in range(1, max_turns + 1):
            env.turn = turn
            reply = client.complete(messages, TOOLS)
            asst: dict = {"role": "assistant", "content": reply.content}
            if reply.input_tokens or reply.output_tokens:
                asst["usage"] = {"input": reply.input_tokens,
                                 "output": reply.output_tokens}
            if reply.tool_calls:
                asst["tool_calls"] = [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name,
                                  "arguments": json.dumps(c.arguments)}}
                    for c in reply.tool_calls]
            messages.append(asst)
            log(asst)
            rec.usage.input_tokens += reply.input_tokens
            rec.usage.output_tokens += reply.output_tokens
            rec.usage.turns = turn
            rec.final_message = reply.content or rec.final_message
            if not reply.tool_calls:
                break
            for c in reply.tool_calls:
                result = env.dispatch(c.name, c.arguments)
                tm = {"role": "tool", "tool_call_id": c.id, "name": c.name,
                      "content": result}
                messages.append(tm)
                log(tm)
        rec.skill_events += env.events
    except Exception as e:  # noqa: BLE001 - record the failure, don't crash batch
        rec.status = "error"
        rec.error = f"{type(e).__name__}: {e}"
    if client.is_mock:  # mock reports no usage — estimate so reports aren't empty
        rec.usage.input_tokens = est_tokens(
            system + prompt + json.dumps(messages[-2:]))
        rec.usage.output_tokens = est_tokens(rec.final_message or "done")
    rec.finished = datetime.now(timezone.utc).isoformat()
    dump_yaml(rec.model_dump(mode="json"), run_dir / "run.yaml")
    return rec


def client_is_mock(model: str) -> bool:
    return model == "mock" or model.startswith("mock:")


def run_experiment(lab: Lab, exp_id: str, only_arm: str | None = None,
                   limit: int | None = None, batch: str | None = None,
                   overwrite: bool = False) -> list[RunRecord]:
    exp = lab.experiment(exp_id)
    records: list[RunRecord] = []
    for arm in exp.arms:
        if only_arm and arm.name != only_arm:
            continue
        for task_id in exp.tasks:
            n = exp.rollouts_per_arm
            if limit:
                n = min(n, limit)
            for i in range(n):
                records.append(run_rollout(lab, exp, arm, task_id, i, batch,
                                           overwrite=overwrite))
    return records


def planned_run_ids(exp: Experiment, arm_filter: str | None = None,
                    limit: int | None = None,
                    batch: str | None = None) -> list[str]:
    """Run ids a `lab run`/`rerun` invocation would produce."""
    ids = []
    for arm in exp.arms:
        if arm_filter and arm.name != arm_filter:
            continue
        for tid in exp.tasks:
            n = exp.rollouts_per_arm
            if limit:
                n = min(n, limit)
            for i in range(n):
                rid = f"{exp.id}--{arm.name}--{tid}--r{i}"
                if batch:
                    rid += f"--{batch}"
                ids.append(rid)
    return ids


_ID_RE = re.compile(r"[A-Za-z0-9._-]+")


def validate_experiment(lab: Lab, exp: Experiment) -> tuple[list[str],
                                                          list[str]]:
    """Pre-flight checks before running. Returns (errors, warnings).

    Enforces the one-independent-variable rule: arms may only differ on the
    dimension declared by `independent_var`. All referenced tasks, skills,
    variants, rubrics and fixtures must resolve before any run dir or LLM
    call happens.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not _ID_RE.fullmatch(exp.id):
        errors.append(f"invalid experiment id {exp.id!r} "
                      "(allowed: [A-Za-z0-9._-])")
    if exp.independent_var == "harness":
        errors.append("independent_var=harness is not supported — only "
                      "harness 'standard-tools-v1' exists")
    if exp.rollouts_per_arm < 1:
        errors.append("rollouts_per_arm must be >= 1")
    if not exp.tasks:
        errors.append("no tasks listed")
    elif len(set(exp.tasks)) != len(exp.tasks):
        errors.append("duplicate task ids in experiment")
    if not str(exp.fixed.model or "").strip():
        errors.append("fixed.model is empty")
    if not 0.0 <= exp.fixed.temperature <= 2.0:
        errors.append(f"temperature must be in [0, 2] "
                      f"(got {exp.fixed.temperature})")
    if not exp.hypothesis.strip():
        warnings.append("empty hypothesis — a falsifiable claim keeps the "
                        "experiment honest")
    for a in exp.arms:
        if not _ID_RE.fullmatch(a.name):
            errors.append(f"invalid arm name {a.name!r} "
                          "(allowed: [A-Za-z0-9._-])")
        if a.skill:
            sid, vid = parse_skill_ref(a.skill)
            try:
                lab.variant_dir(sid, vid)
            except LabError as e:
                errors.append(f"arm '{a.name}': {e}")
    for tid in dict.fromkeys(exp.tasks):
        try:
            t = lab.task(tid)
        except LabError as e:
            errors.append(str(e))
            continue
        if t.rubric:
            try:
                lab.rubric(t.rubric)
            except LabError as e:
                errors.append(f"task '{tid}': {e}")
        tdir = lab.task_dir(tid)
        for fx in t.fixtures:
            if not (tdir / fx).exists():
                errors.append(f"task '{tid}': missing fixture '{fx}'")
    dims = {
        "skill_variant": {a.skill for a in exp.arms},
        "model": {a.model or exp.fixed.model for a in exp.arms},
        "injection_mode": {a.injection_mode or exp.fixed.injection_mode
                           for a in exp.arms},
    }
    for dim, vals in dims.items():
        if dim == exp.independent_var:
            if len(vals) < 2:
                errors.append(f"independent_var={dim} but all arms have the "
                              f"same {dim}")
        elif len(vals) > 1:
            errors.append(f"arms differ in '{dim}' but independent_var="
                          f"{exp.independent_var} — controlled comparison "
                          "allows one variable only")
    if exp.independent_var == "skill_variant" and not any(
            a.skill is None for a in exp.arms):
        warnings.append("no control arm (skill: null) — delta_vs_control "
                        "will be skipped")
    return errors, warnings
