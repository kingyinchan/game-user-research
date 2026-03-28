# -*- coding: utf-8 -*-
"""
小红书评论数据清洗管线。
自动检测 JSONL 目录下的 contents/comments 文件，标准化字段后导出 CSV。
"""

import glob
import json
import os
import re
import sys

import pandas as pd

from config import get_paths

# -- 路径（从 project.yaml 读取） --
ANALYSIS_DIR = os.path.dirname(__file__)
_paths = get_paths()
DATA_DIR = os.path.join(ANALYSIS_DIR, _paths.get("raw_data", "../crawler/MediaCrawler/data/xhs/jsonl"))
OUTPUT_DIR = os.path.join(ANALYSIS_DIR, _paths.get("cleaned_data", "cleaned_data"))
os.makedirs(OUTPUT_DIR, exist_ok=True)


def discover_files(data_dir: str) -> tuple[list[str], list[str]]:
    """扫描目录，按文件名前缀分组为 contents/comments 两类。"""
    contents_files = sorted(glob.glob(os.path.join(data_dir, "search_contents_*.jsonl")))
    comments_files = sorted(glob.glob(os.path.join(data_dir, "search_comments_*.jsonl")))
    return contents_files, comments_files


def load_jsonl(filepath: str) -> list[dict]:
    """读取单个 JSONL 文件，返回字典列表。"""
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"  [{os.path.basename(filepath)}] {len(records)} 条")
    return records


def load_all_jsonl(file_list: list[str]) -> list[dict]:
    """合并多个 JSONL 文件。"""
    all_records = []
    for fp in file_list:
        all_records.extend(load_jsonl(fp))
    return all_records


# ----------------------------------------------------------------
# 数值解析
# ----------------------------------------------------------------
def parse_count(value) -> int:
    """解析展示格式的数值: '2.2万' -> 22000, '278' -> 278。"""
    if not value or value == "":
        return 0
    value = str(value).strip()
    if "万" in value:
        return int(float(value.replace("万", "")) * 10000)
    try:
        return int(value)
    except ValueError:
        return 0


# ----------------------------------------------------------------
# 文本清洗
# ----------------------------------------------------------------
def _remove_xhs_emoji(text: str) -> str:
    """去除平台自定义表情，如 [哭惹R]。"""
    return re.sub(r"\[[\w\u4e00-\u9fff]+R?\]", "", text)


def _remove_at_mentions(text: str) -> str:
    return re.sub(r"@\S+", "", text)


def _remove_hashtags(text: str) -> str:
    """去除 #话题# 标签。"""
    return re.sub(r"#[^#]+\[话题\]#?", "", text)


