# AI Chat 自动化提问与结构化提取系统 - 技术设计（方案 2）

## 1. 目标与范围

本设计面向以下目标：

1. 同时管理多个已登录 AI Chat 会话（openchat, gemini, grok, deepseek）。
2. 轮询调度多会话发送提问，遇阻不阻塞整体。
3. 从回复中稳定提取 JSON，并进行 schema 校验与重试纠错。
4. 提供 API 供外部程序提交任务和获取结果。
5. 提供管理界面：会话管理、测试提取、服务运行监控、日志与统计。
6. 浏览器异常关闭后自动恢复并继续处理。

## 2. 总体架构

采用分层架构：

1. 接入层（API/UI）
- FastAPI 提供 REST 接口。
- 管理界面（建议首版使用 FastAPI + Jinja2 + HTMX，后续可替换独立前端）。

2. 业务编排层（Scheduler/Task Service）
- 任务入队、状态机、轮询调度、超时管理、重试策略。

3. 平台适配层（Provider Adapters）
- 不同平台的页面定位、发送动作、回复完成判定、异常恢复。

4. 提取校验层（Extractor Pipeline）
- 文本清理 -> JSON 提取 -> Schema 校验 -> 缺失字段补问。

5. 存储与可观测层
- SQLite（MVP）+ 可扩展 PostgreSQL。
- 结构化日志、任务指标、平台维度统计。

## 3. 目录与模块映射

与现有目录对齐：

1. src/browser
- browser_controller.py: Playwright 浏览器/上下文生命周期封装。
- session_registry.py: 会话注册、健康状态、登录态标记。
- providers/
  - base.py
  - openchat_adapter.py
  - gemini_adapter.py
  - grok_adapter.py
  - deepseek_adapter.py

2. src/prompt
- template.py: 系统提示模板与补问模板。
- generator.py: 根据文书/任务参数生成最终 prompt。

3. src/parser
- response_extractor.py: 从富文本中提取 JSON。
- json_validator.py: Pydantic schema 校验。
- retry_handler.py: 失败重试与补问决策。

4. src/models
- session.py, task.py, result.py, metrics.py。

5. src/storage
- database.py: SQLAlchemy engine/session。
- repositories.py: CRUD 抽象。
- json_archive.py: 原始回复归档（可选）。

6. src/analyzer
- statistics.py: 聚合统计（成功/失败/平台分布/耗时）。
- health.py: 会话健康与系统健康指标。

7. src/api
- main.py: FastAPI 应用入口。
- routers/
  - sessions.py
  - tasks.py
  - test_extract.py
  - metrics.py
  - logs.py

## 4. 关键数据模型（Pydantic）

```python
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional

class Provider(str, Enum):
    OPENCHAT = "openchat"
    GEMINI = "gemini"
    GROK = "grok"
    DEEPSEEK = "deepseek"

class CaseStatus(str, Enum):
    CLOSED = "Closed"
    ONGOING = "On-Going"

class Timeline(BaseModel):
    filing_date: Optional[date] = None
    judge_assignment_date: Optional[date] = None
    trial_date: Optional[date] = None
    judgment_date: Optional[date] = None

class LegalExtraction(BaseModel):
    case_status: CaseStatus
    judgment_result: str = Field(min_length=1)
    timeline: Timeline

class SessionConfig(BaseModel):
    id: str
    provider: Provider
    chat_url: str
    enabled: bool = True
    priority: int = 100

class TaskCreate(BaseModel):
    external_id: Optional[str] = None
    prompt: str
    document_text: str
    provider_hint: Optional[Provider] = None

class TaskResult(BaseModel):
    task_id: str
    status: str
    provider: Optional[Provider] = None
    raw_response: Optional[str] = None
    extracted_json: Optional[LegalExtraction] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime
```

## 5. 存储模型（SQLite 首版）

建议至少 6 张表：

1. sessions
- id, provider, chat_url, enabled, priority, login_state, health_state, last_seen_at

2. tasks
- id, external_id, status, prompt_text, document_text, provider_hint, created_at, updated_at

3. task_attempts
- id, task_id, session_id, attempt_no, started_at, finished_at, latency_ms, status, error_message

4. raw_responses
- id, task_id, provider, response_text, captured_at

5. extracted_results
- id, task_id, case_status, judgment_result,
  filing_date, judge_assignment_date, trial_date, judgment_date,
  valid_schema, extraction_error

6. system_metrics_hourly
- hour_bucket, provider, success_count, failed_count, timeout_count, avg_latency_ms

