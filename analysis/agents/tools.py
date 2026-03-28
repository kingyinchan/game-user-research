from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Iterable

import pandas as pd


def as_bool(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def normalize_boolean_series(series: pd.Series) -> pd.Series:
    return series.apply(as_bool)


def parse_tag_list(value) -> list[str]:
    if pd.isna(value) or value == "":
        return []

    text = str(value).strip()
    if not text:
        return []

    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass

        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (ValueError, SyntaxError):
            pass

    if "," in text:
        return [item.strip() for item in text.split(",") if item.strip()]

    return [text]


def safe_excerpt(value, max_length: int = 80) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def markdown_table(headers: list[str], rows: Iterable[Iterable[object]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    data_lines = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header_line, divider, *data_lines])


def load_csv_if_exists(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)