def clean_text(text: str) -> str:
    """对单条文本执行完整清洗流程。"""
    if not text or pd.isna(text):
        return ""
    text = _remove_hashtags(text)
    text = _remove_xhs_emoji(text)
    text = _remove_at_mentions(text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ----------------------------------------------------------------
# 帖子处理
# ----------------------------------------------------------------
def process_contents(raw_data: list[dict]) -> pd.DataFrame:
    """标准化帖子数据。"""
    print("\n处理帖子数据...")
    df = pd.DataFrame(raw_data)

    # 时间戳（毫秒 -> datetime）
    df["publish_time"] = pd.to_datetime(df["time"], unit="ms")
    df["last_update"] = pd.to_datetime(df["last_update_time"], unit="ms")

    # 互动数值
    for col in ["liked_count", "collected_count", "comment_count", "share_count"]:
        df[col] = df[col].apply(parse_count)
    df["total_engagement"] = (
        df["liked_count"] + df["collected_count"] + df["comment_count"] + df["share_count"]
    )

    # 文本
    df["title_clean"] = df["title"].apply(clean_text)
    df["desc_clean"] = df["desc"].apply(clean_text)

    # 派生特征
    df["tag_count"] = df["tag_list"].apply(lambda x: len(x.split(",")) if x else 0)
    df["image_count"] = df["image_list"].apply(lambda x: len(x.split(",")) if x else 0)
    df["is_video"] = (df["type"] == "video").astype(int)

    cols = [
        "note_id", "type", "is_video", "title", "title_clean", "desc_clean",
        "publish_time", "nickname", "ip_location",
        "liked_count", "collected_count", "comment_count", "share_count", "total_engagement",
        "tag_list", "tag_count", "image_count", "note_url", "source_keyword",
    ]
    result = df[cols].copy()
    video_n = result["is_video"].sum()
    image_n = len(result) - video_n
    print(f"  完成: {len(result)} 条 | 视频={video_n} | 图文={image_n}")
    return result


# ----------------------------------------------------------------
# 评论处理
# ----------------------------------------------------------------
def process_comments(raw_data: list[dict]) -> pd.DataFrame:
    """标准化评论数据。"""
    print("\n处理评论数据...")
    df = pd.DataFrame(raw_data)

    # 时间
    df["comment_time"] = pd.to_datetime(df["create_time"], unit="ms")
    df["hour"] = df["comment_time"].dt.hour
    df["date"] = df["comment_time"].dt.date
    df["weekday"] = df["comment_time"].dt.day_name()

    # 数值
    df["like_count"] = df["like_count"].apply(parse_count)
    df["sub_comment_count"] = df["sub_comment_count"].apply(parse_count)

    # 文本
    df["content_clean"] = df["content"].apply(clean_text)
    df["content_length"] = df["content"].apply(lambda x: len(x) if x else 0)
    df["content_clean_length"] = df["content_clean"].apply(len)

    # 标记
    df["is_empty"] = (df["content_clean_length"] == 0).astype(int)
    df["is_root_comment"] = (df["parent_comment_id"] == 0).astype(int)
    df["has_picture"] = df["pictures"].apply(lambda x: 1 if x and len(str(x)) > 0 else 0)

    cols = [
        "comment_id", "note_id", "content", "content_clean",
        "comment_time", "hour", "date", "weekday",
        "nickname", "ip_location",
        "like_count", "sub_comment_count",
        "content_length", "content_clean_length", "is_empty",
        "is_root_comment", "has_picture", "parent_comment_id",
    ]
    result = df[cols].copy()
    valid = len(result[result["is_empty"] == 0])
    print(f"  完成: {len(result)} 条 | 有效={valid} | 空={result['is_empty'].sum()}")
    print(f"  一级评论={result['is_root_comment'].sum()} | 含图={result['has_picture'].sum()} | 地域数={result['ip_location'].nunique()}")
    return result


# ----------------------------------------------------------------
# 入口
# ----------------------------------------------------------------
def main(data_dir: str = DATA_DIR):
    print("=" * 50)
    print("小红书数据清洗管线")
    print("=" * 50)

    # 自动发现文件
    print(f"\n扫描目录: {data_dir}")
    contents_files, comments_files = discover_files(data_dir)
    if not contents_files and not comments_files:
        print(f"  未找到 JSONL 文件，请检查路径。")
        sys.exit(1)
    print(f"  发现 {len(contents_files)} 个帖子文件, {len(comments_files)} 个评论文件")

    # 合并加载
    print("\n加载原始数据...")
    contents_raw = load_all_jsonl(contents_files)
    comments_raw = load_all_jsonl(comments_files)

    # 去重（按主键）
    contents_raw = {r["note_id"]: r for r in contents_raw}.values()
    comments_raw = {r["comment_id"]: r for r in comments_raw}.values()
    contents_raw = list(contents_raw)
    comments_raw = list(comments_raw)
    print(f"  去重后: 帖子={len(contents_raw)}, 评论={len(comments_raw)}")

    # 处理
    df_contents = process_contents(contents_raw)
    df_comments = process_comments(comments_raw)

    # 导出
    print("\n导出 CSV...")
    contents_path = os.path.join(OUTPUT_DIR, "contents_cleaned.csv")
    comments_path = os.path.join(OUTPUT_DIR, "comments_cleaned.csv")
    df_contents.to_csv(contents_path, index=False, encoding="utf-8-sig")
    df_comments.to_csv(comments_path, index=False, encoding="utf-8-sig")
    print(f"  -> {contents_path}")
    print(f"  -> {comments_path}")

    # 概要
    print("\n--- 数据概要 ---")
    print(f"帖子总数:    {len(df_contents)}")
    print(f"评论总数:    {len(df_comments)}")
    print(f"涉及帖子:    {df_comments['note_id'].nunique()}")
    print(f"总点赞:      {df_contents['liked_count'].sum():,}")
    print(f"总互动:      {df_contents['total_engagement'].sum():,}")
    print(f"时间范围:    {df_comments['comment_time'].min()} ~ {df_comments['comment_time'].max()}")
    print("\n完成。")
    return df_contents, df_comments


if __name__ == "__main__":
    # 支持命令行传入自定义数据目录
    custom_dir = sys.argv[1] if len(sys.argv) > 1 else DATA_DIR
    main(custom_dir)
