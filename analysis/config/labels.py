# -*- coding: utf-8 -*-
"""
结构化标签体系定义。
用于 LLM 对单条小红书评论进行标注，输出结构化 JSON。

设计原则:
  - 每个字段有明确的判断标准，减少 LLM 幻觉
  - module_tags 允许多选，一条评论可能同时涉及多个模块
  - churn_risk / pay_risk 基于文本中显性信号判断，不做过度推断
  - summary_reason 要求 LLM 用一句话解释标注理由，便于人工抽检
"""

# ================================================================
# 1. sentiment - 情感倾向
# ================================================================
# 判断标准:
#   positive  - 明确表达喜欢、赞美、期待、满意
#   neutral   - 纯提问、客观描述、无情感倾向的陈述
#   negative  - 明确表达不满、失望、批评、抱怨
#   mixed     - 同一条评论中同时包含正面和负面表达
#
# 边界案例:
#   "建模好看但强度太低" -> mixed (外观正面 + 强度负面)
#   "好想抽但是没石头了" -> mixed (期待正面 + 资源不足负面)
#   "这是什么游戏"       -> neutral (纯提问)
#   "已死的心又动了"     -> positive (虽有"死"字，但整体表达被吸引)

SENTIMENT_VALUES = ["positive", "neutral", "negative", "mixed"]

SENTIMENT_RUBRIC = {
    "positive": "明确表达喜欢、赞美、期待、满意等正面情感。",
    "neutral": "纯提问、客观描述、无明显情感倾向。包括 @他人、纯转发、求资源等。",
    "negative": "明确表达不满、失望、批评、抱怨等负面情感。",
    "mixed": "同一条评论中同时包含正面和负面表达，无法归入单一倾向。",
}


# ================================================================
# 2. module_tags - 讨论模块标签（多选）
# ================================================================
# 判断标准: 评论实际讨论的游戏模块，非推测。一条评论可命中多个标签。
# 若评论与游戏模块完全无关（如纯社交互动），标记为空列表。
#
# 边界案例:
#   "西格莉卡好萌想抽"            -> ["gacha_character"] (角色+抽卡意愿)
#   "剧情太刀了但小橘子好可爱"    -> ["story_quest", "gacha_character"]
#   "手机玩怎么样"                -> ["performance"]
#   "求背景音乐"                  -> [] (与游戏模块无关)
#   "强度不行但是老婆就抽"        -> ["combat_strength", "gacha_character"]
#   "活动送的十连出金了"          -> ["event_welfare", "gacha_character"]
#   "养成资源不够角色练不起来"    -> ["progression_resource"]

MODULE_TAGS = {
    "gacha_character": {
        "label": "抽卡/角色",
        "description": "涉及角色外观、建模、抽卡决策、命座/星链、角色定位讨论。",
        "keywords_hint": ["抽", "歪", "保底", "命座", "建模", "好看", "可爱", "萌", "角色"],
    },
    "combat_strength": {
        "label": "战斗/强度",
        "description": "涉及角色强度、伤害、配队、武器、战斗手感、技能机制。",
        "keywords_hint": ["强度", "伤害", "配队", "专武", "主c", "副c", "手感", "连招"],
    },
    "story_quest": {
        "label": "剧情/任务",
        "description": "涉及主线/支线剧情内容、角色故事、世界观、NPC 互动。",
        "keywords_hint": ["剧情", "主线", "故事", "PV", "前瞻", "角色档案", "世界观"],
    },
    "event_welfare": {
        "label": "活动/福利",
        "description": "涉及版本活动、奖励、签到、兑换码、周年庆福利。",
        "keywords_hint": ["活动", "福利", "奖励", "签到", "兑换码", "十连", "送"],
    },
    "progression_resource": {
        "label": "养成/资源",
        "description": "涉及角色培养、材料获取、体力/树脂、日常任务产出。",
        "keywords_hint": ["养成", "材料", "资源", "体力", "升级", "突破", "肝"],
    },
    "performance_bug": {
        "label": "性能/bug",
        "description": "涉及画质、帧率、加载速度、闪退、机型适配、已知 bug。",
        "keywords_hint": ["卡顿", "闪退", "bug", "画质", "帧率", "手机", "优化", "配置"],
    },
    "ui_qol": {
        "label": "UI/QoL",
        "description": "涉及界面设计、操作便利性、菜单交互、生活质量改进诉求。",
        "keywords_hint": ["UI", "界面", "操作", "地图", "导航", "背包", "设置"],
    },
    "gameplay_mode": {
        "label": "玩法模式",
        "description": "涉及特定玩法系统: 深渊/逆境深塔、合作模式、探索、解谜等。",
        "keywords_hint": ["深塔", "深渊", "探索", "解谜", "合作", "联机", "副本"],
    },
}

