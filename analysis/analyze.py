# -*- coding: utf-8 -*-
"""
游戏评论结构化标注结果分析。
读取 comments_labeled.csv，输出分析摘要和可视化图表。

所有配置从 config/project.yaml 读取，不硬编码任何游戏/版本/角色信息。
"""

import ast
import json
import os
import sys
from collections import Counter

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import get_topic, get_paths, get_analysis_config
from config.labels import MODULE_TAGS

# -- 中文字体 --
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# -- 配色 --
C = {
    "primary": "#FF6B35",
    "secondary": "#7B68EE",
    "accent1": "#FFB347",
    "accent2": "#4ECDC4",
    "accent3": "#FF6B6B",
    "accent4": "#45B7D1",
    "bg_dark": "#1a1a2e",
    "bg_card": "#16213e",
    "text": "#e0e0e0",
    "grid": "#333355",
}
PALETTE = [
    "#FF6B35", "#7B68EE", "#4ECDC4", "#FFB347", "#FF6B6B",
    "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8",
]

# -- 路径 --
ANALYSIS_DIR = os.path.dirname(__file__)
_paths = get_paths()
INPUT_PATH = os.path.join(ANALYSIS_DIR, _paths.get("cleaned_data", "cleaned_data"), "comments_labeled.csv")
OUTPUT_DIR = os.path.join(ANALYSIS_DIR, _paths.get("output", "output"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -- module_tags 中文映射 --
TAG_LABELS = {k: v["label"] for k, v in MODULE_TAGS.items()}


# ----------------------------------------------------------------
# 数据加载与预处理
# ----------------------------------------------------------------

def load_data(filepath: str) -> pd.DataFrame:
    """加载标注结果 CSV，校验必需字段。"""
    if not os.path.exists(filepath):
        print(f"错误: 文件不存在 -> {filepath}")
        sys.exit(1)

    df = pd.read_csv(filepath)

    required = ["comment_id", "sentiment"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        print(f"错误: 缺少必需字段 -> {missing}")
        sys.exit(1)

    # 字段别名兼容: is_topic_related <-> is_target_related
    if "is_target_related" in df.columns and "is_topic_related" not in df.columns:
        df["is_topic_related"] = df["is_target_related"]
    elif "is_topic_related" in df.columns and "is_target_related" not in df.columns:
        df["is_target_related"] = df["is_topic_related"]

    print(f"  已加载 {len(df)} 条记录")
    return df


def normalize_boolean(series: pd.Series) -> pd.Series:
    """将布尔/字符串列统一转为 bool。兼容 True/False/'true'/'false'/1/0/NaN。"""
    def _convert(val):
        if pd.isna(val):
            return False
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return bool(val)
        return str(val).strip().lower() in ("true", "1", "yes")
    return series.apply(_convert)


def parse_module_tags(series: pd.Series) -> pd.Series:
    """
    解析 module_tags 列为 Python list。
    兼容格式: "['a','b']" / '["a","b"]' / "a,b" / "a" / NaN
    """
    def _parse(val):
        if pd.isna(val) or val == "":
            return []
        val = str(val).strip()
        # 尝试 JSON 数组
        if val.startswith("["):
            try:
                result = json.loads(val)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
            # 尝试 Python literal
            try:
                result = ast.literal_eval(val)
                if isinstance(result, list):
                    return result
            except (ValueError, SyntaxError):
                pass
        # 逗号分隔
        if "," in val:
            return [t.strip() for t in val.split(",") if t.strip()]
        # 单个标签
        return [val] if val else []

    return series.apply(_parse)


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """预处理: 布尔列归一化 + module_tags 解析。"""
    bool_cols = ["is_version_related", "is_target_related", "is_topic_related"]
    for col in bool_cols:
        if col in df.columns:
            df[col] = normalize_boolean(df[col])

    if "module_tags" in df.columns:
        df["module_tags_list"] = parse_module_tags(df["module_tags"])
    else:
        df["module_tags_list"] = [[] for _ in range(len(df))]

    return df


# ----------------------------------------------------------------
# 分析函数
# ----------------------------------------------------------------

def analyze_negative_modules(df: pd.DataFrame, neg_sentiments: list[str]) -> pd.Series:
    """
    统计版本相关负面评论中各 module_tag 的出现次数。
    返回 tag -> count 的 Series（降序）。
    """
    mask = df["sentiment"].isin(neg_sentiments)
    if "is_version_related" in df.columns:
        mask = mask & df["is_version_related"]

    neg_df = df[mask]
    tag_counter = Counter()
    for tags in neg_df["module_tags_list"]:
        for t in tags:
            tag_counter[t] += 1

    result = pd.Series(tag_counter, name="count").sort_values(ascending=False)
    return result


def analyze_topic_negative_modules(df: pd.DataFrame, neg_sentiments: list[str]) -> pd.Series:
    """
    统计专题相关（is_topic_related）负面评论中各 module_tag 出现次数。
    """
    mask = df["sentiment"].isin(neg_sentiments)
    if "is_topic_related" in df.columns:
        mask = mask & df["is_topic_related"]

    topic_neg = df[mask]
    tag_counter = Counter()
    for tags in topic_neg["module_tags_list"]:
        for t in tags:
            tag_counter[t] += 1

    result = pd.Series(tag_counter, name="count").sort_values(ascending=False)
    return result


def analyze_risk_flags(df: pd.DataFrame) -> dict[str, pd.Series]:
    """统计 churn_risk 和 pay_risk 的分布。"""
    result = {}
    for col in ["churn_risk", "pay_risk"]:
        if col in df.columns:
            result[col] = df[col].fillna("unknown").value_counts()
    return result


def analyze_sentiment_distribution(df: pd.DataFrame) -> pd.Series:
    """统计全量评论的 sentiment 分布。"""
    return df["sentiment"].fillna("unknown").value_counts()


# ----------------------------------------------------------------
# 可视化
# ----------------------------------------------------------------

def _style_fig(fig, title=""):
    fig.patch.set_facecolor(C["bg_dark"])
    if title:
        fig.suptitle(title, fontsize=16, fontweight="bold", color=C["text"], y=0.98)


def _style_ax(ax, title="", xlabel="", ylabel=""):
    ax.set_facecolor(C["bg_card"])
    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", color=C["text"], pad=10)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10, color=C["text"])
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10, color=C["text"])
    ax.tick_params(colors=C["text"], labelsize=9)
    ax.grid(True, alpha=0.15, color=C["grid"], axis="y")
    for spine in ax.spines.values():
        spine.set_color(C["grid"])
        spine.set_linewidth(0.5)


def _save(fig, name: str, output_dir: str) -> str:
    path = os.path.join(output_dir, f"{name}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  已保存: {name}.png")
    return path


def plot_bar_chart(
    data: pd.Series,
    title: str,
    filename: str,
    output_dir: str,
    xlabel: str = "数量",
    ylabel: str = "",
    translate_tags: bool = True,
) -> str | None:
    """通用横向条形图。translate_tags=True 时将 tag key 转为中文。"""
    if data.empty:
        print(f"  跳过: {filename} (无数据)")
        return None

    fig, ax = plt.subplots(figsize=(10, max(4, len(data) * 0.5 + 1)))
    _style_fig(fig)
    _style_ax(ax, title=title, xlabel=xlabel, ylabel=ylabel)

    labels = data.index.tolist()
    if translate_tags:
        labels = [TAG_LABELS.get(l, l) for l in labels]
    values = data.values

    y_pos = range(len(labels))
    colors = PALETTE[:len(labels)]
    bars = ax.barh(y_pos, values, color=colors, edgecolor="white", linewidth=0.3, height=0.6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()

    total = values.sum()
    for bar, val in zip(bars, values):
        pct = val / total * 100 if total > 0 else 0
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{val} ({pct:.1f}%)", va="center", fontsize=9, color=C["text"])

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    return _save(fig, filename, output_dir)


def plot_sentiment_distribution(
    data: pd.Series,
    title: str,
    output_dir: str,
) -> str | None:
    """情感分布饼图 + 条形图组合。"""
    if data.empty:
        print("  跳过: sentiment_distribution (无数据)")
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    _style_fig(fig, title)

    # 配色映射
    sent_colors = {
        "positive": C["accent2"],
        "neutral": C["accent4"],
        "negative": C["accent3"],
        "mixed": C["accent1"],
        "unknown": C["grid"],
    }

    labels = data.index.tolist()
    values = data.values
    colors = [sent_colors.get(l, C["secondary"]) for l in labels]
    cn_labels = {
        "positive": "正面", "neutral": "中性",
        "negative": "负面", "mixed": "混合", "unknown": "未知"
    }

    # 左: 饼图
    ax = axes[0]
    _style_ax(ax, "占比")
    display_labels = [cn_labels.get(l, l) for l in labels]
    wedges, texts, autotexts = ax.pie(
        values, labels=display_labels, autopct="%1.1f%%",
        colors=colors, startangle=90,
        textprops={"color": C["text"], "fontsize": 11},
    )
    for t in autotexts:
        t.set_fontweight("bold")

    # 右: 条形图
    ax = axes[1]
    _style_ax(ax, "数量", "评论数", "")
    bars = ax.barh(range(len(labels)), values, color=colors,
                   edgecolor="white", linewidth=0.3, height=0.6)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(display_labels, fontsize=10)
    ax.invert_yaxis()
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=10, fontweight="bold", color=C["text"])

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    return _save(fig, "sentiment_distribution", output_dir)


def plot_risk_distribution(
    risk_data: dict[str, pd.Series],
    title: str,
    output_dir: str,
) -> str | None:
    """churn_risk + pay_risk 并排条形图。"""
    if not risk_data:
        print("  跳过: risk_distribution (无数据)")
        return None

    n_plots = len(risk_data)
    fig, axes = plt.subplots(1, n_plots, figsize=(7 * n_plots, 5))
    if n_plots == 1:
        axes = [axes]
    _style_fig(fig, title)

    risk_cn = {"churn_risk": "流失风险", "pay_risk": "付费风险"}
    level_cn = {"low": "低", "medium": "中", "high": "高", "unknown": "未知"}
    level_colors = {"low": C["accent2"], "medium": C["accent1"], "high": C["accent3"], "unknown": C["grid"]}

    for ax, (risk_name, data) in zip(axes, risk_data.items()):
        _style_ax(ax, risk_cn.get(risk_name, risk_name), "评论数", "")
        labels = data.index.tolist()
        values = data.values
        display = [level_cn.get(l, l) for l in labels]
        colors = [level_colors.get(l, C["secondary"]) for l in labels]

        bars = ax.bar(display, values, color=colors, edgecolor="white", linewidth=0.5, width=0.5)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    str(val), ha="center", fontsize=11, fontweight="bold", color=C["text"])

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    return _save(fig, "risk_distribution", output_dir)


# ----------------------------------------------------------------
# 摘要打印
# ----------------------------------------------------------------

def print_summary(
    df: pd.DataFrame,
    neg_modules: pd.Series,
    topic_neg_modules: pd.Series,
    sentiment_dist: pd.Series,
    risk_data: dict[str, pd.Series],
    config: dict,
):
    """打印终端分析摘要。"""
    neg_sentiments = config.get("negative_sentiments", ["negative", "mixed"])
    topic_name = config.get("topic_name", "目标")

    neg_mask = df["sentiment"].isin(neg_sentiments)
    ver_mask = df.get("is_version_related", pd.Series(False, index=df.index))
    topic_mask = df.get("is_topic_related", pd.Series(False, index=df.index))

    print("\n" + "=" * 60)
    print(f"  {config.get('display_name', '游戏评论分析报告')}")
    print("=" * 60)

    print(f"\n--- 基础统计 ---")
    print(f"  总评论数:          {len(df)}")
    print(f"  已标注:            {df['sentiment'].notna().sum()}")
    print(f"  版本相关:          {ver_mask.sum()}")
    print(f"  {topic_name}相关:  {topic_mask.sum()}")

    print(f"\n--- 情感分布 ---")
    for sent, cnt in sentiment_dist.items():
        pct = cnt / len(df) * 100
        print(f"  {sent:12s}: {cnt:4d} ({pct:.1f}%)")

    neg_total = neg_mask.sum()
    ver_neg = (neg_mask & ver_mask).sum()
    print(f"\n--- 负面分析 ---")
    print(f"  负面评论总数:      {neg_total}")
    print(f"  版本相关负面:      {ver_neg}")

    if not neg_modules.empty:
        print(f"\n--- 版本相关负面: 模块分布 ---")
        for tag, cnt in neg_modules.items():
            label = TAG_LABELS.get(tag, tag)
            print(f"  {label:16s}: {cnt}")

    if not topic_neg_modules.empty:
        print(f"\n--- {topic_name}相关负面: 模块分布 ---")
        for tag, cnt in topic_neg_modules.items():
            label = TAG_LABELS.get(tag, tag)
            print(f"  {label:16s}: {cnt}")

    for risk_name, data in risk_data.items():
        risk_cn = {"churn_risk": "流失风险", "pay_risk": "付费风险"}
        print(f"\n--- {risk_cn.get(risk_name, risk_name)} ---")
        for level, cnt in data.items():
            print(f"  {level:12s}: {cnt}")

    print("\n" + "=" * 60)


# ----------------------------------------------------------------
# 入口
# ----------------------------------------------------------------

def main():
    print("=" * 50)
    print("标注结果分析管线")
    print("=" * 50)

    # 加载配置
    topic = get_topic()
    analysis_cfg = get_analysis_config()

    config = {
        "display_name": topic.get("display_name", f"{topic.get('game', '')} 分析报告"),
        "game_name": topic.get("game", ""),
        "version_name": topic.get("version", ""),
        "topic_name": topic.get("target", "目标"),
        "negative_sentiments": analysis_cfg.get("negative_sentiments", ["negative", "mixed"]),
    }

    neg_sentiments = config["negative_sentiments"]
    print(f"\n项目: {config['display_name']}")
    print(f"负面标签: {neg_sentiments}")

    # 加载数据
    print(f"\n加载数据: {INPUT_PATH}")
    df = load_data(INPUT_PATH)
    df = preprocess(df)

    # 只分析已标注的行
    df_labeled = df[df["sentiment"].notna()].copy()
    print(f"  已标注: {len(df_labeled)} 条")

    if len(df_labeled) == 0:
        print("无已标注数据，退出。")
        return

    # 执行分析
    print("\n执行分析...")
    sentiment_dist = analyze_sentiment_distribution(df_labeled)
    neg_modules = analyze_negative_modules(df_labeled, neg_sentiments)
    topic_neg_modules = analyze_topic_negative_modules(df_labeled, neg_sentiments)
    risk_data = analyze_risk_flags(df_labeled)

    # 打印摘要
    print_summary(df_labeled, neg_modules, topic_neg_modules, sentiment_dist, risk_data, config)

    # 生成图表
    print(f"\n生成图表 -> {OUTPUT_DIR}")

    plot_sentiment_distribution(
        sentiment_dist,
        f"{config['display_name']} - 情感分布",
        OUTPUT_DIR,
    )

    plot_bar_chart(
        neg_modules,
        f"版本相关负面评论 - 模块分布",
        "negative_module_distribution",
        OUTPUT_DIR,
    )

    plot_bar_chart(
        topic_neg_modules,
        f"「{config['topic_name']}」相关负面评论 - 模块分布",
        "topic_negative_distribution",
        OUTPUT_DIR,
    )

    plot_risk_distribution(
        risk_data,
        f"{config['display_name']} - 风险分布",
        OUTPUT_DIR,
    )

    print(f"\n完成。图表已保存到: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
