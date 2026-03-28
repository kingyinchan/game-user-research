from __future__ import annotations

import pandas as pd

from ..framework import AgentContext, AgentTask, register_task
from ..models import EvidenceRecord, TaskFinding, TaskResult
from ..tools import load_csv_if_exists, markdown_table, safe_excerpt


@register_task
class DataQualityReviewTask(AgentTask):
    name = "data_quality_review"
    description = "Review cleaned datasets and surface data quality risks before labeling."

    def run(self, context: AgentContext) -> TaskResult:
        comments_path = context.cleaned_dir / "comments_cleaned.csv"
        contents_path = context.cleaned_dir / "contents_cleaned.csv"

        comments_df = load_csv_if_exists(comments_path)
        if comments_df is None:
            return TaskResult(
                task_name=self.name,
                status="skipped",
                summary=f"Missing cleaned comments file: {comments_path}",
            )

        contents_df = load_csv_if_exists(contents_path)
        thresholds = context.agent_config.get("quality_thresholds", {})
        findings: list[TaskFinding] = []

        total_comments = len(comments_df)
        empty_rate = float(comments_df["is_empty"].fillna(0).mean()) if "is_empty" in comments_df else 0.0
        duplicate_id_count = int(comments_df["comment_id"].duplicated().sum()) if "comment_id" in comments_df else 0
        duplicate_clean_text_count = 0
        duplicate_clean_text_rate = 0.0
        short_comment_rate = 0.0
        orphan_comment_rate = 0.0

        repeated_examples: list[tuple[str, int]] = []
        if "content_clean" in comments_df:
            cleaned = comments_df["content_clean"].fillna("").astype(str).str.strip()
            non_empty = comments_df.loc[cleaned != ""].copy()
            if len(non_empty) > 0:
                duplicate_clean_text_count = int(non_empty.duplicated("content_clean").sum())
                duplicate_clean_text_rate = duplicate_clean_text_count / len(non_empty)
                repeated = non_empty["content_clean"].value_counts()
                repeated = repeated[repeated > 1].head(5)
                repeated_examples = [(safe_excerpt(text), int(count)) for text, count in repeated.items()]

        if "content_clean_length" in comments_df:
            short_comment_rate = float((comments_df["content_clean_length"].fillna(0) <= 3).mean())

        if contents_df is not None and "note_id" in comments_df and "note_id" in contents_df and len(comments_df) > 0:
            orphan_mask = ~comments_df["note_id"].isin(set(contents_df["note_id"]))
            orphan_comment_rate = float(orphan_mask.mean())

        if empty_rate >= float(thresholds.get("empty_comment_rate", 0.10)):
            findings.append(
                TaskFinding(
                    severity="warning",
                    title="Empty comment rate is high",
                    detail=f"{empty_rate:.1%} of cleaned comments are empty after normalization.",
                    evidence=[EvidenceRecord(source_path=str(comments_path))],
                    metrics={"empty_comment_rate": round(empty_rate, 4), "total_comments": total_comments},
                )
            )

        if duplicate_id_count > 0:
            findings.append(
                TaskFinding(
                    severity="critical",
                    title="Duplicate comment_id detected",
                    detail=f"Found {duplicate_id_count} duplicate comment IDs in cleaned comments.",
                    evidence=[EvidenceRecord(source_path=str(comments_path))],
                    metrics={"duplicate_comment_id_count": duplicate_id_count},
                )
            )

        if duplicate_clean_text_rate >= float(thresholds.get("duplicate_clean_text_rate", 0.15)):
            findings.append(
                TaskFinding(
                    severity="warning",
                    title="Repeated cleaned text is concentrated",
                    detail=f"{duplicate_clean_text_rate:.1%} of non-empty comments share duplicate cleaned text.",
                    evidence=[
                        EvidenceRecord(source_path=str(comments_path), excerpt=f"{text} (x{count})")
                        for text, count in repeated_examples[:3]
                    ],
                    metrics={"duplicate_clean_text_rate": round(duplicate_clean_text_rate, 4)},
                )
            )

        if orphan_comment_rate >= float(thresholds.get("orphan_comment_rate", 0.05)):
            findings.append(
                TaskFinding(
                    severity="warning",
                    title="Comments reference missing posts",
                    detail=f"{orphan_comment_rate:.1%} of comments point to note_ids not present in contents_cleaned.csv.",
                    evidence=[
                        EvidenceRecord(source_path=str(comments_path)),
                        EvidenceRecord(source_path=str(contents_path)),
                    ],
                    metrics={"orphan_comment_rate": round(orphan_comment_rate, 4)},
                )
            )

        if short_comment_rate >= float(thresholds.get("short_comment_rate", 0.25)):
            findings.append(
                TaskFinding(
                    severity="info",
                    title="Very short comments dominate the sample",
                    detail=f"{short_comment_rate:.1%} of comments have cleaned length <= 3 characters.",
                    evidence=[EvidenceRecord(source_path=str(comments_path))],
                    metrics={"short_comment_rate": round(short_comment_rate, 4)},
                )
            )

        metrics = {
            "total_comments": total_comments,
            "total_contents": len(contents_df) if contents_df is not None else 0,
            "empty_comment_rate": round(empty_rate, 4),
            "duplicate_comment_id_count": duplicate_id_count,
            "duplicate_clean_text_count": duplicate_clean_text_count,
            "duplicate_clean_text_rate": round(duplicate_clean_text_rate, 4),
            "short_comment_rate": round(short_comment_rate, 4),
            "orphan_comment_rate": round(orphan_comment_rate, 4),
        }

        artifact_paths = [
            context.artifacts.write_json(
                self.name,
                "quality_metrics.json",
                {
                    "metrics": metrics,
                    "findings": [finding.model_dump() for finding in findings],
                    "source_files": [str(comments_path), str(contents_path)] if contents_df is not None else [str(comments_path)],
                },
            )
        ]

        report_lines = [
            "# Data Quality Review",
            "",
            f"- Topic: {context.topic.get('display_name', context.topic.get('target', 'Unknown topic'))}",
            f"- Comments file: `{comments_path}`",
            f"- Contents file: `{contents_path}`",
            "",
            "## Metrics",
            "",
            markdown_table(
                ["Metric", "Value"],
                [
                    ("total_comments", metrics["total_comments"]),
                    ("total_contents", metrics["total_contents"]),
                    ("empty_comment_rate", f"{empty_rate:.1%}"),
                    ("duplicate_comment_id_count", duplicate_id_count),
                    ("duplicate_clean_text_rate", f"{duplicate_clean_text_rate:.1%}"),
                    ("short_comment_rate", f"{short_comment_rate:.1%}"),
                    ("orphan_comment_rate", f"{orphan_comment_rate:.1%}"),
                ],
            ),
            "",
            "## Findings",
            "",
        ]

        if findings:
            for finding in findings:
                report_lines.extend(
                    [
                        f"### [{finding.severity.upper()}] {finding.title}",
                        finding.detail,
                        "",
                    ]
                )
        else:
            report_lines.extend(["No threshold-based issues were detected.", ""])

        if repeated_examples:
            report_lines.extend(
                [
                    "## Repeated Cleaned Text Samples",
                    "",
                    markdown_table(["Sample", "Count"], repeated_examples),
                    "",
                ]
            )

        artifact_paths.append(
            context.artifacts.write_markdown(
                self.name,
                "data_quality_review.md",
                "\n".join(report_lines),
            )
        )

        summary = f"Reviewed {total_comments} cleaned comments and produced {len(findings)} quality findings."
        return TaskResult(
            task_name=self.name,
            summary=summary,
            findings=findings,
            artifacts=artifact_paths,
            meta=metrics,
        )

