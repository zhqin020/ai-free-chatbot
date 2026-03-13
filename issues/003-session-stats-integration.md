# Issue 003: Session Stats Integration

- status: open
- owner: tbd
- target_time: tbd

## 背景
当前会话管理页面已新增 `stats` 操作入口，但仅返回占位结果。需求是统计当前会话已完成交互数量，并在会话页可视化展示。

## 现状
- 已有占位 API: `GET /api/sessions/{session_id}/stats`
- 当前返回: `implemented=false` + 待实现说明

## 期望
- 返回每个会话已完成交互数量（可按时间窗口过滤）
- 与现有 metrics/logs 数据源对齐，避免重复计数
- 前端会话页 stats 按钮展示真实数值或弹窗明细

## 相关文件
- src/api/routers/sessions.py
- src/storage/repositories.py
- src/api/static/admin-sessions.js
- src/api/routers/metrics.py

## 拆解建议
1. 定义 completed interaction 计数口径（任务完成 + 有有效响应 + 归属 session）
2. 新增仓储查询方法，按 session_id 聚合
3. 实现 `GET /api/sessions/{session_id}/stats`
4. 前端显示总数与最近 24h 数
5. 补充测试（API + repository）
