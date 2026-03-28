from __future__ import annotations

from collections import Counter

import pandas as pd

from ..framework import AgentContext, AgentTask, register_task
from ..models import EvidenceRecord, TaskFinding, TaskResult
from ..tools import as_bool, markdown_table, parse_tag_list, safe_excerpt


@register_task
class LabelReviewQueueTask(AgentTask):
    name = "label_review_queue"
    description = "Build a reusable human-review queue from labeled comments."

    def run(self, context: AgentContext) -> TaskResult:
        labeled_path = context.cleaned_dir / "comments_labeled.csv"
        if not labeled_path.exists():
            return TaskResult(
                task_name=self.name,
                status="skipped",
                summary=f"Missing labeled comments file: {labeled_path}",
            )

        df = pd.read_csv(labeled_path)
        if df.empty:
            return TaskResult(
                task_name=self.name,
                status="skipped",
                summary="comments_labeled.csv is empty.",
            )

        review_cfg = context.agent_config.get("review_queue", {})
        min_length = int(review_cfg.get("long_text_min_length", 6))

        queue_rows: list[dict] = []
        reason_counter: Counter[str] = Counter()

        for _, row in df.iterrows():
            content = str(row.get("content_clean") or row.get("content") or "").strip()
            text_length = int(row.get("content_clean_length", len(content)))
            sentiment = str(row.get("sentiment") or "").strip().lower()
            tags = parse_tag_list(row.get("module_tags"))
            is_target_related = as_bool(row.get("is_target_related"))
            summary_reason = str(row.get("summary_reason") or "")

            reasons: list[tuple[str, str]] = []
            if "标注失败" in summary_reason:
                reasons.append(("P0", "llm_error_fallback"))
            if sentiment == "mixed":
                reasons.append(("P1", "mixed_sentiment"))
            if sentiment in {"negative", "mixed"} and not tags:
                reasons.append(("P0", "negative_without_module"))
            if is_target_related and not tags:
                reasons.append(("P1", "target_related_without_module"))
            if text_length >= min_length and not tags:
                reasons.append(("P2", "long_text_without_module"))

            if not reasons:
                continue

            priority = sorted(reasons, key=lambda item: item[0])[0][0]
            reason_labels = [reason for _, reason in reasons]
            for label in reason_labels:
                reason_counter[label] += 1

            queue_rows.append(
                {
                    "comment_id": row.get("comment_id"),
                    "priority": priority,
                    "review_reason": ",".join(reason_labels),
                    "sentiment": sentiment,
                    "module_tags": ",".join(tags),
                    "is_target_related": is_target_related,
                    "content_clean": content,
                    "summary_reason": summary_reason,
                }
            )

        queue_df = pd.DataFrame(queue_rows)
        if not queue_df.empty:
            queue_df["priority_rank"] = queue_df["priority"].map({"P0": 0, "P1": 1, "P2": 2}).fillna(9)
            queue_df = queue_df.sort_values(["priority_rank", "comment_id"]).drop(columns=["priority_rank"])

        findings = [
            TaskFinding(
                severity="info",
                title="Review queue generated",
                detail=f"Selected {len(queue_df)} comments for human review.",
                evidence=[
                    EvidenceRecord(
                        source_path=str(labeled_path),
                        row_id=str(row["comment_id"]),
                        excerpt=safe_excerpt(row["content_clean"]),
                    )
                    for _, row in queue_df.head(3).iterrows()
                ] if not queue_df.empty else [EvidenceRecord(source_path=str(labeled_path))],
                metrics=dict(reason_counter),
            )
        ]

        artifact_paths: list[str] = []
        csv_path = context.artifacts.artifacts_dir / self.name / "label_review_queue.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        queue_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        artifact_paths.append(str(csv_path))

        summary_rows = list(reason_counter.items())
        report_lines = [
            "# Label Review Queue",
            "",
            f"- Source: `{labeled_path}`",
            f"- Queue size: {len(queue_df)}",
            "",
            "## Reason Breakdown",
            "",
        ]
        if summary_rows:
            report_lines.extend(
                [
                    markdown_table(["Reason", "Count"], summary_rows),
                    "",
                ]
            )
        else:
            report_lines.extend(["No review candidates were generated.", ""])

        if not queue_df.empty:
            preview_rows = [
                (
                    row["comment_id"],
                    row["priority"],
                    row["review_reason"],
                    safe_excerpt(row["content_clean"], max_length=50),
                )
                for _, row in queue_df.head(10).iterrows()
            ]
            report_lines.extend(
                [
                    "## Queue Preview",
                    "",
                    markdown_table(["comment_id", "priority", "reason", "content"], preview_rows),
                    "",
                ]
            )

        artifact_paths.append(
            context.artifacts.write_markdown(
                self.name,
                "label_review_queue.md",
                "\n".join(report_lines),
            )
        )

        return TaskResult(
            task_name=self.name,
            summary=f"Generated review queue with {len(queue_df)} candidate comments.",
            findings=findings,
            artifacts=artifact_paths,
            meta={"queue_size": int(len(queue_df)), "reasons": dict(reason_counter)},
        )

