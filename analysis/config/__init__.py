# -*- coding: utf-8 -*-
"""
项目配置加载器。
从 config/project.yaml 读取项目级配置，提供统一访问入口。
"""

import os
from typing import Any

import yaml

CONFIG_DIR = os.path.dirname(__file__)
PROJECT_YAML = os.path.join(CONFIG_DIR, "project.yaml")

_config_cache: dict | None = None


def load_project_config(path: str = PROJECT_YAML) -> dict[str, Any]:
    """加载项目配置，带内存缓存。"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)
    return _config_cache


def get_topic() -> dict[str, Any]:
    """返回 topic 配置段: game, target, target_aliases。"""
    return load_project_config().get("topic", {})


def get_paths() -> dict[str, str]:
    """返回 paths 配置段。"""
    return load_project_config().get("paths", {})


def get_llm_config() -> dict[str, Any]:
    """返回 llm 配置段。"""
    return load_project_config().get("llm", {})


def get_competitors() -> list[dict]:
    """返回竞品列表。"""
    return load_project_config().get("competitors", [])


def get_analysis_config() -> dict[str, Any]:
    """返回 analysis 配置段。"""
    return load_project_config().get("analysis", {})


def get_agents_config() -> dict[str, Any]:
    """返回 agents 配置段。"""
    return load_project_config().get("agents", {})