MODULE_TAG_VALUES = list(MODULE_TAGS.keys())


# ================================================================
# 3. is_version_related - 是否与版本更新相关
# ================================================================
# 判断标准:
#   True  - 评论内容涉及新版本、前瞻、更新内容、新角色上线、版本号等
#   False - 不涉及版本时间节点，属于日常讨论
#
# 边界案例:
#   "3.0剧情太好了"        -> True (提及版本号)
#   "前瞻看完坚定抽了"     -> True (前瞻 = 版本前瞻)
#   "西格莉卡好可爱"       -> False (未涉及版本节点，仅角色讨论)
#   "新角色什么时候出"     -> True (关注新版本内容)

IS_VERSION_RELATED_RUBRIC = (
    "评论是否涉及版本更新、前瞻直播、新版本内容、版本号、"
    "上线时间等与版本节奏相关的讨论。仅讨论角色本身不算。"
)


# ================================================================
# 4. is_target_related - 是否与搜索目标相关
# ================================================================
# 目标关键词在运行时从数据的 source_keyword 字段自动提取，
# 也可通过 target_aliases 参数传入昵称/别名列表。
#
# 判断标准:
#   True  - 评论主体或关键内容涉及搜索目标（含别名）
#   False - 未提及或仅在无关上下文中提及
#
# 边界案例（以搜索目标"某角色"为例）:
#   "某角色好萌想抽"      -> True (围绕目标讨论)
#   "某角色好像也在那个活动里" -> True (与目标相关)
#   纯回复他人且未实质讨论目标 -> False


def build_target_rubric(target_keyword: str, aliases: list[str] | None = None) -> str:
    """根据运行时的搜索关键词动态生成判断标准。"""
    all_names = [target_keyword] + (aliases or [])
    return (
        f"评论主体是否涉及搜索目标 '{target_keyword}'。"
        f"已知名称/别名: {', '.join(all_names)}。"
        "仅在回复他人时顺带提及、或完全无关的上下文不算。"
    )


IS_TARGET_RELATED_RUBRIC_TEMPLATE = (
    "评论主体是否涉及搜索目标 '{target}'。"
    "已知名称/别名: {aliases}。"
    "仅在回复他人时顺带提及、或完全无关的上下文不算。"
)


# ================================================================
# 5. churn_risk - 流失风险
# ================================================================
# 判断标准: 基于评论文本中的显性信号判断用户流失倾向。
#   low    - 无流失信号，或表达积极游玩意愿
#   medium - 表达犹豫、倦怠、阶段性不满，但未明确表示离开
#   high   - 明确表达要弃坑、已弃坑、对游戏失去兴趣
#
# 边界案例:
#   "太肝了玩不动"        -> medium (倦怠但未说弃坑)
#   "已经卸载了"          -> high
#   "纠结要不要入坑"      -> low (是潜在新用户，非流失)
#   "回坑了真香"          -> low (回归用户，正面)
#   "氪不动了下次再说"    -> medium

CHURN_RISK_VALUES = ["low", "medium", "high"]

CHURN_RISK_RUBRIC = {
    "low": "无流失信号。表达积极游玩意愿、入坑意愿、回坑等。或与流失完全无关。",
    "medium": "存在犹豫、倦怠、阶段性不满，但未明确表示放弃。如: 太肝、没时间、有点累。",
    "high": "明确表达弃坑、卸载、不玩了、对游戏彻底失望。",
}


# ================================================================
# 6. pay_risk - 付费意愿风险
# ================================================================
# 判断标准: 基于评论文本判断用户对付费/氪金的态度。
#   low    - 无付费相关讨论，或表达正常付费意愿
#   medium - 对付费性价比有顾虑，或在免费/付费之间犹豫
#   high   - 明确表达付费劝退、充值不值、氪金过重等强烈负面
#
# 注意: 此字段衡量的是"付费体验的负面风险"，非"付费金额"。
#   "十连出金了"          -> low (正常抽卡体验)
#   "歪了好心痛"          -> medium (抽卡不顺但未上升到付费体系批评)
#   "这游戏太氪了不充了"  -> high
#   "没石头了等白嫖"      -> medium
#   "好可爱想抽"          -> low (有付费意愿)

PAY_RISK_VALUES = ["low", "medium", "high"]

PAY_RISK_RUBRIC = {
    "low": "无付费相关讨论，或表达正常/积极的付费意愿。",
    "medium": "对付费性价比有顾虑、抽卡不顺的抱怨、资源不足的焦虑，但未上升到体系性批评。",
    "high": "明确表达氪金劝退、充值不值、付费体系不合理等强烈负面态度。",
}


