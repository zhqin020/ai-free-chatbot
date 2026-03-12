# 001 - plan rebaseline and UI priority

- status: open
- owner: TBD
- expected_fix_time: 2026-03-14

## 问题描述
根据最新决策，开发计划需要重新基线：
1. 成功率口径改为按任务统计。
2. 4 平台都需要达标。
3. 管理界面优先级前置。

## 复现步骤
1. 查看现有计划中优先级与验收条目。
2. 对照最新决策检查是否一致。

## 相关文件
- docs/implementation-plan.md

## 处理记录
- 2026-03-11: 已更新计划文档中的优先级、验收定义与下一步执行建议。
- 2026-03-11: 已实现会话管理页 MVP（`/admin/sessions`）并对接 sessions API（CRUD、启停、mark-login-ok、open）。
- 2026-03-11: 已新增 UI 可访问性测试并通过：`tests/test_sessions_ui.py`。
- 2026-03-11: 已完成会话页增强（搜索筛选、批量启停、最近错误摘要）并通过回归测试。
- 2026-03-11: 已新增浏览器 E2E 交互测试（创建 -> 筛选 -> 批量禁用 -> 删除）：`tests/test_sessions_ui_e2e.py`（`RUN_UI_E2E=1` 时执行）。
- 2026-03-11: 已完成测试页 MVP（`/admin/test-extract`），前端对接 `/api/test/extract` 并展示 generated_prompt、raw_response、extracted_json、validation_errors、retry_prompt。
- 2026-03-11: 已更新 README 操作说明，补齐服务启动流程、环境变量设置、管理页面访问入口与常见排查。
- 2026-03-11: 已将测试页示例升级为 requirement 风格模板（提示词模板 + 正文示例 + raw response 示例），可一键填充。
- 2026-03-11: 已新增统一入口页（`/admin`）与设置/查询页面（`/admin/settings`, `/admin/query`），并将会话页和测试页接入统一导航。
- 2026-03-11: 已修复测试页模板误提交流程：新增 raw_response 占位符检测，避免将 `结案|正在进行`、`YYYY-MM-DD` 等模板值直接提交。
- 2026-03-11: 已在 examples 目录补齐接口示例代码（sessions/tasks/test_extract/metrics/logs），便于外部程序参考调用。
- 2026-03-11: 已将 JSON 返回模板更新为 requirement 指定结构（含 case_id/hearing/Applicant_file_completed/reply_memo/Sent_to_Court），并同步更新校验器、提示词模板、测试页与相关测试。

## 完成标准
1. 文档口径与最新决策一致。
2. 后续任务与提交流程按该 issue 持续追踪。
