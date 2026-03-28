from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config import load_project_config

from .llm import LLMService
from .models import TaskResult
from .tools import ensure_parent_dir

TASK_REGISTRY: dict[str, type["AgentTask"]] = {}


class ArtifactStore:
    def __init__(self, artifacts_dir: Path, reports_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.reports_dir = reports_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, task_name: str, filename: str, payload: dict[str, Any]) -> str:
        path = self.artifacts_dir / task_name / filename
        ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return str(path)

    def write_markdown(self, task_name: str, filename: str, content: str) -> str:
        path = self.reports_dir / task_name / filename
        ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(path)

    def write_text(self, task_name: str, filename: str, content: str) -> str:
        path = self.artifacts_dir / task_name / filename
        ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(path)


@dataclass
class AgentContext:
    project_root: Path
    analysis_dir: Path
    config: dict[str, Any]
    topic: dict[str, Any]
    paths: dict[str, Any]
    agent_config: dict[str, Any]
    artifacts: ArtifactStore
    llm: LLMService | None = None

    def resolve_from_analysis(self, relative_path: str, default: str) -> Path:
        target = Path(relative_path or default)
        if target.is_absolute():
            return target
        return (self.analysis_dir / target).resolve()

    @property
    def cleaned_dir(self) -> Path:
        return self.resolve_from_analysis(self.paths.get("cleaned_data", "cleaned_data"), "cleaned_data")

    @property
    def raw_data_dir(self) -> Path:
        return self.resolve_from_analysis(
            self.paths.get("raw_data", "../crawler/MediaCrawler/data/xhs/jsonl"),
            "../crawler/MediaCrawler/data/xhs/jsonl",
        )

    @property
    def output_dir(self) -> Path:
        return self.resolve_from_analysis(self.paths.get("output", "output"), "output")


class AgentTask(ABC):
    name = ""
    description = ""

    @abstractmethod
    def run(self, context: AgentContext) -> TaskResult:
        raise NotImplementedError


def register_task(task_cls: type[AgentTask]) -> type[AgentTask]:
    if not task_cls.name:
        raise ValueError("Registered task must define a non-empty name.")
    TASK_REGISTRY[task_cls.name] = task_cls
    return task_cls


def list_tasks() -> dict[str, type[AgentTask]]:
    return dict(TASK_REGISTRY)


def create_task(name: str) -> AgentTask:
    task_cls = TASK_REGISTRY.get(name)
    if task_cls is None:
        available = ", ".join(sorted(TASK_REGISTRY))
        raise KeyError(f"Unknown task '{name}'. Available tasks: {available}")
    return task_cls()


def build_context(analysis_dir: str | Path | None = None) -> AgentContext:
    analysis_dir = Path(analysis_dir or Path(__file__).resolve().parents[1]).resolve()
    project_root = analysis_dir.parent
    load_dotenv(project_root / ".env")

    config = load_project_config(str(analysis_dir / "config" / "project.yaml"))
    topic = config.get("topic", {})
    paths = config.get("paths", {})
    agent_config = config.get("agents", {})

    artifacts_dir = analysis_dir / agent_config.get("artifacts_dir", "artifacts/agents")
    reports_dir = analysis_dir / agent_config.get("reports_dir", "reports")
    artifact_store = ArtifactStore(artifacts_dir=artifacts_dir, reports_dir=reports_dir)
    llm = LLMService.from_config(agent_config.get("llm", {}))

    return AgentContext(
        project_root=project_root,
        analysis_dir=analysis_dir,
        config=config,
        topic=topic,
        paths=paths,
        agent_config=agent_config,
        artifacts=artifact_store,
        llm=llm,
    )

