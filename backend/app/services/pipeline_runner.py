from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from backend.app.config import ROOT_DIR, RUNTIME_DIR
from backend.app.schemas import PipelineRunResponse, PipelineStatusResponse


class PipelineRunner:
    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._log_handle = None
        self._task: str | None = None
        self._log_path: Path | None = None
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._return_code: int | None = None
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    def start(self, task: str) -> PipelineRunResponse:
        self._refresh_state()
        if self._process and self._process.poll() is None:
            raise RuntimeError("已有任务在运行，请先等待当前任务结束。")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._task = task
        self._started_at = datetime.now()
        self._finished_at = None
        self._return_code = None
        self._log_path = RUNTIME_DIR / f"{task}_{timestamp}.log"
        self._log_handle = self._log_path.open("w", encoding="utf-8")

        command = [
            sys.executable,
            str(ROOT_DIR / "analysis" / "agent_runner.py"),
            "--task",
            task,
        ]
        self._process = subprocess.Popen(
            command,
            cwd=str(ROOT_DIR),
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )

        return PipelineRunResponse(
            status="running",
            task=task,
            pid=self._process.pid,
            log_path=str(self._log_path),
            message="任务已启动。",
        )

    def _refresh_state(self) -> None:
        if self._process is None:
            return

        return_code = self._process.poll()
        if return_code is None:
            return

        self._return_code = return_code
        self._finished_at = self._finished_at or datetime.now()
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def _tail_lines(self, max_lines: int = 80) -> list[str]:
        if not self._log_path or not self._log_path.exists():
            return []
        lines = self._log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-max_lines:]

    def status(self) -> PipelineStatusResponse:
        self._refresh_state()

        if self._process is None:
            return PipelineStatusResponse(status="idle", log_tail=self._tail_lines())

        running = self._process.poll() is None
        if running:
            status = "running"
        else:
            status = "completed" if (self._return_code or 0) == 0 else "failed"

        return PipelineStatusResponse(
            status=status,
            task=self._task,
            pid=self._process.pid,
            return_code=self._return_code,
            started_at=self._started_at.isoformat(timespec="seconds") if self._started_at else None,
            finished_at=self._finished_at.isoformat(timespec="seconds") if self._finished_at else None,
            log_path=str(self._log_path) if self._log_path else None,
            log_tail=self._tail_lines(),
        )


pipeline_runner = PipelineRunner()
