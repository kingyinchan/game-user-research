# 可复用 Agent 层

这个目录是在现有分析流水线之上增加的一层可复用 Agent 编排层：

`抓取 -> 清洗 -> 标注 -> 分析 -> Agent 任务`

设计原则是保持原有 ETL 和图表生成逻辑的确定性，把需要判断、复核、总结和产出报告的部分封装成独立任务。

## 设计目标

- 在不同游戏专题之间复用同一套任务接口
- 让 Agent 输出能回溯到 CSV 行和源文件
- 当上游产物缺失时自动降级，不让整个流程报错中断
- 支持可选的 LLM 总结能力，但不让全流程强依赖 LLM

## 目录结构

- `framework.py`
  通用任务基类、注册表、运行上下文和工件输出封装。
- `models.py`
  通用结果模型、发现模型和证据模型。
- `llm.py`
  可选的 OpenAI 兼容 LLM 适配层。
- `tools.py`
  通用 CSV 解析、布尔归一化和 Markdown 输出工具。
- `tasks/`
  内置 Agent 任务目录。

## 当前内置任务

- `data_quality_review`
  在标注前检查清洗数据质量，输出质检指标和风险项。
- `full_pipeline_report`
  一键串起清洗、质检、标注、分析和下游 Agent 任务，并输出总报告。
- `label_review_queue`
  基于标注结果生成人工复核队列。
- `insight_report`
  基于标注结果生成可复用洞察简报。

## 使用方式

列出所有任务：

```bash
python analysis/agent_runner.py --list
```

运行配置文件中的默认任务：

```bash
python analysis/agent_runner.py
```

只运行指定任务：

```bash
python analysis/agent_runner.py --task data_quality_review --task label_review_queue
```

一键跑完整流并汇总报表：

```bash
python analysis/agent_runner.py --task full_pipeline_report
```

## 如何扩展

1. 在 `analysis/agents/tasks/` 下新增一个任务文件。
2. 定义一个继承 `AgentTask` 的类。
3. 设置 `name` 和 `description`。
4. 用 `@register_task` 装饰这个类。
5. 在 `run()` 中返回 `TaskResult`，至少包含：
   - `summary`
   - `findings`
   - `artifacts`
   - `meta`

## 推荐扩展模式

- 把原始统计和规则判断保持为确定性逻辑。
- 只把 LLM 用在总结、排序、解释这类增值层。
- 所有输出统一写入 `analysis/artifacts/agents/` 或 `analysis/reports/`。
- 只要任务产出结论或问题，尽量附带 `comment_id` 或文件级证据。

## 配置位置

Agent 相关配置统一写在 `analysis/config/project.yaml` 的 `agents` 段里。

这样做的好处是：

- 换专题时不需要改 Agent 框架本身
- 可以按不同专题配置默认任务、阈值和 LLM 开关
- 更适合后续复用到其他游戏、角色或版本研究
