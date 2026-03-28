from __future__ import annotations

import locale
import os
import subprocess
import sys
from typing import Any

from ..framework import AgentContext, AgentTask, create_task, register_task
from ..models import EvidenceRecord, TaskFinding, TaskResult
from ..tools import markdown_table


@register_task
class FullPipelineReportTask(AgentTask):
    name = "full_pipeline_report"
    description = "Run the full pipeline end to end and emit a consolidated report."

    def run(self, context: AgentContext) -> TaskResult:
        pipeline_cfg = context.agent_config.get("pipeline", {})
        downstream_tasks = pipeline_cfg.get("downstream_tasks", ["label_review_queue", "insight_report"])
        continue_on_failure = bool(pipeline_cfg.get("continue_on_failure", False))
        reuse_existing_labeled = bool(pipeline_cfg.get("reuse_existing_labeled", True))

        env_path = context.project_root / ".env"
        raw_data_dir = context.raw_data_dir
        cleaned_comments = context.cleaned_dir / "comments_cleaned.csv"
        labeled_comments = context.cleaned_dir / "comments_labeled.csv"

        preflight = {
            "raw_data_exists": raw_data_dir.exists(),
            "env_file_exists": env_path.exists(),
            "api_key_present": bool(os.getenv("OPENAI_API_KEY", "")),
            "existing_cleaned_comments": cleaned_comments.exists(),
            "existing_labeled_comments": labeled_comments.exists(),
        }

        findings: list[TaskFinding] = []
        if not preflight["raw_data_exists"]:
            findings.append(
                TaskFinding(
                    severity="critical",
                    title="Missing raw data directory",
                    detail=f"Raw data directory does not exist: {raw_data_dir}",
                    evidence=[EvidenceRecord(source_path=str(raw_data_dir))],
                )
            )

        if not preflight["env_file_exists"]:
            findings.append(
                TaskFinding(
                    severity="warning",
                    title="Missing .env file",
                    detail="LLM labeling cannot run automatically until a .env file is provided.",
                    evidence=[EvidenceRecord(source_path=str(env_path))],
                )
            )

        if not preflight["api_key_present"] and not preflight["existing_labeled_comments"]:
            findings.append(
                TaskFinding(
                    severity="critical",
                    title="Missing API key for labeling",
                    detail="OPENAI_API_KEY is not available, so the pipeline cannot produce fresh labeled data.",
                    evidence=[EvidenceRecord(source_path=str(env_path))],
                )
            )

        step_records: list[dict[str, Any]] = []
        artifact_paths: list[str] = []

        def record_step(step_name: str, status: str, detail: str, log_path: str | None = None) -> None:
            step_records.append(
                {
                    "step": step_name,
                    "status": status,
                    "detail": detail,
                    "log": log_path or "",
                }
            )
            if log_path:
                artifact_paths.append(log_path)

        def run_script(step_name: str, relative_script: str) -> bool:
            command = [sys.executable, str(context.analysis_dir / relative_script)]
            encoding = locale.getpreferredencoding(False) or "utf-8"
            completed = subprocess.run(
                command,
                cwd=str(context.project_root),
                capture_output=True,
                text=True,
                encoding=encoding,
                errors="replace",
            )
            log_content = "\n".join(
                [
                    f"COMMAND: {' '.join(command)}",
                    "",
                    "STDOUT:",
                    (completed.stdout or "").strip(),
                    "",
                    "STDERR:",
                    (completed.stderr or "").strip(),
                    "",
                    f"EXIT_CODE: {completed.returncode}",
                ]
            )
            log_path = context.artifacts.write_text(self.name, f"{step_name}.log", log_content)
            if completed.returncode == 0:
                record_step(step_name, "success", f"{relative_script} completed successfully.", log_path)
                return True

            record_step(step_name, "failed", f"{relative_script} failed with exit code {completed.returncode}.", log_path)
            return False

        if preflight["raw_data_exists"]:
            cleaning_ok = run_script("data_cleaning", "data_cleaning.py")
        else:
            cleaning_ok = False
            record_step("data_cleaning", "skipped", "Skipped because raw data directory is missing.")

        if cleaning_ok:
            quality_task = create_task("data_quality_review")
            quality_result = quality_task.run(context)
            record_step("data_quality_review", quality_result.status, quality_result.summary)
            artifact_paths.extend(quality_result.artifacts)
        elif cleaned_comments.exists():
            quality_task = create_task("data_quality_review")
            quality_result = quality_task.run(context)
            record_step("data_quality_review", quality_result.status, "Used existing cleaned data for quality review.")
            artifact_paths.extend(quality_result.artifacts)
        else:
            record_step("data_quality_review", "skipped", "Skipped because cleaned comments are not available.")

        can_run_labeling = bool(os.getenv("OPENAI_API_KEY", ""))
        if can_run_labeling:
            labeling_ok = run_script("llm_label", "llm_label.py")
        elif reuse_existing_labeled and labeled_comments.exists():
            labeling_ok = True
            record_step("llm_label", "skipped", "Reused existing labeled comments file.")
        else:
            labeling_ok = False
            record_step("llm_label", "skipped", "Skipped because OPENAI_API_KEY is not configured and no labeled file exists.")

        if not labeling_ok and not continue_on_failure:
            report_path = self._write_report(context, preflight, step_records, findings)
            artifact_paths.append(report_path)
            summary = "Pipeline stopped before analysis because labeling prerequisites were not met."
            return TaskResult(
                task_name=self.name,
                status="failed",
                summary=summary,
                findings=findings,
                artifacts=list(dict.fromkeys(artifact_paths)),
                meta={"preflight": preflight, "steps": step_records},
            )

        if labeled_comments.exists():
            analysis_ok = run_script("analyze", "analyze.py")
        else:
            analysis_ok = False
            record_step("analyze", "skipped", "Skipped because labeled comments are not available.")

        if analysis_ok or labeled_comments.exists():
            for task_name in downstream_tasks:
                task = create_task(task_name)
                result = task.run(context)
                record_step(task_name, result.status, result.summary)
                artifact_paths.extend(result.artifacts)
        else:
            for task_name in downstream_tasks:
                record_step(task_name, "skipped", "Skipped because analysis prerequisites were not met.")

        report_path = self._write_report(context, preflight, step_records, findings)
        artifact_paths.append(report_path)

        has_failure = any(step["status"] == "failed" for step in step_records)
        status = "failed" if has_failure else "success"
        summary = "Full pipeline run completed." if status == "success" else "Full pipeline run completed with blocking failures."
        return TaskResult(
            task_name=self.name,
            status=status,
            summary=summary,
            findings=findings,
            artifacts=list(dict.fromkeys(artifact_paths)),
            meta={"preflight": preflight, "steps": step_records},
        )

    def _write_report(
        self,
        context: AgentContext,
        preflight: dict[str, Any],
        step_records: list[dict[str, Any]],
        findings: list[TaskFinding],
    ) -> str:
        preflight_rows = [(key, value) for key, value in preflight.items()]
        step_rows = [(item["step"], item["status"], item["detail"]) for item in step_records]

        lines = [
            "# 全流程执行报告",
            "",
            f"- 专题: {context.topic.get('display_name', context.topic.get('target', 'Unknown topic'))}",
            f"- 原始数据目录: `{context.raw_data_dir}`",
            f"- 清洗数据目录: `{context.cleaned_dir}`",
            f"- 输出目录: `{context.output_dir}`",
            "",
            "## 预检结果",
            "",
            markdown_table(["检查项", "结果"], preflight_rows),
            "",
            "## 执行步骤",
            "",
            markdown_table(["步骤", "状态", "说明"], step_rows),
            "",
            "## 阻塞项",
            "",
        ]

        if findings:
            for finding in findings:
                lines.extend(
                    [
                        f"- [{finding.severity}] {finding.title}: {finding.detail}",
                    ]
                )
        else:
            lines.append("- 无阻塞项")

        lines.append("")
        return context.artifacts.write_markdown(self.name, "full_pipeline_report.md", "\n".join(lines))