## 6. 调度与状态机

任务状态机：

1. PENDING: 已入队，待分配。
2. DISPATCHED: 已发给某会话，等待回复。
3. EXTRACTING: 已收到回复，正在提取。
4. COMPLETED: 提取成功并入库。
5. FAILED: 超过重试上限或不可恢复错误。

会话状态机：

1. READY: 可发送。
2. BUSY: 正在等待该会话回复。
3. WAIT_LOGIN: 需要人工登录。
4. UNHEALTHY: 页面异常或选择器失效。
5. RECOVERING: 正在重启浏览器/重建页面。

轮询策略：

1. 采用加权轮询（priority 越低优先级越高）。
2. 单会话并发度默认 1，防止回复串扰。
3. 任务分发时跳过 BUSY/WAIT_LOGIN/UNHEALTHY。
4. 若所有会话不可用：sleep backoff（2s, 5s, 10s，上限 30s）。

## 7. 浏览器恢复策略

1. 心跳探测：每 20s 检查 page.is_closed()、关键 DOM 是否可见。
2. 检测关闭后进入 RECOVERING：
- 重新创建 context/page。
- 打开会话 chat_url。
- 检测登录态。
3. 若未登录：标记 WAIT_LOGIN，并通过 UI 提示用户登录。
4. 登录成功后状态回到 READY，任务继续。

## 8. 提取与校验策略

提取流水线：

1. Normalizer
- 去除 markdown fence、全角标点修正、常见尾逗号修复。

2. JSON Candidate Finder
- 优先提取 ```json 代码块。
- 其次扫描首个完整花括号对象。

3. Validator
- 按 LegalExtraction schema 校验。
- 日期标准化为 YYYY-MM-DD。

4. Repair & Retry
- 缺失字段触发补问模板（最多 1 次）。
- 仍失败则任务失败，保留 raw_response 供人工处理。

## 9. API 设计（MVP + 方案2增强）

1. 会话管理
- POST /api/sessions
- GET /api/sessions
- PUT /api/sessions/{session_id}
- DELETE /api/sessions/{session_id}
- POST /api/sessions/{session_id}/open
- POST /api/sessions/{session_id}/mark-login-ok

2. 测试接口
- POST /api/test/extract
  - 输入：prompt + document_text + optional provider
  - 输出：raw_response + extracted_json + validation_errors

3. 任务接口
- POST /api/tasks
- GET /api/tasks/{task_id}
- GET /api/tasks?status=&provider=&limit=

4. 服务监控
- GET /api/metrics/summary
- GET /api/metrics/providers
- GET /api/logs?level=&provider=&task_id=&page=

## 10. 管理界面设计（首版 3 页）

1. 会话管理页
- 会话列表、启用/禁用、优先级、健康状态、登录状态。
- 一键打开链接（新标签页）供人工登录。

2. 测试页
- 输入 prompt 和正文。
- 展示原始回复、提取 JSON、校验错误。

3. 监控页
- 当前会话数、READY/BUSY/WAIT_LOGIN 数。
- 成功/失败计数、平台维度柱状图、近 24 小时趋势。
- 最近错误日志表格。

## 11. 日志与指标

日志字段建议：

- ts, level, trace_id, task_id, session_id, provider, event, message, latency_ms, retry_count

关键指标建议：

1. task_success_total / task_failed_total
2. task_timeout_total
3. provider_success_ratio
4. extraction_schema_error_total
5. session_recovery_total

## 12. 安全与合规

1. 不在日志中明文记录敏感文书全文（可截断或哈希）。
2. 对外 API 增加 token 鉴权（MVP 可用固定 token，后续升级 JWT）。
3. 数据库定期备份，支持结果导出审计。

## 13. 测试策略

1. 单元测试
- parser: JSON 提取、日期修复、schema 校验。
- scheduler: 轮询、公平性、超时回收。
- provider adapter: 选择器匹配（mock page）。

2. 集成测试
- 本地假页面模拟 chat 平台，验证发送/等待/提取全链路。

3. 端到端测试
- 2 个真实平台 + 1 个 mock 平台，验证多会话并行与恢复。

## 14. 交付验收标准（方案2）

1. 支持 4 个平台适配器（openchat/gemini/grok/deepseek）。
2. 同时管理 >= 6 个会话窗口。
3. 连续 200 条任务运行：成功率 >= 90%（以可提取有效 JSON 为准）。
4. 浏览器意外关闭后可在 60 秒内恢复并继续任务。
5. 监控页可按平台展示成功/失败统计与最近错误日志。
