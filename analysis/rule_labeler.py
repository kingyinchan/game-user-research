# -*- coding: utf-8 -*-
"""规则预标引擎：用于筛出高置信、低成本样本。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from config.labels import MODULE_TAGS


SOCIAL_KEYWORDS = [
    "关注",
    "互关",
    "点赞",
    "转发",
    "更新",
    "混剪",
    "灌注",
    "主页",
    "私信",
    "私我",
    "链接",
]

QUESTION_KEYWORDS = [
    "吗",
    "?",
    "？",
    "怎么",
    "如何",
    "为什么",
    "啥",
    "什么",
    "求问",
    "想问",
]

POSITIVE_KEYWORDS = [
    "喜欢",
    "可爱",
    "好看",
    "真香",
    "想抽",
    "必抽",
    "爱了",
    "老婆",
    "老公",
    "香",
    "期待",
    "入坑",
]

NEGATIVE_KEYWORDS = [
    "不行",
    "难受",
    "失望",
    "垃圾",
    "讨厌",
    "劝退",
    "烦",
    "无语",
    "拉胯",
    "难绷",
]

VERSION_KEYWORDS = [
    "版本",
    "前瞻",
    "更新",
    "维护",
    "上线",
    "复刻",
    "卡池",
    "上半",
    "下半",
]

PERFORMANCE_NEGATIVE = [
    "卡",
    "卡顿",
    "闪退",
    "掉帧",
    "发热",
    "崩溃",
    "优化差",
    "优化烂",
]

PERFORMANCE_POSITIVE = [
    "流畅",
    "不卡",
    "丝滑",
    "稳",
    "优化好了",
]

CHURN_HIGH_KEYWORDS = [
    "弃坑",
    "退坑",
    "卸载",
    "不玩了",
]

CHURN_MEDIUM_KEYWORDS = [
    "玩不动",
    "太肝",
    "累了",
    "没时间",
    "纠结要不要入坑",
]

PAY_HIGH_KEYWORDS = [
    "太氪",
    "骗氪",
    "不充了",
    "不值得充",
]

PAY_MEDIUM_KEYWORDS = [
    "没石头",
    "歪了",
    "抽不起",
    "攒不动",
]


@dataclass
class RuleDecision:
    label_data: dict
    route_reason: str


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def count_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def extract_module_tags(text: str) -> list[str]:
    tags: list[str] = []
    for tag, meta in MODULE_TAGS.items():
        for keyword in meta.get("keywords_hint", []):
            if keyword in text:
                tags.append(tag)
                break

    if ("抽" in text or "老婆" in text or "老公" in text or "可爱" in text) and "gacha_character" not in tags:
        tags.append("gacha_character")
    if contains_any(text, PERFORMANCE_NEGATIVE + PERFORMANCE_POSITIVE) and "performance_bug" not in tags:
        tags.append("performance_bug")
    return tags


def detect_version_related(text: str) -> bool:
    if re.search(r"\b\d+\.\d+\b", text):
        return True
    return contains_any(text, VERSION_KEYWORDS)


def detect_target_related(text: str, target_keyword: str, target_aliases: list[str] | None = None) -> bool:
    names = [target_keyword] + list(target_aliases or [])
    return any(name and name in text for name in names)


def build_rule_label(text: str, target_keyword: str, target_aliases: list[str] | None = None) -> RuleDecision | None:
    """命中高置信规则时返回完整标签。"""
    text = str(text or "").strip()
    if not text:
        return RuleDecision(
            label_data={
                "sentiment": "neutral",
                "module_tags": [],
                "is_version_related": False,
                "is_target_related": False,
                "churn_risk": "low",
                "pay_risk": "low",
                "summary_reason": "空文本，无有效信息。",
            },
            route_reason="rule_empty_text",
        )

    is_version_related = detect_version_related(text)
    is_target_related = detect_target_related(text, target_keyword, target_aliases)
    module_tags = extract_module_tags(text)

    positive_hits = count_hits(text, POSITIVE_KEYWORDS)
    negative_hits = count_hits(text, NEGATIVE_KEYWORDS)
    question_like = text.endswith("?") or text.endswith("？") or contains_any(text, QUESTION_KEYWORDS)

    if contains_any(text, CHURN_HIGH_KEYWORDS):
        return RuleDecision(
            label_data={
                "sentiment": "negative",
                "module_tags": module_tags or ["progression_resource"],
                "is_version_related": is_version_related,
                "is_target_related": is_target_related,
                "churn_risk": "high",
                "pay_risk": "low",
                "summary_reason": "出现弃坑/卸载等强流失信号。",
            },
            route_reason="rule_churn_high",
        )

    if contains_any(text, PAY_HIGH_KEYWORDS):
        return RuleDecision(
            label_data={
                "sentiment": "negative",
                "module_tags": module_tags or ["gacha_character"],
                "is_version_related": is_version_related,
                "is_target_related": is_target_related,
                "churn_risk": "low",
                "pay_risk": "high",
                "summary_reason": "出现明显的高付费负面态度。",
            },
            route_reason="rule_pay_high",
        )

    if contains_any(text, PERFORMANCE_NEGATIVE):
        return RuleDecision(
            label_data={
                "sentiment": "negative",
                "module_tags": list(dict.fromkeys(module_tags or ["performance_bug"])),
                "is_version_related": is_version_related,
                "is_target_related": is_target_related,
                "churn_risk": "medium" if contains_any(text, CHURN_MEDIUM_KEYWORDS) else "low",
                "pay_risk": "low",
                "summary_reason": "明显在讨论性能/优化负面体验。",
            },
            route_reason="rule_performance_negative",
        )

    if contains_any(text, PERFORMANCE_POSITIVE) and negative_hits == 0:
        return RuleDecision(
            label_data={
                "sentiment": "positive",
                "module_tags": list(dict.fromkeys(module_tags or ["performance_bug"])),
                "is_version_related": is_version_related,
                "is_target_related": is_target_related,
                "churn_risk": "low",
                "pay_risk": "low",
                "summary_reason": "明显在讨论性能/画面正面体验。",
            },
            route_reason="rule_performance_positive",
        )

    if is_target_related and positive_hits > 0 and negative_hits == 0:
        return RuleDecision(
            label_data={
                "sentiment": "positive",
                "module_tags": list(dict.fromkeys(module_tags or ["gacha_character"])),
                "is_version_related": is_version_related,
                "is_target_related": True,
                "churn_risk": "low",
                "pay_risk": "medium" if contains_any(text, PAY_MEDIUM_KEYWORDS) else "low",
                "summary_reason": "高置信目标角色正向表达。",
            },
            route_reason="rule_target_positive",
        )

    if question_like and positive_hits == 0 and negative_hits == 0:
        return RuleDecision(
            label_data={
                "sentiment": "neutral",
                "module_tags": module_tags,
                "is_version_related": is_version_related,
                "is_target_related": is_target_related,
                "churn_risk": "low",
                "pay_risk": "low",
                "summary_reason": "高置信提问/咨询型评论。",
            },
            route_reason="rule_neutral_question",
        )

    if contains_any(text, SOCIAL_KEYWORDS) and positive_hits == 0 and negative_hits == 0 and not module_tags:
        return RuleDecision(
            label_data={
                "sentiment": "neutral",
                "module_tags": [],
                "is_version_related": False,
                "is_target_related": False,
                "churn_risk": "low",
                "pay_risk": "low",
                "summary_reason": "社交互动/引流类文本，非有效讨论。",
            },
            route_reason="rule_social_noise",
        )

    return None
