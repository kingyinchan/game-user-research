from __future__ import annotations

from collections import Counter

import pandas as pd

from config.labels import MODULE_TAGS

from ..framework import AgentContext, AgentTask, register_task
from ..llm import LLMService
from ..models import EvidenceRecord, TaskFinding, TaskResult
from ..report_llm import build_commentary_payload, build_commentary_prompts
from ..tools import as_bool, load_csv_if_exists, markdown_table, parse_tag_list, safe_excerpt


@register_task
class InsightReportTask(AgentTask):
    name = "insight_report"
    description = "Generate a reusable insight brief from labeled comments."

    def run(self, context: AgentContext) -> TaskResult:
        labeled_path = context.cleaned_dir / "comments_labeled.csv"
        if not labeled_path.exists():
            return TaskResult(
                task_name=self.name,
                status="skipped",
                summary=f"Missing labeled comments file: {labeled_path}",
            )

        df = pd.read_csv(labeled_path)
        if df.empty or "sentiment" not in df.columns:
            return TaskResult(
                task_name=self.name,
                status="skipped",
                summary="Labeled dataset is empty or missing sentiment field.",
            )

        df = df[df["sentiment"].notna()].copy()
        if df.empty:
            return TaskResult(
                task_name=self.name,
                status="skipped",
                summary="No labeled rows available for insight generation.",
            )

        df["comment_id"] = df["comment_id"].astype(str)
        df["module_tags_list"] = df["module_tags"].apply(parse_tag_list) if "module_tags" in df.columns else [[] for _ in range(len(df))]
        df["is_target_related"] = df["is_target_related"].apply(as_bool) if "is_target_related" in df.columns else False

        negative_sentiments = context.config.get("analysis", {}).get("negative_sentiments", ["negative", "mixed"])
        sentiment_counts = df["sentiment"].value_counts()
        negative_df = df[df["sentiment"].isin(negative_sentiments)]
        target_df = df[df["is_target_related"]]
        target_negative_df = df[df["is_target_related"] & df["sentiment"].isin(negative_sentiments)]

        module_counter: Counter[str] = Counter()
        target_module_counter: Counter[str] = Counter()
        for tags in negative_df["module_tags_list"]:
            module_counter.update(tags)
        for tags in target_negative_df["module_tags_list"]:
            target_module_counter.update(tags)

        top_negative_modules = module_counter.most_common(5)
        top_target_negative_modules = target_module_counter.most_common(5)

        churn_high = int((df.get("churn_risk", pd.Series(dtype=str)).fillna("") == "high").sum()) if "churn_risk" in df.columns else 0
        pay_high = int((df.get("pay_risk", pd.Series(dtype=str)).fillna("") == "high").sum()) if "pay_risk" in df.columns else 0

        insight_lines = [
            f"有效标注评论共 {len(df)} 条，其中负向/混合评论 {len(negative_df)} 条，占比 {len(negative_df) / len(df):.1%}。",
            f"目标角色相关评论 {len(target_df)} 条，其中目标相关负向评论 {len(target_negative_df)} 条。",
        ]

        if top_negative_modules:
            top_module_label, top_module_count = top_negative_modules[0]
            insight_lines.append(
                f"整体负向热点主要集中在“{MODULE_TAGS.get(top_module_label, {}).get('label', top_module_label)}”，出现 {top_module_count} 次。"
            )
        if top_target_negative_modules:
            top_target_label, top_target_count = top_target_negative_modules[0]
            insight_lines.append(
                f"目标角色相关负向热点主要集中在“{MODULE_TAGS.get(top_target_label, {}).get('label', top_target_label)}”，出现 {top_target_count} 次。"
            )
        if churn_high or pay_high:
            insight_lines.append(f"高流失风险评论 {churn_high} 条，高付费风险评论 {pay_high} 条。")

        review_queue_path = context.artifacts.artifacts_dir / "label_review_queue" / "label_review_queue.csv"
        review_queue_df = load_csv_if_exists(review_queue_path)

        commentary_payload = build_commentary_payload(
            df=df,
            negative_sentiments=negative_sentiments,
            topic_display_name=context.topic.get("display_name", context.topic.get("target", "Unknown topic")),
            target_name=context.topic.get("target", "Unknown target"),
            review_queue_df=review_queue_df,
            config=context.agent_config.get("report_llm", {}),
        )

        llm_commentary = ""
        report_llm_config = context.agent_config.get("report_llm", {})
        report_llm = LLMService.from_config(report_llm_config) if report_llm_config else None
        if report_llm and report_llm.is_available():
            system_prompt, user_prompt = build_commentary_prompts(commentary_payload)
            try:
                llm_commentary = report_llm.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
            except Exception as exc:
                llm_commentary = f"_LLM 点评生成失败：{exc}_"

        report_lines = [
            "# Insight Report",
            "",
            f"- Topic: {context.topic.get('display_name', context.topic.get('target', 'Unknown topic'))}",
            f"- Source: `{labeled_path}`",
            "",
            "## Snapshot",
            "",
            markdown_table(
                ["Metric", "Value"],
                [
                    ("labeled_comments", len(df)),
                    ("negative_comments", len(negative_df)),
                    ("negative_ratio", f"{len(negative_df) / len(df):.1%}"),
                    ("target_related_comments", len(target_df)),
                    ("target_negative_comments", len(target_negative_df)),
                    ("high_churn_risk", churn_high),
                    ("high_pay_risk", pay_high),
                ],
            ),
            "",
            "## Deterministic Insights",
            "",
        ]
        report_lines.extend([f"- {line}" for line in insight_lines])
        report_lines.append("")

        if top_negative_modules:
            report_lines.extend(
                [
                    "## Negative Module Hotspots",
                    "",
                    markdown_table(
                        ["Module", "Count"],
                        [
                            (MODULE_TAGS.get(tag, {}).get("label", tag), count)
                            for tag, count in top_negative_modules
                        ],
                    ),
                    "",
                ]
            )

        if top_target_negative_modules:
            report_lines.extend(
                [
                    "## Target Negative Hotspots",
                    "",
                    markdown_table(
                        ["Module", "Count"],
                        [
                            (MODULE_TAGS.get(tag, {}).get("label", tag), count)
                            for tag, count in top_target_negative_modules
                        ],
                    ),
                    "",
                ]
            )

        if llm_commentary:
            report_lines.extend(
                [
                    "## LLM Commentary",
                    "",
                    llm_commentary,
                    "",
                ]
            )

        artifact_paths = [
            context.artifacts.write_json(
                self.name,
                "insight_snapshot.json",
                {
                    "sentiment_counts": sentiment_counts.to_dict(),
                    "top_negative_modules": top_negative_modules,
                    "top_target_negative_modules": top_target_negative_modules,
                    "high_churn_risk": churn_high,
                    "high_pay_risk": pay_high,
                },
            ),
            context.artifacts.write_json(
                self.name,
                "commentary_payload.json",
                commentary_payload,
            ),
            context.artifacts.write_markdown(
                self.name,
                "insight_report.md",
                "\n".join(report_lines),
            ),
        ]

        evidence: list[EvidenceRecord] = []
        if "content_clean" in negative_df.columns and not negative_df.empty:
            for _, row in negative_df.head(3).iterrows():
                evidence.append(
                    EvidenceRecord(
                        source_path=str(labeled_path),
                        row_id=str(row.get("comment_id")),
                        excerpt=safe_excerpt(row.get("content_clean") or row.get("content")),
                    )
                )

        findings = [
            TaskFinding(
                severity="info",
                title="Insight brief generated",
                detail=f"Built an insight report from {len(df)} labeled comments.",
                evidence=evidence or [EvidenceRecord(source_path=str(labeled_path))],
                metrics={
                    "labeled_comments": len(df),
                    "negative_comments": len(negative_df),
                    "target_related_comments": len(target_df),
                },
            )
        ]

        meta = {
            "labeled_comments": len(df),
            "negative_comments": len(negative_df),
            "top_negative_modules": top_negative_modules,
            "llm_commentary_enabled": bool(report_llm_config.get("enabled", False)),
            "llm_commentary_generated": bool(llm_commentary and not llm_commentary.startswith("_LLM 点评生成失败")),
        }

        return TaskResult(
            task_name=self.name,
            summary=f"Generated reusable insight report from {len(df)} labeled comments.",
            findings=findings,
            artifacts=artifact_paths,
            meta=meta,
        )
