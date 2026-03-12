# AI Chat 自动化提问与结构化提取系统 - 开发计划（方案 2）

## 1. 计划说明

目标周期：4 周（20 个工作日）

交付目标：

1. 4 平台适配（openchat, gemini, grok, deepseek）。
2. 多会话轮询调度与自动恢复。
3. JSON 提取校验与重试。
4. API 服务 + 管理界面 + 监控统计。

## 2. 里程碑

1. M1（第 1 周末）
- 单会话打通 + 基础 API + 基础提取。

2. M2（第 2 周末）
- 多会话轮询 + 超时机制 + 恢复机制。

3. M3（第 3 周末）
- 完整提取校验链路 + 存储 + 指标。

4. M4（第 4 周末）
- 管理界面 + 完整测试 + 部署文档。

## 3. 按天任务拆解

### 第 1 周：基础骨架与单链路贯通

1. Day 1
- 初始化配置与日志模块。
- 建立基础数据模型（session/task/result）。
- 建立 SQLite schema 与迁移脚本。

2. Day 2
- 实现 BrowserController 生命周期管理。
- 完成 ProviderAdapter 基类定义。

3. Day 3
- 接入 openchat 适配器，打通发送与回复读取。
- 增加登录态检测与 WAIT_LOGIN 标记。

4. Day 4
- 实现 PromptGenerator（主提示 + 补问提示模板）。
- 实现基础 ResponseExtractor（代码块提取 + 花括号扫描）。

5. Day 5
- 完成 POST /api/tasks 与 GET /api/tasks/{id}。
- 完成首个端到端链路：提交任务 -> 调用会话 -> 存储结果。

### 第 2 周：多会话调度与故障恢复

1. Day 6
- 实现 SessionRegistry（会话增删改查、状态管理）。
- 实现 /api/sessions 系列接口。

2. Day 7
- 实现 Scheduler（加权轮询、会话挑选、任务分发）。
- 单会话并发限制为 1。

3. Day 8
- 增加超时回收机制（DISPATCHED 超时转重试）。
- 增加 task_attempts 记录。

4. Day 9
- 实现浏览器健康检查（page close、关键 DOM 探测）。
- 实现自动恢复流程（重建 context/page、回填状态）。

5. Day 10
- 接入 gemini/grok/deepseek 适配器首版。
- 完成多平台 smoke test。

### 第 3 周：提取质量与可观测性

1. Day 11
- 引入 Pydantic 校验器与日期标准化。
- 完成 extraction error 分类。

2. Day 12
- 实现 retry_handler（补问一次 + 最终失败归档）。
- 增加 raw_responses 与 extracted_results 存储。

3. Day 13
- 完成 POST /api/test/extract。
- 输出 raw_response + extracted_json + validation_errors。

4. Day 14
- 实现 metrics 聚合（成功/失败/超时/均耗时）。
- 完成 /api/metrics/summary 与 /api/metrics/providers。

5. Day 15
- 完成结构化日志查询接口 /api/logs。
- 建立问题定位视图（按 task_id/session_id 过滤）。

### 第 4 周：管理界面与稳定性收敛

1. Day 16
- 完成会话管理页（增删改查、启停、优先级、打开链接）。

2. Day 17
- 完成测试页（prompt + 正文 + 结果可视化）。

3. Day 18
- 完成监控页（运行状态、平台统计、错误日志）。

4. Day 19
- 补齐单测、集成测试、端到端回归。
- 重点压测轮询与恢复场景。

5. Day 20
- 发布准备：运行手册、部署说明、故障排查手册。
- 验收并冻结版本。

## 4. 任务优先级（Must/Should/Could）

1. Must
- 多会话轮询与超时回收。
- 浏览器异常恢复。
- JSON 提取 + schema 校验。
- 核心 API（sessions/tasks/test/metrics）。
- 管理界面三页（会话管理、测试页、监控页）。
- 4 平台全部达标（openchat/gemini/grok/deepseek）。

2. Should
- 平台维度统计和日志筛选。
- 发布前稳定性压测与恢复演练。

3. Could
- WebSocket 实时推送。
- PostgreSQL 切换与多实例调度。

## 5. 风险与预案

1. 平台 DOM 变化导致适配器失效
- 预案：每平台维护选择器优先级列表 + 回退策略。

2. 登录态过期频繁
- 预案：会话置 WAIT_LOGIN，UI 强提醒，人工一键恢复。

3. 回复格式波动导致抽取失败
- 预案：强约束提示词 + 一次补问 + 错误归档人工复核。

4. 并发上升导致资源不足
- 预案：限制会话并发、任务队列削峰、批处理窗口化。

## 6. 人力建议

最小配置：2 人

1. 后端/编排工程师（1 人）
- 负责 scheduler、api、storage、metrics。

2. 自动化/提取工程师（1 人）
- 负责 provider adapters、parser、重试策略、E2E。

可选第 3 人（前端）：

1. 管理界面与可视化监控。

## 7. 验收清单

1. 功能验收
- 会话管理可增删改查并可打开登录页。
- 提交任务后可成功获取结构化结果。
- 多会话轮询时，不会因单会话卡住阻塞整体。
- 浏览器关闭后可自动恢复。

2. 指标验收
- 连续任务成功率 >= 90%（按任务统计：成功任务数 / 已完成任务总数，其中已完成任务总数 = 成功 + 失败）。
- 恢复时延 <= 60 秒。
- API 可稳定查询任务与统计。
- 4 平台分别达标（openchat、gemini、grok、deepseek 均满足成功率与恢复时延指标）。

3. 工程验收
- 单元测试覆盖 parser/scheduler 核心路径。
- 关键日志具备 trace_id/task_id。
- 文档完整（运行、配置、故障排查）。

## 8. 第一个迭代建议（明天即可开工）

1. 先完成 openchat 单平台端到端。
2. 同步打通 tasks API 与数据库落盘。
3. 以测试页验证提取质量，再扩展到 4 平台。

## 9. 下一步执行建议（基于最新决策）

### 第 1 优先级：管理界面前置（先做可用再做增强）

1. Day A
- 完成会话管理页 MVP：会话增删改查、启停、优先级、打开登录链接。
- 对接 `/api/sessions` 全量接口，补充基本交互校验。

2. Day B
- 完成测试页 MVP：输入 prompt + 正文，调用 `/api/test/extract`，展示原文、提取 JSON、校验错误。
- 增加“复制结果 / 一键重试”操作。

3. Day C
- 完成监控页 MVP：任务总览、平台维度成功/失败/超时、最近错误日志。
- 对接 `/api/metrics/summary`、`/api/metrics/providers`、`/api/logs`。

### 第 2 优先级：统一验收口径与看板

1. Day D
- 在 metrics 层明确“按任务成功率”口径并固化到文档与接口字段说明。
- 在监控页展示公式与统计窗口（默认最近 24 小时，可切换 7 天）。

2. Day E
- 增加 4 平台独立验收面板，要求全部平台都达标后才显示“验收通过”。
- 为每个平台补 smoke + 失败样例回放记录。

### 第 3 优先级：稳定性收口（发布前门槛）

1. Day F
- 执行轮询与恢复压测，输出峰值并发、超时率、恢复时延分位数。
- 固化失败分类（DOM 变化、登录过期、提取失败、超时）统计。

2. Day G
- 完成回归测试与发布检查单（接口、UI、worker、数据落盘、日志追踪）。
- 发布条件：4 平台全部达标 + 管理界面三页可用 + 核心回归通过。
