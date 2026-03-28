from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from agents.framework import build_context, create_task, list_tasks
from agents.models import RunManifest, TaskResult
import agents.tasks  # noqa: F401  # Ensure built-in tasks are registered.


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run reusable agent tasks for the analysis pipeline.")
    parser.add_argument("--list", action="store_true", help="List available tasks and exit.")
    parser.add_argument(
        "--task",
        action="append",
        dest="tasks",
        help="Task name to run. Repeat for multiple tasks. If omitted, uses config default_tasks.",
    )
    return parser.parse_args()


def print_task_catalog() -> None:
    print("Available agent tasks:")
    for task_name, task_cls in sorted(list_tasks().items()):
        print(f"  - {task_name}: {task_cls.description}")


def main() -> None:
    args = parse_args()
    context = build_context(CURRENT_DIR)

    if args.list:
        print_task_catalog()
        return

    task_names = args.tasks or context.agent_config.get("default_tasks", [])
    if not task_names:
        raise SystemExit("No tasks specified. Use --task or configure agents.default_tasks in project.yaml.")

    results: list[TaskResult] = []
    for task_name in task_names:
        print(f"\n=== Running task: {task_name} ===")
        try:
            task = create_task(task_name)
            result = task.run(context)
        except Exception as exc:
            result = TaskResult(task_name=task_name, status="failed", summary=str(exc))

        results.append(result)
        print(f"[{result.status}] {result.summary}")
        for artifact in result.artifacts:
            print(f"  artifact: {artifact}")

    manifest = RunManifest(
        topic_name=context.topic.get("display_name", context.topic.get("target", "Unknown topic")),
        tasks=results,
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = context.artifacts.write_json("runs", f"agent_run_{timestamp}.json", manifest.model_dump())

    print(f"\nRun manifest saved to: {manifest_path}")


if __name__ == "__main__":
    main()

