from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = ROOT_DIR / "analysis"
RUNTIME_DIR = ROOT_DIR / "backend" / "runtime"
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_ROOT_ENV = "APP_DATA_ROOT"

_configured_data_root = os.getenv(DATA_ROOT_ENV, "").strip()
_demo_data_root = Path(_configured_data_root).expanduser() if _configured_data_root else None
DEMO_MODE = bool(_demo_data_root and _demo_data_root.exists())

if DEMO_MODE:
    DATA_SOURCE_LABEL = str(_demo_data_root)
    CLEANED_DATA_DIR = _demo_data_root / "data"
    OUTPUT_DIR = _demo_data_root / "charts"
    REPORTS_DIR = _demo_data_root / "reports"
    ARTIFACTS_DIR = _demo_data_root / "reports"
    RUNS_DIR = RUNTIME_DIR

    PROJECT_CONFIG_PATH = _demo_data_root / "config" / "project.yaml"
    LABELED_COMMENTS_PATH = CLEANED_DATA_DIR / "comments_labeled.csv"
    ROUTING_REPORT_PATH = CLEANED_DATA_DIR / "label_routing_report.json"
    REVIEW_QUEUE_PATH = REPORTS_DIR / "label_review_queue.csv"
    INSIGHT_REPORT_PATH = REPORTS_DIR / "insight_report.md"
else:
    DATA_SOURCE_LABEL = str(ANALYSIS_DIR)
    CLEANED_DATA_DIR = ANALYSIS_DIR / "cleaned_data"
    OUTPUT_DIR = ANALYSIS_DIR / "output"
    REPORTS_DIR = ANALYSIS_DIR / "reports"
    ARTIFACTS_DIR = ANALYSIS_DIR / "artifacts" / "agents"
    RUNS_DIR = ARTIFACTS_DIR / "runs"

    PROJECT_CONFIG_PATH = ANALYSIS_DIR / "config" / "project.yaml"
    LABELED_COMMENTS_PATH = CLEANED_DATA_DIR / "comments_labeled.csv"
    ROUTING_REPORT_PATH = CLEANED_DATA_DIR / "_label_routing_report.json"
    REVIEW_QUEUE_PATH = ARTIFACTS_DIR / "label_review_queue" / "label_review_queue.csv"
    INSIGHT_REPORT_PATH = REPORTS_DIR / "insight_report" / "insight_report.md"

CHART_TITLES = {
    "sentiment_distribution.png": "????",
    "topic_negative_distribution.png": "????????",
    "risk_distribution.png": "????",
    "negative_module_distribution.png": "??????",
}