# ================================================================
# 7. summary_reason - 标注理由
# ================================================================
# 要求 LLM 用一句中文概括标注理由，便于人工抽检。
# 不超过 50 字。

SUMMARY_REASON_RUBRIC = (
    "用一句话（不超过50字）概括本条评论的核心内容和标注理由。"
    "重点说明为什么选择了当前的 sentiment 和 module_tags。"
)


# ================================================================
# 完整标签 schema（用于生成 LLM prompt 和验证输出）
# ================================================================
LABEL_SCHEMA = {
    "sentiment": {
        "type": "enum",
        "values": SENTIMENT_VALUES,
        "required": True,
        "description": "评论整体情感倾向",
        "rubric": SENTIMENT_RUBRIC,
    },
    "module_tags": {
        "type": "list[enum]",
        "values": MODULE_TAG_VALUES,
        "required": True,
        "allow_empty": True,
        "description": "评论涉及的游戏模块（多选，可为空）",
        "rubric": {k: v["description"] for k, v in MODULE_TAGS.items()},
    },
    "is_version_related": {
        "type": "bool",
        "required": True,
        "description": "是否与版本更新/前瞻相关",
        "rubric": IS_VERSION_RELATED_RUBRIC,
    },
    "is_target_related": {
        "type": "bool",
        "required": True,
        "description": "是否与搜索目标相关（目标由 source_keyword 自动确定）",
        "rubric": "运行时通过 build_target_rubric() 动态生成",
    },
    "churn_risk": {
        "type": "enum",
        "values": CHURN_RISK_VALUES,
        "required": True,
        "description": "用户流失风险等级",
        "rubric": CHURN_RISK_RUBRIC,
    },
    "pay_risk": {
        "type": "enum",
        "values": PAY_RISK_VALUES,
        "required": True,
        "description": "付费体验负面风险等级",
        "rubric": PAY_RISK_RUBRIC,
    },
    "summary_reason": {
        "type": "str",
        "required": True,
        "max_length": 50,
        "description": "标注理由（一句话）",
        "rubric": SUMMARY_REASON_RUBRIC,
    },
}


# ================================================================
# 标注输出样例（用于 few-shot prompt）
# ================================================================
ANNOTATION_EXAMPLES = [
    {
        "_note": "is_target_related 取决于运行时 source_keyword，这里假设目标为搜索关键词对应的角色",
        "comment": "这个角色好萌好可爱想抽但是没石头了",
        "annotation": {
            "sentiment": "mixed",
            "module_tags": ["gacha_character"],
            "is_version_related": False,
            "is_target_related": True,
            "churn_risk": "low",
            "pay_risk": "medium",
            "summary_reason": "对目标角色外观好感但缺少抽卡资源，付费焦虑轻度。",
        },
    },
    {
        "comment": "新版本剧情太刀了呜呜呜",
        "annotation": {
            "sentiment": "mixed",
            "module_tags": ["story_quest"],
            "is_version_related": True,
            "is_target_related": False,
            "churn_risk": "low",
            "pay_risk": "low",
            "summary_reason": "对新版本剧情有情感共鸣，整体正面但表达心痛。",
        },
    },
    {
        "comment": "这个角色强度太低了不值得抽",
        "annotation": {
            "sentiment": "negative",
            "module_tags": ["combat_strength", "gacha_character"],
            "is_version_related": False,
            "is_target_related": False,
            "churn_risk": "low",
            "pay_risk": "medium",
            "summary_reason": "对角色强度不满，影响抽卡决策。",
        },
    },
    {
        "comment": "手机玩怎么样",
        "annotation": {
            "sentiment": "neutral",
            "module_tags": ["performance_bug"],
            "is_version_related": False,
            "is_target_related": False,
            "churn_risk": "low",
            "pay_risk": "low",
            "summary_reason": "纯提问，咨询移动端体验。",
        },
    },
    {
        "comment": "太肝了真的玩不动了准备弃坑",
        "annotation": {
            "sentiment": "negative",
            "module_tags": ["progression_resource"],
            "is_version_related": False,
            "is_target_related": False,
            "churn_risk": "high",
            "pay_risk": "low",
            "summary_reason": "养成压力导致弃坑意愿，明确流失信号。",
        },
    },
    {
        "comment": "求背景音乐名字",
        "annotation": {
            "sentiment": "neutral",
            "module_tags": [],
            "is_version_related": False,
            "is_target_related": False,
            "churn_risk": "low",
            "pay_risk": "low",
            "summary_reason": "纯提问，与游戏模块无关。",
        },
    },
]
