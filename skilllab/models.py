"""Pydantic schemas for all lab artifacts + YAML/frontmatter helpers."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator


# ---------- helpers ----------

def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def dump_yaml(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Empty dict if none."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = yaml.safe_load(m.group(1)) or {}
    return fm, text[m.end():]


def dir_hash(path: Path) -> str:
    """Content hash over all files under a directory."""
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(path)).encode())
            h.update(p.read_bytes())
    return "sha256:" + h.hexdigest()[:16]


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def parse_skill_ref(ref: str) -> tuple[str, Optional[str]]:
    """'id@variant' -> (id, variant); 'id' -> (id, None)."""
    if "@" in ref:
        sid, vid = ref.split("@", 1)
        return sid, vid
    return ref, None


# ---------- skill ----------

SkillKind = Literal["skill-md", "prompt-fragment", "system-prompt", "tool-desc"]
SkillStatus = Literal["draft", "testing", "graduated", "archived"]


class Variant(BaseModel):
    id: str
    path: str          # relative to skill dir, e.g. "variants/v1"
    note: str = ""


class SkillMeta(BaseModel):
    id: str
    kind: SkillKind = "skill-md"
    status: SkillStatus = "draft"
    tags: list[str] = Field(default_factory=list)
    variants: list[Variant] = Field(default_factory=list)

    @classmethod
    def load(cls, skill_dir: Path) -> "SkillMeta":
        return cls(**load_yaml(skill_dir / "skill.yaml"))

    def save(self, skill_dir: Path) -> None:
        dump_yaml(self.model_dump(mode="json"), skill_dir / "skill.yaml")


# ---------- task ----------

TaskKind = Literal["performance", "activation-positive", "activation-negative"]


class Check(BaseModel):
    type: Literal["command", "file-exists", "script"]
    command: Optional[str] = None   # for type=command
    path: Optional[str] = None      # for type=file-exists / script
    id: Optional[str] = None        # name used by rubric criteria

    def name(self) -> str:
        return self.id or self.command or self.path or self.type


class SkillRelevance(BaseModel):
    expected: list[str] = Field(default_factory=list)
    unexpected: list[str] = Field(default_factory=list)


class TaskSpec(BaseModel):
    id: str
    kind: TaskKind = "performance"
    prompt: str = ""                 # inline text or path (relative to task dir) to a .md file
    fixtures: list[str] = Field(default_factory=list)
    skill_relevance: SkillRelevance = Field(default_factory=SkillRelevance)
    rubric: Optional[str] = None
    deterministic_checks: list[Check] = Field(default_factory=list)

    @classmethod
    def load(cls, task_dir: Path) -> "TaskSpec":
        return cls(**load_yaml(task_dir / "task.yaml"))

    def resolve_prompt(self, task_dir: Path) -> str:
        p = task_dir / self.prompt
        if self.prompt and p.is_file():
            return p.read_text()
        return self.prompt


# ---------- rubric ----------

class Criterion(BaseModel):
    id: str
    weight: float = 1.0
    method: Literal["deterministic", "llm-judge", "human"] = "deterministic"
    check: Optional[str] = None        # id of a deterministic_check in the task
    judge_prompt: Optional[str] = None # inline or path relative to rubric file
    scale: str = "1-5"


class Rubric(BaseModel):
    id: str
    criteria: list[Criterion] = Field(default_factory=list)


# ---------- experiment ----------

InjectionMode = Literal["available", "injected"]
IndependentVar = Literal["skill_variant", "model", "injection_mode", "harness"]


class FixedConfig(BaseModel):
    model: str = "mock"
    temperature: float = 0.0
    seed_policy: Literal["fixed", "varied"] = "varied"
    harness: str = "standard-tools-v1"
    injection_mode: InjectionMode = "available"


class Arm(BaseModel):
    name: str
    skill: Optional[str] = None        # "skill-id@variant-id" | "skill-id" | null
    model: Optional[str] = None        # only meaningful when independent_var=model
    injection_mode: Optional[InjectionMode] = None


class Experiment(BaseModel):
    id: str
    title: str = ""
    hypothesis: str = ""
    independent_var: IndependentVar = "skill_variant"
    fixed: FixedConfig = Field(default_factory=FixedConfig)
    arms: list[Arm] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    rollouts_per_arm: int = 5
    metrics: list[str] = Field(default_factory=lambda: [
        "activation_rate", "false_activation", "rubric_score",
        "token_cost", "turns", "outcome_variance",
    ])
    status: Literal["designed", "running", "analyzed", "concluded"] = "designed"
    conclusion: Optional[str] = None
    insights_generated: list[str] = Field(default_factory=list)

    @classmethod
    def load(cls, exp_dir: Path) -> "Experiment":
        return cls(**load_yaml(exp_dir / "experiment.yaml"))

    def save(self, exp_dir: Path) -> None:
        dump_yaml(self.model_dump(mode="json"), exp_dir / "experiment.yaml")

    @model_validator(mode="after")
    def _check_arms(self) -> "Experiment":
        if not self.arms:
            raise ValueError("experiment needs at least one arm")
        names = [a.name for a in self.arms]
        if len(names) != len(set(names)):
            raise ValueError("arm names must be unique")
        return self


# ---------- run ----------

class SkillEvent(BaseModel):
    t: int                             # turn index
    event: Literal["offered", "activated", "resource_read"]
    skill: Optional[str] = None
    path: Optional[str] = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    turns: int = 0


class RunRecord(BaseModel):
    run_id: str
    experiment: str
    arm: str
    task: str
    model: dict = Field(default_factory=dict)
    seed: int = 0
    injection_mode: InjectionMode = "available"
    skill_ref: Optional[str] = None
    skill_hash: Optional[str] = None
    status: Literal["ok", "error"] = "ok"
    error: Optional[str] = None
    started: str = ""
    finished: str = ""
    usage: Usage = Field(default_factory=Usage)
    skill_events: list[SkillEvent] = Field(default_factory=list)
    final_message: str = ""

    def activated(self, skill_id: str) -> bool:
        return any(e.event == "activated" and e.skill == skill_id
                   for e in self.skill_events)


# ---------- eval ----------

class CheckResult(BaseModel):
    id: str
    method: Literal["deterministic", "llm-judge", "human"]
    passed: Optional[bool] = None      # None = pending (human) / error
    score: Optional[float] = None
    detail: str = ""


class EvalResult(BaseModel):
    checks: list[CheckResult] = Field(default_factory=list)
    rubric_score: Optional[float] = None
    success: bool = False
