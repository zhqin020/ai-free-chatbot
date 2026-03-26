# API 集成指引 (Integration Guide)

本项目提供了完整的 API 接口，支持第三方系统通过 HTTP 调用来实现 AI 对话与结构化信息提取。

## 1. 快速集成 (Quick Start)

推荐直接使用 `examples/client_common.py` 中的 `ApiClient` 类，它封装了常用的请求逻辑和错误处理。

### 1.1 核心流程 (Typical Workflow)

1.  **启动服务**: `python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000`
2.  **提交任务**: 向 `/api/tasks` 发送 POST 请求（包含 prompt 和待处理文本）。
3.  **轮询状态**: 循环调用 `/api/tasks/{task_id}` 直到状态变为 `COMPLETED`。
4.  **获取结果**: 从响应中的 `extracted_json` 字段读取识别出的结构化数据。

### 1.2 Python 示例 (Python Example)

```python
from examples.client_common import ApiClient
import time

client = ApiClient() # 默认访问 http://127.0.0.1:8000

# 1. 提交任务
created = client.post("/api/tasks", json={
    "prompt": "请提取文书中的案件基本信息",
    "document_text": "此处粘贴文书正文..."
})
task_id = created["id"]

# 2. 轮询
while True:
    task = client.get(f"/api/tasks/{task_id}")
    status = task["status"]
    
    if status == "COMPLETED":
        print("提取成功:", task["extracted_json"])
        break
    elif status == "FAILED":
        print("任务失败:", task.get("error"))
        break
    
    time.sleep(2)
```

---

## 2. 现有示例说明 (Included Examples)

你可以直接运行以下脚本来熟悉接口：

| 脚本 | 功能说明 |
| :--- | :--- |
| `example_tasks_api.py` | 基础任务提交与状态查询流程。 |
| `example_sessions_api.py` | 管理浏览器会话（刷新、手动标记登录等）。 |
| `example_test_extract_api.py` | **推荐阅读**：包含复杂的法律文书提取 Prompt 和 JSON 模板。 |
| `example_metrics_logs_api.py` | 查询服务运行统计（任务量、成功率）及系统日志。 |

---

## 3. 核心 API 参考 (Core API Reference)

| Endpoint | Method | 说明 |
| :--- | :--- | :--- |
| `/api/tasks` | POST | 创建异步提取任务。 |
| `/api/tasks/{id}` | GET | 查询任务详情与结果。 |
| `/api/sessions` | GET | 查看所有浏览器会话状态。 |
| `/api/test/extract`| POST | 同步测试模式（仅用于调试小的片段）。 |
| `/healthz` | GET | 服务健康检查。 |

详细文档请在服务启动后访问: `http://127.0.0.1:8000/docs` (Swagger UI)
