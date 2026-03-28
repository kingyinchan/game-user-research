from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceRecord(BaseModel):
    source_path: str
    row_id: str | None = None
    excerpt: str | None = None


class TaskFinding(BaseModel):
    severity: Literal["info", "warning", "critical"] = "info"
    title: str
    detail: str
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    task_name: str
    status: Literal["success", "skipped", "failed"] = "success"
    summary: str
    findings: list[TaskFinding] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class RunManifest(BaseModel):
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z")
    topic_name: str
    tasks: list[TaskResult]
