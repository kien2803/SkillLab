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
    type: Literal["command", "file-exists", "script", "file-content",
                  "json"]
    command: Optional[str] = None   # for type=command
    path: Optional[str] = None      # for file-exists / script / file-content / json
    id: Optional[str] = None        # name used by rubric criteria
    contains: Optional[str] = None  # file-content: literal substring required
    regex: Optional[str] = None     # file-content: pattern that must match
    equals: Optional[str] = None    # file-content: whole-file comparison
    keys: list[str] = Field(default_factory=list)   # json: required top-level keys
    field: Optional[str] = None     # json: dotted path to compare
    value: Optional[str] = None     # json: expected scalar for `field`

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
ExpCategory = Literal[
    "capability", "trigger", "workflow", "instruction", "resource",
    "tool-use", "compatibility", "reliability", "efficiency",
]


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
    category: Optional[ExpCategory] = None
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

CheckStatus = Literal["pending", "passed", "failed", "error"]
EvalStatus = Literal["pending", "passed", "failed", "error"]


class CheckResult(BaseModel):
    id: str
    method: Literal["deterministic", "llm-judge", "human"]
    passed: Optional[bool] = None      # legacy field — synced with status
    status: Optional[CheckStatus] = None  # None derives from `passed`
    score: Optional[float] = None
    detail: str = ""
    judge_model: Optional[str] = None   # provenance for llm-judge criteria

    @model_validator(mode="after")
    def _sync_status(self) -> "CheckResult":
        """Keep `status` and `passed` consistent (old eval.yaml has no status)."""
        if self.status is None:
            self.status = ("pending" if self.passed is None
                           else ("passed" if self.passed else "failed"))
        elif self.passed is None:
            self.passed = {"passed": True, "failed": False}.get(self.status)
        return self


class EvalResult(BaseModel):
    checks: list[CheckResult] = Field(default_factory=list)
    rubric_score: Optional[float] = None
    success: bool = False
    status: Optional[EvalStatus] = None   # pending | passed | failed | error
    evaluated_at: Optional[str] = None    # ISO timestamp (provenance)

    @model_validator(mode="after")
    def _sync_status(self) -> "EvalResult":
        """Derive missing status from checks/success — old eval.yaml files
        predate the lifecycle and only carry `success`."""
        if self.status is None:
            states = {c.status for c in self.checks}
            for s in ("error", "pending", "failed"):
                if s in states:
                    self.status = s
                    break
            else:
                self.status = ("passed" if self.success else
                               ("failed" if states else "error"))
        return self


# ---------- research projects ----------

ProjectStatus = Literal["draft", "active", "researching", "designing",
                        "developing", "experimenting", "validating",
                        "completed", "archived"]


class ProjectMeta(BaseModel):
    id: str
    title: str = ""
    objective: str = ""
    problem: str = ""
    status: ProjectStatus = "draft"
    tags: list[str] = Field(default_factory=list)
    scope: str = ""
    constraints: list[str] = Field(default_factory=list)
    created: str = ""
    updated: str = ""

    @classmethod
    def load(cls, project_dir: Path) -> "ProjectMeta":
        return cls(**load_yaml(project_dir / "project.yaml"))

    def save(self, project_dir: Path) -> None:
        dump_yaml(self.model_dump(mode="json"),
                  project_dir / "project.yaml")


QuestionStatus = Literal["open", "investigating", "answered", "deferred"]


class ResearchQuestion(BaseModel):
    id: str
    question: str = ""
    objective: str = ""
    hypothesis: str = ""
    status: QuestionStatus = "open"
    findings: list[str] = Field(default_factory=list)
    experiments: list[str] = Field(default_factory=list)
    created: str = ""


SourceType = Literal["url", "doc", "note", "paper", "other"]


class ResearchSource(BaseModel):
    id: str
    type: SourceType = "other"
    title: str = ""
    author: str = ""
    url: str = ""
    path: str = ""
    accessed: str = ""
    excerpt: str = ""
    annotations: list[str] = Field(default_factory=list)


FindingKind = Literal["verified-source", "observation", "ai-hypothesis",
                      "unverified"]
FindingStatus = Literal["candidate", "supported", "refuted",
                        "inconclusive"]
FindingConfidence = Literal["low", "medium", "high"]


class ResearchFinding(BaseModel):
    id: str
    statement: str = ""
    kind: FindingKind = "unverified"
    question: str = ""                   # q-id this finding answers
    confidence: FindingConfidence = "low"
    sources: list[str] = Field(default_factory=list)   # s-ids
    evidence: list[str] = Field(default_factory=list)  # exp/run ids
    limitations: str = ""
    status: FindingStatus = "candidate"
    created: str = ""


DecisionStatus = Literal["proposed", "accepted", "rejected",
                         "superseded"]


class ResearchDecision(BaseModel):
    id: str
    decision: str = ""
    rationale: str = ""
    alternatives: list[str] = Field(default_factory=list)
    status: DecisionStatus = "proposed"
    created: str = ""


# ---------- skill blueprints ----------

BlueprintStatus = Literal["draft", "designing", "ready_for_generation",
                          "generated", "testing", "improving",
                          "validated", "released", "archived"]


class Blueprint(BaseModel):
    """Structured spec bridging research findings and a skill draft.

    `fields` holds the 23 spec sections (see blueprint.FIELDS); every
    save bumps `rev` and snapshots the prior revision."""
    id: str
    title: str = ""
    status: BlueprintStatus = "draft"
    rev: int = 1
    fields: dict = Field(default_factory=dict)
    related_findings: list[str] = Field(default_factory=list)
    generated_variants: list[str] = Field(default_factory=list)
    created: str = ""
    updated: str = ""


# ---------- releases ----------

ReleaseStatus = Literal["draft", "candidate", "validated", "released",
                        "deprecated"]


class Release(BaseModel):
    skill: str
    version: str
    variant: str = ""
    status: ReleaseStatus = "draft"
    changelog: str = ""
    created: str = ""
    released_at: str = ""


# ---------- architect proposals ----------

ProposalStatus = Literal["pending", "approved", "rejected", "applied"]


class Proposal(BaseModel):
    """An assistant-suggested change: explicit patch + diff preview,
    approval-gated before it touches a skill file."""
    id: str
    skill: str
    variant: str = ""
    finding: str = ""                  # the analyzer finding addressed
    patch: dict = Field(default_factory=dict)   # {type, file, ...}
    diff_preview: str = ""
    status: ProposalStatus = "pending"
    original_content: str = ""         # pre-apply snapshot for rollback
    created: str = ""
    applied_at: str = ""
