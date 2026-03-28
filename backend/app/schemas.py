from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PipelineStatusLiteral = Literal["idle", "running", "completed", "failed"]


class TopicSummary(BaseModel):
    game: str
    version: str
    target: str
    display_name: str
    target_aliases: list[str] = Field(default_factory=list)


class MetricCard(BaseModel):
    key: str
    label: str
    value: str


class NamedCount(BaseModel):
    name: str
    count: int


class ChartAsset(BaseModel):
    filename: str
    title: str
    url: str


class DashboardResponse(BaseModel):
    topic: TopicSummary
    metrics: list[MetricCard]
    sentiment_counts: list[NamedCount]
    label_source_counts: list[NamedCount]
    top_modules: list[NamedCount]
    charts: list[ChartAsset]
    data_mode: Literal["analysis", "demo"] = "analysis"
    data_source_label: str = ""


class InsightReportResponse(BaseModel):
    markdown: str
    deterministic_markdown: str = ""
    llm_commentary_markdown: str = ""
    llm_commentary_available: bool = False
    llm_commentary_status: Literal["missing", "available", "failed"] = "missing"


class ReviewQueueRow(BaseModel):
    comment_id: str
    priority: str
    review_reason: str
    sentiment: str | None = None
    module_tags: str | None = None
    is_target_related: bool | None = None
    content_clean: str | None = None
    summary_reason: str | None = None


class ReviewQueueResponse(BaseModel):
    total: int
    items: list[ReviewQueueRow]


class CommentsResponse(BaseModel):
    total: int
    items: list[dict]


class PipelineRunRequest(BaseModel):
    task: str = "full_pipeline_report"


class PipelineRunResponse(BaseModel):
    status: PipelineStatusLiteral
    task: str
    pid: int | None = None
    log_path: str | None = None
    message: str


class PipelineStatusResponse(BaseModel):
    status: PipelineStatusLiteral
    task: str | None = None
    pid: int | None = None
    return_code: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    log_path: str | None = None
    log_tail: list[str] = Field(default_factory=list)
