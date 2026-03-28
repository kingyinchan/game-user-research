# -*- coding: utf-8 -*-
"""
更接近工业做法的 LLM 标注管线。

分层策略:
  1. 规则预标高置信样本
  2. 对完全相同的清洗文本做结果复用
  3. 仅将剩余疑难样本送入 LLM
  4. 失败批次写失败日志，不污染成功缓存
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from collections.abc import Iterable
from typing import Literal

import pandas as pd
from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, APIStatusError, OpenAI, RateLimitError
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
from tqdm import tqdm

from config import get_llm_config, get_paths, get_topic
from config.labels import MODULE_TAGS
from config.prompts import build_batch_user_prompt, build_system_prompt
from rule_labeler import RuleDecision, build_rule_label

# -- 环境变量 --
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API_KEY = os.getenv("OPENAI_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")

# -- 路径（从 project.yaml 读取） --
ANALYSIS_DIR = os.path.dirname(__file__)
_paths = get_paths()
INPUT_PATH = os.path.join(ANALYSIS_DIR, _paths.get("cleaned_data", "cleaned_data"), "comments_cleaned.csv")
OUTPUT_PATH = os.path.join(ANALYSIS_DIR, _paths.get("cleaned_data", "cleaned_data"), "comments_labeled.csv")
CACHE_PATH = os.path.join(ANALYSIS_DIR, _paths.get("cleaned_data", "cleaned_data"), "_label_cache.jsonl")
FAILURE_LOG_PATH = os.path.join(ANALYSIS_DIR, _paths.get("cleaned_data", "cleaned_data"), "_label_failures.jsonl")
ROUTING_REPORT_PATH = os.path.join(ANALYSIS_DIR, _paths.get("cleaned_data", "cleaned_data"), "_label_routing_report.json")


LABEL_FIELDS = [
    "sentiment",
    "module_tags",
    "is_version_related",
    "is_target_related",
    "churn_risk",
    "pay_risk",
    "summary_reason",
]

EXPORT_FIELDS = [
    "comment_id",
    *LABEL_FIELDS,
    "label_source",
    "route_reason",
]


class CommentLabel(BaseModel):
    sentiment: Literal["positive", "neutral", "negative", "mixed"] = Field(description="评论整体情感倾向")
    module_tags: list[str] = Field(default_factory=list, description="评论涉及的游戏模块（多选，可为空）")
    is_version_related: bool = Field(description="是否与版本更新/前瞻相关")
    is_target_related: bool = Field(description="是否与搜索目标相关")
    churn_risk: Literal["low", "medium", "high"] = Field(description="用户流失风险等级")
    pay_risk: Literal["low", "medium", "high"] = Field(description="付费体验负面风险等级")
    summary_reason: str = Field(max_length=50, description="标注理由（一句话，不超过50字）")


class BatchCommentLabel(CommentLabel):
    comment_id: str = Field(description="评论 ID，必须与输入一致")


class BatchLabelResponse(BaseModel):
    items: list[BatchCommentLabel] = Field(default_factory=list)


class TransientLabelError(Exception):
    """可稍后重跑的暂时性错误。"""


class BatchValidationError(Exception):
    """批量输出不符合预期。"""


client = None
_llm_cfg = get_llm_config()
VALID_TAGS = set(MODULE_TAGS.keys())


def get_client() -> OpenAI:
    global client
    if client is None:
        if not API_KEY:
            print("错误: 未设置 OPENAI_API_KEY，请检查 .env 文件。")
            sys.exit(1)
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return client


def is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError, TransientLabelError)):
        return True

    status_code = getattr(exc, "status_code", None)
    if status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True

    text = str(exc).lower()
    transient_markers = [
        "429",
        "rate limit",
        "too many requests",
        "connection error",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "service unavailable",
        "server error",
    ]
    return any(marker in text for marker in transient_markers)


def should_retry_exception(exc: Exception) -> bool:
    return is_transient_error(exc)


def normalize_label_payload(data: dict) -> dict:
    normalized = dict(data)
    normalized["sentiment"] = str(normalized.get("sentiment", "neutral")).strip().lower()
    normalized["churn_risk"] = str(normalized.get("churn_risk", "low")).strip().lower()
    normalized["pay_risk"] = str(normalized.get("pay_risk", "low")).strip().lower()

    module_tags = normalized.get("module_tags", [])
    if isinstance(module_tags, str):
        module_tags = [item.strip() for item in module_tags.split(",") if item.strip()]
    normalized["module_tags"] = [tag for tag in module_tags if tag in VALID_TAGS]
    normalized["summary_reason"] = str(normalized.get("summary_reason", "")).strip()[:50]
    return normalized


def chunked(items: list[dict], batch_size: int) -> Iterable[list[dict]]:
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def build_cache_record(comment_id: str, label: CommentLabel, label_source: str, route_reason: str) -> dict:
    return {
        "comment_id": comment_id,
        **label.model_dump(),
        "label_source": label_source,
        "route_reason": route_reason,
    }


def append_cache_record(record: dict) -> None:
    with open(CACHE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def save_label_record(
    comment_id: str,
    label: CommentLabel,
    cache: dict[str, dict],
    label_source: str,
    route_reason: str,
) -> dict:
    record = build_cache_record(comment_id, label, label_source, route_reason)
    append_cache_record(record)
    cache[comment_id] = record
    return record


def append_failure_log(comment_ids: list[str], error: Exception, reason: str) -> None:
    record = {
        "comment_ids": comment_ids,
        "reason": reason,
        "error": str(error),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(FAILURE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_cache() -> dict[str, dict]:
    cache: dict[str, dict] = {}
    skipped_failed = 0

    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if _llm_cfg.get("retry_failed_cache", True) and str(record.get("summary_reason", "")).startswith("标注失败:"):
                    skipped_failed += 1
                    continue

                cache[str(record["comment_id"])] = record

        print(f"  已加载缓存: {len(cache)} 条")
        if skipped_failed:
            print(f"  检测到 {skipped_failed} 条失败缓存，本次会重新尝试。")

    return cache


def build_text_reuse_cache(df_valid: pd.DataFrame, cache: dict[str, dict]) -> dict[str, dict]:
    id_to_text = {
        str(row["comment_id"]): str(row["content_clean"]).strip()
        for _, row in df_valid.iterrows()
        if str(row["content_clean"]).strip()
    }
    text_cache: dict[str, dict] = {}
    for comment_id, record in cache.items():
        text = id_to_text.get(comment_id, "")
        if text:
            text_cache[text] = {field: record.get(field) for field in LABEL_FIELDS}
    return text_cache


def write_routing_report(route_counter: Counter, reason_counter: Counter, total_valid: int, cache_size: int, remaining: int) -> None:
    payload = {
        "total_valid_comments": total_valid,
        "cache_size": cache_size,
        "remaining_unlabeled": remaining,
        "route_counter": dict(route_counter),
        "route_reason_counter": dict(reason_counter),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(ROUTING_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  路由报告已保存: {ROUTING_REPORT_PATH}")


@retry(
    stop=stop_after_attempt(_llm_cfg.get("retry_attempts", 6)),
    wait=wait_exponential(
        multiplier=1,
        min=_llm_cfg.get("retry_min_wait", 3),
        max=_llm_cfg.get("retry_max_wait", 90),
    ),
    retry=retry_if_exception(should_retry_exception),
    reraise=True,
)
def call_llm_batch(system_prompt: str, comments: list[tuple[str, str]]) -> list[BatchCommentLabel]:
    response = get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_batch_user_prompt(comments)},
        ],
        temperature=_llm_cfg.get("temperature", 0.1),
        max_tokens=_llm_cfg.get("max_tokens", 1024),
        response_format={"type": "json_object"},
    )

    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise BatchValidationError("模型返回为空。")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BatchValidationError(f"模型返回不是合法 JSON: {exc}") from exc

    try:
        parsed = BatchLabelResponse(**payload)
    except Exception as exc:
        raise BatchValidationError(f"批量输出 schema 校验失败: {exc}") from exc

    expected_ids = {comment_id for comment_id, _ in comments}
    actual_ids = {item.comment_id for item in parsed.items}
    if expected_ids != actual_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        raise BatchValidationError(f"comment_id 不匹配，missing={missing} extra={extra}")

    return [BatchCommentLabel(**normalize_label_payload(item.model_dump())) for item in parsed.items]


def process_single_comment(system_prompt: str, comment_id: str, comment: str) -> BatchCommentLabel:
    items = call_llm_batch(system_prompt, [(comment_id, comment)])
    return items[0]


def process_rows_individually(
    system_prompt: str,
    batch_rows: list[dict],
    cache: dict[str, dict],
    text_cache: dict[str, dict],
    route_counter: Counter,
) -> tuple[int, int]:
    success = 0
    failed = 0
    interval = float(_llm_cfg.get("request_interval_seconds", 0))

    for row in batch_rows:
        try:
            item = process_single_comment(system_prompt, row["comment_id"], row["content_clean"])
            label = CommentLabel(**item.model_dump(exclude={"comment_id"}))
            save_label_record(row["comment_id"], label, cache, "llm", "llm_single_fallback")
            text_cache[row["content_clean"]] = label.model_dump()
            route_counter["llm_success"] += 1
            route_counter["llm_single_fallback_success"] += 1
            success += 1
        except Exception as exc:
            if is_transient_error(exc):
                append_failure_log([row["comment_id"]], exc, "transient_single_retry_failure")
                raise TransientLabelError(str(exc)) from exc

            append_failure_log([row["comment_id"]], exc, "non_transient_single_failure")
            print(f"\n  跳过异常样本 [{row['comment_id']}]: {exc}")
            route_counter["llm_non_transient_skip"] += 1
            failed += 1

        if interval > 0:
            time.sleep(interval)

    return success, failed


def process_batch(
    system_prompt: str,
    batch_rows: list[dict],
    cache: dict[str, dict],
    text_cache: dict[str, dict],
    route_counter: Counter,
) -> tuple[int, int]:
    comment_pairs = [(row["comment_id"], row["content_clean"]) for row in batch_rows]
    try:
        items = call_llm_batch(system_prompt, comment_pairs)
        for item in items:
            label = CommentLabel(**item.model_dump(exclude={"comment_id"}))
            save_label_record(item.comment_id, label, cache, "llm", "llm_batch")
            original_text = next(row["content_clean"] for row in batch_rows if row["comment_id"] == item.comment_id)
            text_cache[original_text] = label.model_dump()
        route_counter["llm_success"] += len(items)
        return len(items), 0
    except BatchValidationError as exc:
        print(f"\n  批量输出异常，降级为单条重试: {exc}")
        route_counter["llm_batch_validation_fallback"] += len(batch_rows)
        return process_rows_individually(system_prompt, batch_rows, cache, text_cache, route_counter)
    except Exception as exc:
        if is_transient_error(exc):
            append_failure_log([comment_id for comment_id, _ in comment_pairs], exc, "transient_batch_failure")
            raise TransientLabelError(str(exc)) from exc

        append_failure_log([comment_id for comment_id, _ in comment_pairs], exc, "non_transient_batch_failure")
        print(f"\n  批量失败，降级为单条重试: {exc}")
        route_counter["llm_batch_error_fallback"] += len(batch_rows)
        return process_rows_individually(system_prompt, batch_rows, cache, text_cache, route_counter)


def export_labeled_csv(df: pd.DataFrame, cache: dict[str, dict]) -> int:
    if cache:
        label_df = pd.DataFrame(list(cache.values()))
        label_df["comment_id"] = label_df["comment_id"].astype(str)
        label_df["module_tags"] = label_df["module_tags"].apply(
            lambda value: ",".join(value) if isinstance(value, list) else value
        )
        label_df_slim = label_df[EXPORT_FIELDS].copy()
    else:
        label_df_slim = pd.DataFrame(columns=EXPORT_FIELDS)

    df = df.copy()
    df["comment_id_str"] = df["comment_id"].astype(str)
    label_df_slim.rename(columns={"comment_id": "comment_id_str"}, inplace=True)
    df_result = df.merge(label_df_slim, on="comment_id_str", how="left")
    df_result.drop(columns=["comment_id_str"], inplace=True)
    df_result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    labeled_count = int(df_result["sentiment"].notna().sum())
    print(f"\n已保存: {OUTPUT_PATH}")
    print(f"  总行数: {len(df_result)} | 已标注: {labeled_count}")
    return labeled_count


def main() -> int:
    print("=" * 50)
    print("分层标注管线")
    print("=" * 50)

    topic = get_topic()
    game = topic.get("game", "未知游戏")
    target_keyword = topic.get("target", "目标角色")
    target_aliases = topic.get("target_aliases", [])
    batch_size = max(1, int(_llm_cfg.get("batch_size", 5)))
    enable_rule_router = bool(_llm_cfg.get("enable_rule_router", True))
    enable_text_reuse = bool(_llm_cfg.get("enable_text_reuse", True))

    print("\n项目配置:")
    print(f"  游戏: {game}")
    print(f"  目标: {target_keyword}")
    print(f"  模型: {MODEL}")
    print(f"  批大小: {batch_size}")
    print(f"  规则预标: {enable_rule_router}")
    print(f"  文本复用: {enable_text_reuse}")

    df = pd.read_csv(INPUT_PATH, parse_dates=["comment_time"])
    df_valid = df[df["is_empty"] == 0].copy()
    df_valid["comment_id"] = df_valid["comment_id"].astype(str)
    df_valid["content_clean"] = df_valid["content_clean"].fillna("").astype(str)
    print(f"\n总评论: {len(df)} | 有效评论: {len(df_valid)}")

    system_prompt = build_system_prompt(game, target_keyword, target_aliases, batch_mode=True)

    print("\n检查缓存...")
    cache = load_cache()
    text_cache = build_text_reuse_cache(df_valid, cache)
    route_counter: Counter = Counter()
    reason_counter: Counter = Counter()

    llm_rows: list[dict] = []
    for _, row in df_valid.iterrows():
        comment_id = row["comment_id"]
        content_clean = row["content_clean"].strip()
        if not content_clean:
            continue

        if comment_id in cache:
            route_counter["cached"] += 1
            continue

        if enable_text_reuse and content_clean in text_cache:
            reused_label = CommentLabel(**text_cache[content_clean])
            save_label_record(comment_id, reused_label, cache, "reuse", "reuse_exact_text")
            route_counter["reuse"] += 1
            reason_counter["reuse_exact_text"] += 1
            continue

        if enable_rule_router:
            decision = build_rule_label(content_clean, target_keyword, target_aliases)
            if decision is not None:
                label = CommentLabel(**decision.label_data)
                save_label_record(comment_id, label, cache, "rule", decision.route_reason)
                text_cache[content_clean] = label.model_dump()
                route_counter["rule"] += 1
                reason_counter[decision.route_reason] += 1
                continue

        llm_rows.append({"comment_id": comment_id, "content_clean": content_clean})
        route_counter["llm_pending"] += 1

    print("\n分流结果:")
    print(f"  直接复用缓存: {route_counter['cached']}")
    print(f"  规则预标:     {route_counter['rule']}")
    print(f"  文本复用:     {route_counter['reuse']}")
    print(f"  待送 LLM:     {route_counter['llm_pending']}")

    interrupted = False
    success = 0
    failed = 0
    interval = float(_llm_cfg.get("request_interval_seconds", 0))
    total_batches = (len(llm_rows) + batch_size - 1) // batch_size if llm_rows else 0

    if llm_rows:
        print("\n开始 LLM 兜底标注...")
        for batch_rows in tqdm(list(chunked(llm_rows, batch_size)), total=total_batches, desc="LLM 批次"):
            try:
                batch_success, batch_failed = process_batch(system_prompt, batch_rows, cache, text_cache, route_counter)
                success += batch_success
                failed += batch_failed
            except TransientLabelError as exc:
                interrupted = True
                cooldown = int(_llm_cfg.get("transient_error_cooldown_seconds", 60))
                print(f"\n  检测到暂时性错误，停止本轮以保护缓存质量: {exc}")
                print(f"  建议稍后重跑，当前等待 {cooldown} 秒后退出。")
                if cooldown > 0:
                    time.sleep(cooldown)
                break

            if interval > 0:
                time.sleep(interval)

    remaining = sum(1 for row in llm_rows if row["comment_id"] not in cache)
    print(f"\nLLM 阶段结束: 成功={success} | 跳过={failed} | 剩余={remaining}")

    export_labeled_csv(df, cache)
    write_routing_report(route_counter, reason_counter, len(df_valid), len(cache), remaining)

    if interrupted or remaining > 0:
        print("\n本轮未完成全部标注，已保留成功缓存。稍后重跑即可续跑。")
        return 2

    print("\n完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
