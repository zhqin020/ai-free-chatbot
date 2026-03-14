# AI-Free-Chatbot Python API 快速集成指南

本项目已封装 ApiClient，第三方只需引入 examples/client_common.py，无需关心底层 HTTP 细节。

## 1. 环境准备
- 启动 API 服务（python -m scripts.run_stack）
- 确保 examples/client_common.py 可用

## 2. 典型调用流程

### 2.1 导入 ApiClient
```python
from client_common import ApiClient
import time
```

### 2.2 构造请求 payload
推荐使用 ApiClient.make_chat_request_payload（如未内置，可自行复制该函数）：
```python
payload = ApiClient.make_chat_request_payload(
    document_text="你的原始文本内容",
    msg_id_prefix="your-app"
)
```

### 2.3 提交任务
```python
client = ApiClient()  # 自动读取 API_BASE_URL 环境变量
created = client.post("/api/tasks", json=payload)
task_id = created["id"]
```

### 2.4 轮询任务状态
```python
while True:
    row = client.get(f"/api/tasks/{task_id}")
    status = row["status"]
    if status == "CRITICAL":
        print("服务端不可用，终止处理")
        break
    if status in ("COMPLETED", "FAILED"):
        print("处理完成/失败，可根据需要重试")
        print(row)
        break
    time.sleep(2)
client.close()
```

### 2.5 结果说明
- status == "COMPLETED" 时，row["extracted_json"] 为结构化提取结果
- status == "FAILED" 可重试
- status == "CRITICAL" 应立即终止，服务端不可用

---

## 3. 进阶建议
- 可将 make_chat_request_payload 作为 @staticmethod 放入 ApiClient，便于统一调用
- 可扩展 ApiClient 增加 get_task_status_helper 等工具方法
- 支持自定义 prompt、json 模板等

---

## 4. 其他语言
如需其他语言调用，可参考 client_common.py 的实现，直接用 HTTP POST/GET 即可。

---

## 5. 参考
- 详细接口文档见 http://127.0.0.1:8000/docs
- 代码示例见 examples/example_test_extract_api.py

如需进一步封装或有特殊需求，请联系开发者。
