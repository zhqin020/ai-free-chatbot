# 任务状态机（超简版）

目标：把客户端与 worker 的协作收敛为最小闭环，降低失败点。

## 设计原则

1. 客户端只做两件事：创建任务、轮询状态。
2. 服务端不在创建任务时做 provider 健康检查。
3. worker 对 provider 响应只做 JSON 合法性判断。
4. 失败后不自动重试；是否重试由客户端自行决定（重新创建任务）。

## API 最小闭环

1. 创建任务
- 接口：POST /api/tasks
- 入参：prompt、document_text、provider_hint（可选）
- 返回：task_id、status=PENDING

2. 轮询任务（已合并结果）
- 接口：GET /api/tasks/{task_id}
- 返回字段：
  - status
  - latest_trace_id
  - raw_response
  - extracted_json（仅保证是可解析 JSON 对象）
  - error_message

3. 兼容接口（可选）
- 接口：GET /api/tasks/{task_id}/result
- 说明：为兼容旧客户端保留；新客户端可只使用 GET /api/tasks/{task_id}

## 状态定义（任务）

1. PENDING：已入队，等待 worker 处理。
2. DISPATCHED：worker 已认领任务，正在执行。
3. EXTRACTING：收到 provider 文本响应，正在做 JSON 提取。
4. COMPLETED：提取到合法 JSON，任务完成。
5. FAILED：处理失败（含超时、页面未就绪、响应非 JSON、解析失败）。

说明：当前策略为失败终态，不会自动回到 PENDING。

## 状态流转

1. 创建任务：PENDING
2. worker 认领：PENDING -> DISPATCHED
3. provider 返回文本：DISPATCHED -> EXTRACTING
4. 文本中可提取合法 JSON：EXTRACTING -> COMPLETED
5. 任一步失败：DISPATCHED/EXTRACTING -> FAILED

## 客户端建议流程

1. 调用 POST /api/tasks 创建任务。
2. 每 1 到 2 秒轮询 GET /api/tasks/{task_id}。
3. 当 status 为 COMPLETED 或 FAILED 时停止轮询。
4. 直接从轮询响应读取 raw_response、extracted_json、error_message。
5. 若 status=FAILED 且业务需要重试：客户端重新创建新任务。

## 服务端简化后的职责边界

1. API 层：只负责接收任务、返回任务状态与结果。
2. 调度层：只负责分配 READY 会话和任务状态推进。
3. 执行层（worker）：只负责发送消息、拿回文本、判断是否可提取 JSON。
4. 重试策略：不在服务端自动执行。

## 常见卡点（最简排查）

1. 任务一直 PENDING
- worker 未运行，或没有 READY 会话。

2. 任务直接 FAILED
- provider 页未就绪（登录/验证未完成）。
- provider 无响应或超时。
- 响应里没有可提取 JSON 对象。

3. latest_trace_id 为空
- 任务尚未进入派发阶段（worker 没有真正消费到该任务）。

## 兼容性说明

1. extracted_json 已放宽为通用 JSON 对象，不再要求固定字段 schema。
2. retry_count 字段保留用于历史兼容与观测，不代表服务端自动重试行为。
