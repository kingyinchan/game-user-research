from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEMO_DATA_DIR = Path(__file__).resolve().parent / "data"


def list_snapshots() -> list[Path]:
    if not DEMO_DATA_DIR.exists():
        return []
    return sorted(path for path in DEMO_DATA_DIR.iterdir() if path.is_dir())


def resolve_snapshot(name: str | None) -> Path:
    snapshots = list_snapshots()
    if not snapshots:
        raise SystemExit("demo/data/ 下没有可用快照。")

    if name:
        candidate = DEMO_DATA_DIR / name
        if not candidate.exists():
            available = ", ".join(path.name for path in snapshots)
            raise SystemExit(f"未找到 demo 快照: {name}。可用快照: {available}")
        return candidate

    if len(snapshots) == 1:
        return snapshots[0]

    available = ", ".join(path.name for path in snapshots)
    raise SystemExit(f"检测到多个 demo 快照，请使用 --snapshot 指定。可用快照: {available}")


def load_manifest(snapshot_dir: Path) -> dict:
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the dashboard against a demo snapshot.")
    parser.add_argument("--snapshot", help="Snapshot directory name under demo/data")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true", help="Disable uvicorn auto-reload")
    parser.add_argument("--list", action="store_true", help="List available snapshots and exit")
    args = parser.parse_args()

    snapshots = list_snapshots()
    if args.list:
        if not snapshots:
            print("No demo snapshots found.")
            return 0
        print("Available demo snapshots:")
        for path in snapshots:
            print(f"- {path.name}")
        return 0

    snapshot_dir = resolve_snapshot(args.snapshot)
    manifest = load_manifest(snapshot_dir)

    env = os.environ.copy()
    env["APP_DATA_ROOT"] = str(snapshot_dir)

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if not args.no_reload:
        command.append("--reload")

    snapshot_name = manifest.get("snapshot_name", snapshot_dir.name)
    topic = manifest.get("topic", snapshot_dir.name)
    print(f"Using demo snapshot: {snapshot_name}")
    print(f"Topic: {topic}")
    print(f"Data root: {snapshot_dir}")
    print(f"Dashboard: http://{args.host}:{args.port}/studio/")
    print(f"API docs: http://{args.host}:{args.port}/docs")
    print("")

    completed = subprocess.run(command, cwd=str(ROOT_DIR), env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
