from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = ROOT_DIR / "analysis"
CLEANED_DATA_DIR = ANALYSIS_DIR / "cleaned_data"
OUTPUT_DIR = ANALYSIS_DIR / "output"
REPORTS_DIR = ANALYSIS_DIR / "reports"
ARTIFACTS_DIR = ANALYSIS_DIR / "artifacts" / "agents"
RUNS_DIR = ARTIFACTS_DIR / "runs"
RUNTIME_DIR = ROOT_DIR / "backend" / "runtime"
FRONTEND_DIR = ROOT_DIR / "frontend"

PROJECT_CONFIG_PATH = ANALYSIS_DIR / "config" / "project.yaml"
LABELED_COMMENTS_PATH = CLEANED_DATA_DIR / "comments_labeled.csv"
ROUTING_REPORT_PATH = CLEANED_DATA_DIR / "_label_routing_report.json"
REVIEW_QUEUE_PATH = ARTIFACTS_DIR / "label_review_queue" / "label_review_queue.csv"
INSIGHT_REPORT_PATH = REPORTS_DIR / "insight_report" / "insight_report.md"

CHART_TITLES = {
    "sentiment_distribution.png": "情感分布",
    "topic_negative_distribution.png": "目标相关负面模块",
    "risk_distribution.png": "风险分布",
}
