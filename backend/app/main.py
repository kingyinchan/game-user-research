from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import OUTPUT_DIR
from backend.app.schemas import (
    CommentsResponse,
    DashboardResponse,
    InsightReportResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatusResponse,
    ReviewQueueResponse,
    TopicSummary,
)
from backend.app.services.analysis_store import (
    get_comments,
    get_dashboard,
    get_insight_report,
    get_review_queue,
    get_routing_report,
    get_topic_summary,
)
from backend.app.services.pipeline_runner import pipeline_runner


app = FastAPI(
    title="AI Game User Research Studio API",
    version="0.1.0",
    description="Expose analysis artifacts and pipeline controls for the web frontend.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets/charts", StaticFiles(directory=str(OUTPUT_DIR)), name="charts")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/api/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/topic", response_model=TopicSummary)
def read_topic() -> TopicSummary:
    return get_topic_summary()


@app.get("/api/dashboard", response_model=DashboardResponse)
def read_dashboard() -> DashboardResponse:
    return get_dashboard()


@app.get("/api/insight-report", response_model=InsightReportResponse)
def read_insight_report() -> InsightReportResponse:
    return get_insight_report()


@app.get("/api/review-queue", response_model=ReviewQueueResponse)
def read_review_queue(limit: int = Query(default=50, ge=0, le=500)) -> ReviewQueueResponse:
    return get_review_queue(limit=limit)


@app.get("/api/comments", response_model=CommentsResponse)
def read_comments(
    limit: int = Query(default=50, ge=1, le=300),
    sentiment: str | None = Query(default=None),
    label_source: str | None = Query(default=None),
) -> CommentsResponse:
    return get_comments(limit=limit, sentiment=sentiment, label_source=label_source)


@app.get("/api/routing-report")
def read_routing_report() -> dict:
    return get_routing_report()


@app.get("/api/pipeline/status", response_model=PipelineStatusResponse)
def read_pipeline_status() -> PipelineStatusResponse:
    return pipeline_runner.status()


@app.post("/api/pipeline/run", response_model=PipelineRunResponse)
def run_pipeline(request: PipelineRunRequest) -> PipelineRunResponse:
    try:
        return pipeline_runner.start(request.task)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
