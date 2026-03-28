# 游戏用户研究流水线

这是一个面向游戏用户研究的专题分析项目，当前聚焦于小红书游戏帖子与评论数据。项目将抓取结果接入后，依次完成数据清洗、LLM 结构化标注、统计分析出图，以及基于产物的 Agent 任务处理。

当前默认专题配置位于 `analysis/config/project.yaml`，示例主题为“鸣潮 3.2 西格莉卡专题”。

## 项目能做什么

- 读取小红书抓取结果 JSONL 文件
- 清洗帖子和评论数据，导出标准化 CSV
- 调用 OpenAI 兼容接口，对评论做结构化标注
- 统计情感分布、负面模块、风险分布并生成图表
- 运行可复用 Agent 任务，做数据质检、复核队列生成和洞察简报

## 目录结构

```text
.
├─ analysis/
│  ├─ cleaned_data/          # 清洗后数据、标注结果
│  ├─ config/                # 专题配置、标签体系、提示词
│  ├─ agents/                # 可复用 Agent 层
│  ├─ data_cleaning.py       # 数据清洗
│  ├─ llm_label.py           # LLM 标注
│  ├─ analyze.py             # 统计分析与出图
│  └─ agent_runner.py        # Agent 任务运行入口
├─ crawler/                  # 可选，本地存放外部抓取器（不随仓库提交）
├─ .env.example              # API 环境变量示例
├─ pyproject.toml            # 项目依赖
└─ README.md
```

## 环境要求

- Python >= 3.10
- 推荐使用 `uv`
- 如果需要重新抓取数据，需要单独准备外部抓取器 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)

本机当前已验证：

- `python --version` -> `3.11.5`
- `uv --version` -> `0.10.12`

## 快速体验 Demo

仓库内已包含一份可直接展示的 demo 快照，适合 clone 后快速查看页面和结果。

先安装依赖：

```bash
uv sync
```

启动 demo：

```bash
python demo/run_demo.py
```

启动后可访问：

- API 文档：`http://127.0.0.1:8000/docs`
- Dashboard：`http://127.0.0.1:8000/studio/`
- Demo 快照目录：`demo/data/wuwa_3_2_xigelika/`

## 页面预览

### Dashboard Overview

![Dashboard Overview](demo/figure/overview.png)

### Analysis Views

<p align="center">
  <img src="demo/figure/overview2.png" alt="Dashboard Detail Overview" width="49%" />
  <img src="demo/figure/chart.png" alt="Chart View" width="49%" />
</p>

### Review Queue

![Review Queue](demo/figure/queue.png)

## 启动后端与 Dashboard

如需读取当前工作区的 `analysis/` 产物，而不是 demo 快照，可直接启动 FastAPI：

```bash
uv run uvicorn backend.app.main:app --reload
```

启动后可访问：

- API 文档：`http://127.0.0.1:8000/docs`
- Dashboard：`http://127.0.0.1:8000/studio/`

## 安装依赖

推荐方式：

```bash
uv sync
```

如果不使用 `uv`，也可以自行用 `pip` 安装 [pyproject.toml](./pyproject.toml) 中列出的依赖。

## 配置环境变量

在项目根目录创建 `.env`，至少配置以下变量：

```env
OPENAI_API_KEY=API_KEY
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
```

示例见 [.env.example](./.env.example)。

说明：

- `llm_label.py` 依赖这些环境变量
- `agent_runner.py` 只有在 `analysis/config/project.yaml` 里打开 `agents.llm.enabled: true` 时才会调用 LLM

## 从现在开始怎么跑完整流

如需让 Agent 自动串起整条链路，而不是手动逐步执行，可以直接使用一键任务：

```bash
python analysis/agent_runner.py --task full_pipeline_report
```

这个任务会自动执行：

```text
清洗 -> 数据质检 -> 标注 -> 分析 -> 复核队列 -> 洞察报告
```

并输出总报告到：

- `analysis/reports/full_pipeline_report/full_pipeline_report.md`

前提是：

- 原始数据目录存在
- 如果需要重新标注，则 `.env` 中必须有 `OPENAI_API_KEY`

### 方案 A：直接使用当前已有抓取结果

