# 全流程执行报告

- 专题: 鸣潮 3.2 西格莉卡专题
- 原始数据目录: `C:\game_user_research\crawler\MediaCrawler\data\xhs\jsonl`
- 清洗数据目录: `C:\game_user_research\analysis\cleaned_data`
- 输出目录: `C:\game_user_research\analysis\output`

## 预检结果

| 检查项 | 结果 |
| --- | --- |
| raw_data_exists | True |
| env_file_exists | True |
| api_key_present | True |
| existing_cleaned_comments | True |
| existing_labeled_comments | False |

## 执行步骤

| 步骤 | 状态 | 说明 |
| --- | --- | --- |
| data_cleaning | success | data_cleaning.py completed successfully. |
| data_quality_review | success | Reviewed 526 cleaned comments and produced 0 quality findings. |
| llm_label | success | llm_label.py completed successfully. |
| analyze | success | analyze.py completed successfully. |
| label_review_queue | success | Generated review queue with 454 candidate comments. |
| insight_report | success | Generated reusable insight report from 488 labeled comments. |

## 阻塞项

- 无阻塞项
