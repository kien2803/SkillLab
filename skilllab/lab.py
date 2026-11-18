"""Lab context: locate lab root, hold config, expose standard paths."""

from __future__ import annotations

from pathlib import Path

from .models import Experiment, Rubric, SkillMeta, TaskSpec, load_yaml

DEFAULT_CONFIG = {
    "model": "mock",
    "judge_model": "mock",
    "temperature": 0.0,
    "rollouts_per_arm": 5,
    "max_turns": 15,
    "sandbox": None,           # "bwrap" for isolated run_command
    "llm_timeout": 120,        # seconds per LLM call (rollout + judge)
    "llm_retries": 3,          # retries on transient API errors
    "analysis": {
        "skill_md_max_lines": 500,
        "skill_md_token_warn": 2000,
        "resource_token_warn": 4000,
        "description_min_chars": 40,
        "description_max_chars": 600,
        "trigger_conflict_threshold": 0.6,
    },
}

DIRS = ["skills", "tasks", "rubrics", "experiments", "runs", "insights", "principles"]


class LabError(Exception):
    pass


class Lab:
    def __init__(self, root: Path):
        self.root = root
        self.cfg = {**DEFAULT_CONFIG, **load_yaml(root / "lab.yaml")}

    # -- paths -------------------------------------------------------------

    def d(self, name: str) -> Path:
        return self.root / name

    @property
    def skills_dir(self) -> Path: return self.d("skills")
    @property
    def tasks_dir(self) -> Path: return self.d("tasks")
    @property
    def rubrics_dir(self) -> Path: return self.d("rubrics")
    @property
    def experiments_dir(self) -> Path: return self.d("experiments")
    @property
    def runs_dir(self) -> Path: return self.d("runs")
    @property
    def insights_dir(self) -> Path: return self.d("insights")
    @property
    def principles_dir(self) -> Path: return self.d("principles")

    # -- discovery ---------------------------------------------------------

    @classmethod
    def find(cls, start: Path | None = None) -> "Lab":
        p = (start or Path.cwd()).resolve()
        for cand in (p, *p.parents):
            if (cand / "lab.yaml").is_file():
                return cls(cand)
        raise LabError("No lab.yaml found — run `lab init` first.")

    @classmethod
    def init(cls, root: Path) -> "Lab":
        root.mkdir(parents=True, exist_ok=True)
        (root / "lab.yaml").write_text(
            "# Skill Lab config\n"
            "model: mock            # rollout model ('mock' = offline simulation)\n"
            "judge_model: mock      # model used for llm-judge criteria\n"
            "temperature: 0.0\n"
            "rollouts_per_arm: 5\n"
            "max_turns: 15\n"
            "llm_timeout: 120      # seconds per LLM call\n"
            "llm_retries: 3        # retries on transient API errors\n"
            "# sandbox: bwrap       # isolate run_command: no network, ro system\n"
        )
        for d in DIRS:
            (root / d).mkdir(exist_ok=True)
            (root / d / ".gitkeep").touch()
        return cls(root)

    # -- loaders -----------------------------------------------------------

    def skills(self) -> list[SkillMeta]:
        out = []
        if self.skills_dir.is_dir():
            for d in sorted(self.skills_dir.iterdir()):
                if (d / "skill.yaml").is_file():
                    out.append(SkillMeta.load(d))
        return out

    def skill(self, skill_id: str) -> SkillMeta:
        d = self.skills_dir / skill_id
        if not (d / "skill.yaml").is_file():
            raise LabError(f"Skill '{skill_id}' not found in registry.")
        return SkillMeta.load(d)

    def variant_dir(self, skill_id: str, variant_id: str | None) -> Path:
        meta = self.skill(skill_id)
        if not meta.variants:
            raise LabError(f"Skill '{skill_id}' has no variants.")
        if variant_id is None:
            return self.skills_dir / skill_id / meta.variants[0].path
        for v in meta.variants:
            if v.id == variant_id:
                return self.skills_dir / skill_id / v.path
        raise LabError(f"Variant '{variant_id}' not found on skill '{skill_id}'.")

    def tasks(self) -> list[TaskSpec]:
        out = []
        if self.tasks_dir.is_dir():
            for d in sorted(self.tasks_dir.iterdir()):
                if (d / "task.yaml").is_file():
                    out.append(TaskSpec.load(d))
        return out

    def task(self, task_id: str) -> TaskSpec:
        d = self.tasks_dir / task_id
        if not (d / "task.yaml").is_file():
            raise LabError(f"Task '{task_id}' not found.")
        return TaskSpec.load(d)

    def task_dir(self, task_id: str) -> Path:
        return self.tasks_dir / task_id

    def rubric(self, rubric_id: str) -> Rubric:
        p = self.rubrics_dir / f"{rubric_id}.yaml"
        if not p.is_file():
            raise LabError(f"Rubric '{rubric_id}' not found.")
        return Rubric(**load_yaml(p))

    def experiment(self, exp_id: str) -> Experiment:
        d = self.experiments_dir / exp_id
        if not (d / "experiment.yaml").is_file():
            raise LabError(f"Experiment '{exp_id}' not found.")
        return Experiment.load(d)

    def exp_dir(self, exp_id: str) -> Path:
        return self.experiments_dir / exp_id
