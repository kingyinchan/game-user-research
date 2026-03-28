# -*- coding: utf-8 -*-
"""
LLM 标注提示词模板。
system_prompt 根据 project.yaml 动态填充，支持单条和批量两种标注模式。
"""

from __future__ import annotations

import json

from config.labels import (
    ANNOTATION_EXAMPLES,
    CHURN_RISK_RUBRIC,
    MODULE_TAGS,
    PAY_RISK_RUBRIC,
    SENTIMENT_RUBRIC,
    build_target_rubric,
)


SYSTEM_PROMPT_TEMPLATE = """\
# 角色
你是一名资深游戏用户研究员，擅长从社交媒体评论中提取结构化用户洞察。

# 任务
对小红书平台上《{game}》玩家评论进行结构化标注。
当前分析的搜索目标是: 「{target}」。

# 输出格式
严格输出合法 JSON，禁止输出任何解释、前缀或 markdown 标记。
{output_format}

# 字段判定标准

## 1. sentiment - 情感倾向
{sentiment_rubric}

特别注意游戏社区表达习惯:
- 反讽/阴阳怪气: "强度很高呢（笑）" -> negative（表面正面但实际讽刺）
- 又夸又骂: "建模好看强度拉胯" -> mixed
- 玩梗: "草 又被刀了" -> 需结合上下文判断，"刀"指剧情催泪，通常为 mixed 或 positive
- 缩写黑话: "DNA动了" = 心动/想抽 -> positive; "寄了" = 完了 -> negative
- "老婆"/"老公" = 对角色的喜爱 -> positive
- 纯表情、纯互动（如"已关注""转发了"）-> neutral

## 2. module_tags - 讨论模块（多选）
从以下枚举中选择，一条评论可命中多个标签。若与游戏模块完全无关，返回空列表 []。
{module_tags_rubric}

判定原则:
- 角色外观讨论 + 抽卡意愿 -> ["gacha_character"]
- 同时讨论强度和抽卡 -> ["combat_strength", "gacha_character"]
- 活动中抽到角色 -> ["event_welfare", "gacha_character"]
- 纯社交互动、求资源、与游戏模块无关 -> []

## 3. is_version_related - 是否与版本更新相关
True: 明确涉及版本号、前瞻直播、版本更新内容、新版本上线、维护公告等。
False: 仅讨论角色/玩法本身，不涉及版本时间节点。
注意: "新角色" 不等于版本更新，除非评论明确与版本节点关联。

## 4. is_target_related - 是否与搜索目标相关
{target_rubric}
注意: 评论必须实质讨论目标，纯粹在回复链中 @提及不算。

## 5. churn_risk - 流失风险
{churn_rubric}

注意:
- "想入坑"/"纠结要不要玩" 是潜在新用户 -> low（非流失信号）
- "回坑了" -> low（回归）
- "太肝了" 但未说弃坑 -> medium
- 必须有显性弃坑信号才标 high

## 6. pay_risk - 付费体验负面风险
{pay_rubric}

注意:
- 此字段衡量付费体验的负面程度，非付费金额
- "好可爱想抽" -> low（正向付费意愿）
- "歪了好心痛" -> medium（抽卡不顺但未上升到体系批评）
- "这游戏太氪了" -> high（体系性批评）

## 7. summary_reason - 标注理由
用一句中文概括此评论的核心内容及你选择当前标签的理由，不超过 50 字。

# 标注示例
{examples}

# 规则（严格遵守）
1. 只输出 JSON，无任何额外文字
2. module_tags 的值必须来自上述枚举
3. 对不确定的内容保守判断，不做过度推断
4. 对反讽、阴阳怪气等表达要识别真实情感，勿被表面措辞误导
5. 空评论或无法判断内容标为 neutral + 空 module_tags
"""


USER_PROMPT_TEMPLATE = '请标注以下评论:\n"{comment}"'

BATCH_USER_PROMPT_TEMPLATE = """请标注以下评论列表，输出时必须覆盖每个 comment_id，且不要遗漏：

{comments}
"""


def _build_output_format(batch_mode: bool) -> str:
    if not batch_mode:
        return """JSON schema:
{
  "sentiment": "positive|neutral|negative|mixed",
  "module_tags": ["tag1", "tag2"],
  "is_version_related": true|false,
  "is_target_related": true|false,
  "churn_risk": "low|medium|high",
  "pay_risk": "low|medium|high",
  "summary_reason": "不超过50字的标注理由"
}"""

    return """输出一个 JSON object，结构如下:
{
  "items": [
    {
      "comment_id": "原始 comment_id",
      "sentiment": "positive|neutral|negative|mixed",
      "module_tags": ["tag1", "tag2"],
      "is_version_related": true|false,
      "is_target_related": true|false,
      "churn_risk": "low|medium|high",
      "pay_risk": "low|medium|high",
      "summary_reason": "不超过50字的标注理由"
    }
  ]
}

要求:
- items 中每个元素必须包含 comment_id
- 必须覆盖输入中的全部 comment_id
- comment_id 必须与输入完全一致
- 除 items 外不要输出其他字段"""


def build_system_prompt(game: str, target: str, aliases: list[str] | None = None, batch_mode: bool = False) -> str:
    """根据项目配置动态构建 system prompt。"""
    sentiment_lines = "\n".join(f"- {k}: {v}" for k, v in SENTIMENT_RUBRIC.items())
    module_lines = "\n".join(
        f"- {k}: {v['label']} - {v['description']}"
        for k, v in MODULE_TAGS.items()
    )
    target_rubric = build_target_rubric(target, aliases)
    churn_lines = "\n".join(f"- {k}: {v}" for k, v in CHURN_RISK_RUBRIC.items())
    pay_lines = "\n".join(f"- {k}: {v}" for k, v in PAY_RISK_RUBRIC.items())

    examples_text = ""
    for i, ex in enumerate(ANNOTATION_EXAMPLES[:4], 1):
        ann_json = json.dumps(ex["annotation"], ensure_ascii=False, indent=2)
        examples_text += f'### 示例 {i}\n评论: "{ex["comment"]}"\n输出:\n{ann_json}\n\n'

    return SYSTEM_PROMPT_TEMPLATE.format(
        game=game,
        target=target,
        output_format=_build_output_format(batch_mode),
        sentiment_rubric=sentiment_lines,
        module_tags_rubric=module_lines,
        target_rubric=target_rubric,
        churn_rubric=churn_lines,
        pay_rubric=pay_lines,
        examples=examples_text,
    )


def build_user_prompt(comment: str) -> str:
    """构建单条评论的 user prompt。"""
    return USER_PROMPT_TEMPLATE.format(comment=comment)


def build_batch_user_prompt(comments: list[tuple[str, str]]) -> str:
    """构建批量评论的 user prompt。"""
    payload = [
        {
            "comment_id": comment_id,
            "content": str(comment).replace("\n", " ").strip(),
        }
        for comment_id, comment in comments
    ]
    comments_json = json.dumps(payload, ensure_ascii=False, indent=2)
    return BATCH_USER_PROMPT_TEMPLATE.format(comments=comments_json)