如果已经有 `crawler/MediaCrawler/data/xhs/jsonl/` 下的抓取数据，这是最直接的方式。

1. 清洗数据

```bash
python analysis/data_cleaning.py
```

这一步会读取 `analysis/config/project.yaml` 中的 `paths.raw_data`，默认是：

```text
../crawler/MediaCrawler/data/xhs/jsonl
```

运行后会生成：

- `analysis/cleaned_data/contents_cleaned.csv`
- `analysis/cleaned_data/comments_cleaned.csv`

2. 运行 LLM 标注

```bash
python analysis/llm_label.py
```

运行后会生成：

- `analysis/cleaned_data/comments_labeled.csv`
- `analysis/cleaned_data/_label_cache.jsonl`

说明：

- 这个脚本支持缓存和断点续跑
- 如果 API 调用失败，会写入兜底标签，避免重复处理同一条评论

3. 生成统计分析和图表

```bash
python analysis/analyze.py
```

运行后会在 `analysis/output/` 下生成图表，例如：

- 情感分布图
- 版本相关负面模块分布
- 目标相关负面模块分布
- 风险分布图

4. 运行 Agent 任务

先查看可用任务：

```bash
python analysis/agent_runner.py --list
```

运行默认任务：

```bash
python analysis/agent_runner.py
```

默认任务由 `analysis/config/project.yaml` 中的 `agents.default_tasks` 控制，当前包括：

- `data_quality_review`
- `label_review_queue`
- `insight_report`

运行后会写出：

- `analysis/artifacts/agents/`
- `analysis/reports/`

如果只需要让 Agent 自动跑完整流，直接执行：

```bash
python analysis/agent_runner.py --task full_pipeline_report
```

### 方案 B：从抓取开始重跑全流程

如果需要从头重新抓小红书数据，先把外部抓取器克隆到本地 `crawler/MediaCrawler`：

```bash
git clone https://github.com/NanmiCoder/MediaCrawler.git crawler/MediaCrawler
```

抓取器本身的详细说明见：

- [MediaCrawler GitHub 仓库](https://github.com/NanmiCoder/MediaCrawler)

然后进入抓取器目录：

```bash
cd crawler/MediaCrawler
```

按其说明完成依赖安装与登录后，常见入口命令是：

```bash
uv run main.py --platform xhs --lt qrcode --type search
```

抓取完成后回到项目根目录，继续执行：

```bash
python analysis/data_cleaning.py
python analysis/llm_label.py
python analysis/analyze.py
python analysis/agent_runner.py
```

## 当前工作区状态

当前工作区已经存在：

- `analysis/cleaned_data/comments_cleaned.csv`
- `analysis/cleaned_data/contents_cleaned.csv`

这表示“抓取结果接入 + 数据清洗”已经可用。

当前还没有：

- `analysis/cleaned_data/comments_labeled.csv`
- `analysis/output/`

因此如果当前直接运行 `python analysis/agent_runner.py`：

- `data_quality_review` 会正常执行
- `label_review_queue` 和 `insight_report` 会因为缺少标注结果而跳过

## 配置专题

核心配置文件是：

- `analysis/config/project.yaml`

通常会改这些字段：

- `topic.game`
- `topic.version`
- `topic.target`
- `topic.display_name`
- `topic.target_aliases`
- `paths.raw_data`
- `analysis.negative_sentiments`
- `agents.default_tasks`

这意味着换一个游戏、角色、版本或专题时，不需要改主流程代码。

## Agent 层说明

Agent 层文档已单独放在：

- [analysis/agents/README.md](./analysis/agents/README.md)

它描述了：

- 通用任务接口
- 任务注册机制
- 工件输出位置
- 如何新增一个可复用 Agent 任务

## 常用命令汇总

```bash
python analysis/data_cleaning.py
python analysis/llm_label.py
python analysis/analyze.py
python analysis/agent_runner.py --list
python analysis/agent_runner.py
```

## 建议的运行顺序

```text
抓取 -> 清洗 -> 标注 -> 分析 -> Agent
```

不要跳过 `llm_label.py` 直接跑分析或依赖标注结果的 Agent 任务，否则会因为缺少 `comments_labeled.csv` 无法得到完整产物。
