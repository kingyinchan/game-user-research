from __future__ import annotations

import json
from collections import Counter

import pandas as pd
import yaml

from backend.app.config import (
    CHART_TITLES,
    INSIGHT_REPORT_PATH,
    LABELED_COMMENTS_PATH,
    OUTPUT_DIR,
    PROJECT_CONFIG_PATH,
    REVIEW_QUEUE_PATH,
    ROUTING_REPORT_PATH,
)
from backend.app.schemas import (
    ChartAsset,
    CommentsResponse,
    DashboardResponse,
    InsightReportResponse,
    MetricCard,
    NamedCount,
    ReviewQueueResponse,
    ReviewQueueRow,
    TopicSummary,
)


def _load_project_config() -> dict:
    if not PROJECT_CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(PROJECT_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _load_labeled_comments() -> pd.DataFrame:
    if not LABELED_COMMENTS_PATH.exists():
        return pd.DataFrame()

    df = pd.read_csv(LABELED_COMMENTS_PATH)
    if "comment_id" in df.columns:
        df["comment_id"] = df["comment_id"].astype(str)
    return df


def _split_tags(value: object) -> list[str]:
    if pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    return [tag.strip() for tag in text.split(",") if tag.strip()]


def _named_counts(counter: Counter | dict[str, int]) -> list[NamedCount]:
    return [NamedCount(name=str(name), count=int(count)) for name, count in counter.items()]


def _split_insight_report(markdown: str) -> tuple[str, str]:
    marker = "## LLM Commentary"
    if marker not in markdown:
        return markdown.strip(), ""

    deterministic, llm_section = markdown.split(marker, 1)
    return deterministic.strip(), llm_section.strip()


def get_topic_summary() -> TopicSummary:
    config = _load_project_config()
    topic = config.get("topic", {})
    return TopicSummary(
        game=str(topic.get("game", "")),
        version=str(topic.get("version", "")),
        target=str(topic.get("target", "")),
        display_name=str(topic.get("display_name", topic.get("target", ""))),
        target_aliases=[str(item) for item in topic.get("target_aliases", [])],
    )


def get_chart_assets() -> list[ChartAsset]:
    assets: list[ChartAsset] = []
    for filename, title in CHART_TITLES.items():
        path = OUTPUT_DIR / filename
        if path.exists():
            assets.append(ChartAsset(filename=filename, title=title, url=f"/assets/charts/{filename}"))
    return assets


def get_review_queue(limit: int = 50) -> ReviewQueueResponse:
    if not REVIEW_QUEUE_PATH.exists():
        return ReviewQueueResponse(total=0, items=[])

    df = pd.read_csv(REVIEW_QUEUE_PATH)
    if "comment_id" in df.columns:
        df["comment_id"] = df["comment_id"].astype(str)

    total = len(df)
    if limit > 0:
        df = df.head(limit)

    items = [
        ReviewQueueRow(
            comment_id=str(row.get("comment_id", "")),
            priority=str(row.get("priority", "")),
            review_reason=str(row.get("review_reason", "")),
            sentiment=None if pd.isna(row.get("sentiment")) else str(row.get("sentiment")),
            module_tags=None if pd.isna(row.get("module_tags")) else str(row.get("module_tags")),
            is_target_related=None if pd.isna(row.get("is_target_related")) else bool(row.get("is_target_related")),
            content_clean=None if pd.isna(row.get("content_clean")) else str(row.get("content_clean")),
            summary_reason=None if pd.isna(row.get("summary_reason")) else str(row.get("summary_reason")),
        )
        for _, row in df.iterrows()
    ]
    return ReviewQueueResponse(total=total, items=items)


def get_dashboard() -> DashboardResponse:
    df = _load_labeled_comments()
    topic = get_topic_summary()

    if df.empty:
        return DashboardResponse(
            topic=topic,
            metrics=[],
            sentiment_counts=[],
            label_source_counts=[],
            top_modules=[],
            charts=get_chart_assets(),
        )

    labeled_df = df[df["sentiment"].notna()].copy()
    negative_df = labeled_df[labeled_df["sentiment"].isin(["negative", "mixed"])]
    target_df = labeled_df[labeled_df["is_target_related"].fillna(False).astype(bool)]
    target_negative_df = target_df[target_df["sentiment"].isin(["negative", "mixed"])]
    negative_ratio = (len(negative_df) / len(labeled_df)) if len(labeled_df) else 0
    review_total = get_review_queue(limit=0).total

    metrics = [
        MetricCard(key="total_comments", label="总评论数", value=str(len(df))),
        MetricCard(key="labeled_comments", label="有效标注", value=str(len(labeled_df))),
        MetricCard(key="negative_ratio", label="负向占比", value=f"{negative_ratio:.1%}"),
        MetricCard(key="target_related_comments", label="目标相关", value=str(len(target_df))),
        MetricCard(key="target_negative_comments", label="目标负向", value=str(len(target_negative_df))),
        MetricCard(key="review_queue", label="复核队列", value=str(review_total)),
    ]

    sentiment_counter = Counter(labeled_df["sentiment"].astype(str))
    source_counter = Counter(labeled_df["label_source"].fillna("unknown").astype(str))
    module_counter: Counter[str] = Counter()
    for value in negative_df["module_tags"]:
        for tag in _split_tags(value):
            module_counter[tag] += 1

    return DashboardResponse(
        topic=topic,
        metrics=metrics,
        sentiment_counts=_named_counts(sentiment_counter),
        label_source_counts=_named_counts(source_counter),
        top_modules=_named_counts(dict(module_counter.most_common(8))),
        charts=get_chart_assets(),
    )


def get_insight_report() -> InsightReportResponse:
    markdown = INSIGHT_REPORT_PATH.read_text(encoding="utf-8") if INSIGHT_REPORT_PATH.exists() else ""
    deterministic_markdown, llm_commentary_markdown = _split_insight_report(markdown)
    llm_commentary_available = bool(llm_commentary_markdown)
    llm_commentary_status = "missing"
    if llm_commentary_available:
        llm_commentary_status = "failed" if llm_commentary_markdown.startswith("_LLM ???????") else "available"
    return InsightReportResponse(
        markdown=markdown,
        deterministic_markdown=deterministic_markdown,
        llm_commentary_markdown=llm_commentary_markdown,
        llm_commentary_available=llm_commentary_available,
        llm_commentary_status=llm_commentary_status,
    )


def get_comments(limit: int = 50, sentiment: str | None = None, label_source: str | None = None) -> CommentsResponse:
    df = _load_labeled_comments()
    if df.empty:
        return CommentsResponse(total=0, items=[])

    labeled_df = df[df["sentiment"].notna()].copy()
    if sentiment:
        labeled_df = labeled_df[labeled_df["sentiment"] == sentiment]
    if label_source:
        labeled_df = labeled_df[labeled_df["label_source"] == label_source]

    total = len(labeled_df)
    preview = labeled_df.head(limit).fillna("")
    return CommentsResponse(total=total, items=preview.to_dict(orient="records"))


def get_routing_report() -> dict:
    if not ROUTING_REPORT_PATH.exists():
        return {}
    return json.loads(ROUTING_REPORT_PATH.read_text(encoding="utf-8"))
