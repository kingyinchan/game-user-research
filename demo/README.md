# Demo 数据快照

这个目录用于放可以直接随仓库展示的 demo 产物，不依赖重新抓数或重新调用 LLM。

当前快照：`demo/wuwa_3_2_xigelika/`

包含内容：
- `data/comments_labeled.csv`：已完成结构化标注的评论结果
- `data/comments_cleaned.csv`：清洗后的评论数据
- `data/label_routing_report.json`：标注路由统计
- `charts/*.png`：分析图表
- `reports/insight_report.md`：洞察报告，包含 LLM 点评
- `reports/label_review_queue.csv`：人工复核队列
- `config/project.yaml`：对应专题配置

不包含内容：
- `.env`
- 原始爬虫数据
- `_label_cache.jsonl`、`_label_failures.jsonl` 这类运行时缓存
- 外部抓取器 `MediaCrawler`

如果你只是想让别人 clone 后直接看结果，优先看这个目录；如果想重新跑分析，还是使用 `analysis/` 和 `backend/` 下的主流程。
