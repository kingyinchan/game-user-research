# Backend

这个目录提供一个基于 `FastAPI` 的薄后端，用来读取现有分析产物，并向前端暴露任务状态和结果接口。

## 启动

```bash
uv run uvicorn backend.app.main:app --reload
```

默认地址：

- `http://127.0.0.1:8000`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`

## 主要接口

- `GET /api/dashboard`
- `GET /api/insight-report`
- `GET /api/review-queue`
- `GET /api/comments`
- `GET /api/pipeline/status`
- `POST /api/pipeline/run`
