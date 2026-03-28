from __future__ import annotations

import json
from collections import Counter

import pandas as pd

from config.labels import MODULE_TAGS

from .tools import parse_tag_list, safe_excerpt


def _module_label(tag: str) -> str:
    return MODULE_TAGS.get(tag, {}).get("label", tag)


def _top_module_pairs(series: pd.Series, limit: int) -> list[dict[str, object]]:
    counter: Counter[str] = Counter()
    for value in series:
        counter.update(parse_tag_list(value))
    return [{"module": _module_label(tag), "count": count} for tag, count in counter.most_common(limit)]


def _select_examples(
    bucket_name: str,
    frame: pd.DataFrame,
    limit: int,
    used_ids: set[str],
) -> list[dict[str, object]]:
    if frame.empty or limit <= 0:
        return []

    ranking_columns = [col for col in ["like_count", "content_clean_length", "content_length"] if col in frame.columns]
    if ranking_columns:
        frame = frame.sort_values(by=ranking_columns, ascending=False, na_position="last")

    examples: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        comment_id = str(row.get("comment_id", ""))
        if not comment_id or comment_id in used_ids:
            continue

        used_ids.add(comment_id)
        examples.append(
            {
                "bucket": bucket_name,
                "comment_id": comment_id,
                "sentiment": str(row.get("sentiment", "")),
                "module_tags": [_module_label(tag) for tag in parse_tag_list(row.get("module_tags"))],
                "is_target_related": bool(row.get("is_target_related", False)),
                "churn_risk": str(row.get("churn_risk", "")),
                "pay_risk": str(row.get("pay_risk", "")),
                "summary_reason": str(row.get("summary_reason", "")),
                "content": safe_excerpt(row.get("content_clean") or row.get("content"), max_length=120),
            }
        )
        if len(examples) >= limit:
            break

    return examples


def build_commentary_payload(
    df: pd.DataFrame,
    negative_sentiments: list[str],
    topic_display_name: str,
    target_name: str,
    review_queue_df: pd.DataFrame | None,
    config: dict,
) -> dict[str, object]:
    sample_size = int(config.get("sample_size_per_bucket", 6))
    max_review_examples = int(config.get("max_review_examples", 6))
    top_module_limit = int(config.get("top_module_limit", 5))

    labeled_df = df[df["sentiment"].notna()].copy()
    negative_df = labeled_df[labeled_df["sentiment"].isin(negative_sentiments)]
    mixed_df = labeled_df[labeled_df["sentiment"] == "mixed"]
    target_df = labeled_df[labeled_df["is_target_related"]]
    target_negative_df = target_df[target_df["sentiment"].isin(negative_sentiments)]
    high_risk_df = labeled_df[
        (labeled_df.get("churn_risk", pd.Series(dtype=str)).fillna("") == "high")
        | (labeled_df.get("pay_risk", pd.Series(dtype=str)).fillna("") == "high")
    ]
    negative_without_module_df = negative_df[negative_df["module_tags_list"].apply(len) == 0]
    target_positive_df = target_df[target_df["sentiment"] == "positive"]

    used_ids: set[str] = set()
    example_buckets: list[dict[str, object]] = []
    example_buckets.extend(_select_examples("negative_with_module", negative_df[negative_df["module_tags_list"].apply(len) > 0], sample_size, used_ids))
    example_buckets.extend(_select_examples("negative_without_module", negative_without_module_df, sample_size, used_ids))
    example_buckets.extend(_select_examples("mixed", mixed_df, sample_size, used_ids))
    example_buckets.extend(_select_examples("target_negative", target_negative_df, sample_size, used_ids))
    example_buckets.extend(_select_examples("target_positive", target_positive_df, sample_size, used_ids))
    example_buckets.extend(_select_examples("high_risk", high_risk_df, sample_size, used_ids))

    if review_queue_df is not None and not review_queue_df.empty:
        review_queue_df = review_queue_df.copy()
        if "comment_id" in review_queue_df.columns:
            review_queue_df["comment_id"] = review_queue_df["comment_id"].astype(str)
        merged = labeled_df.merge(
            review_queue_df[["comment_id", "priority", "review_reason"]],
            on="comment_id",
            how="inner",
        )
        example_buckets.extend(_select_examples("review_queue", merged, max_review_examples, used_ids))

    payload = {
        "topic": topic_display_name,
        "target": target_name,
        "summary": {
            "labeled_comments": int(len(labeled_df)),
            "negative_comments": int(len(negative_df)),
            "negative_ratio": round((len(negative_df) / len(labeled_df)) if len(labeled_df) else 0, 4),
            "target_related_comments": int(len(target_df)),
            "target_negative_comments": int(len(target_negative_df)),
            "high_churn_risk": int((labeled_df.get("churn_risk", pd.Series(dtype=str)).fillna("") == "high").sum()),
            "high_pay_risk": int((labeled_df.get("pay_risk", pd.Series(dtype=str)).fillna("") == "high").sum()),
        },
        "sentiment_counts": {str(k): int(v) for k, v in labeled_df["sentiment"].value_counts().to_dict().items()},
        "label_source_counts": {str(k): int(v) for k, v in labeled_df["label_source"].fillna("unknown").value_counts().to_dict().items()},
        "top_negative_modules": _top_module_pairs(negative_df["module_tags"], top_module_limit),
        "top_target_negative_modules": _top_module_pairs(target_negative_df["module_tags"], top_module_limit),
        "review_queue_total": int(len(review_queue_df)) if review_queue_df is not None else 0,
        "sampled_examples": example_buckets,
    }
    return payload


def build_commentary_prompts(payload: dict[str, object]) -> tuple[str, str]:
    system_prompt = (
        "你是资深游戏用户研究分析师。"
        "你会收到一份基于结构化统计和代表性评论样本整理出的分析输入。"
        "请只基于提供的数据进行点评，不要虚构数字，不要重新计算未提供的指标。"
        "如果样本只能支持倾向性判断，要明确写出'基于样本观察'。"
        "输出使用中文 Markdown，控制在 4 个小节内：核心判断、情绪与原因、目标角色专项、风险与建议。"
    )

    user_prompt = "\n".join(
        [
            "请基于下面的专题分析输入，输出一段高质量的 LLM 点评。",
            "要求：",
            "1. 先给 2-4 条核心判断。",
            "2. 点评要引用已提供的数字和现象。",
            "3. 不要重复抄写原始 JSON。",
            "4. 适合直接贴进研究报告。",
            "",
            "分析输入：",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )
    return system_prompt, user_prompt
