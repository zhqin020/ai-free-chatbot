# 005-session-pool-key-consistency.md

## 问题描述

在多 provider/多 session 并发场景下，发现如下问题：
- 已经打开的 provider chat 页面未被 session_pool 监控，导致 worker 或管理页面重复打开新页面，资源浪费。
- pool._entries 中缺少已打开页面的 key，页面无法被唯一复用。
- 主要原因是 pool key 生成和查找方式不统一，或多处实例化 pool 导致状态不共享。

## 复现步骤
1. 通过管理页面或 worker 打开 provider chat 页面。
2. 再次通过“open browser”或任务调度请求同一 provider/session，发现会新开页面而不是复用。
3. 日志显示 pool._entries 中 key 不一致或缺失。

## 解决方案
- 全局统一 pool key 生成方式，新增 make_pool_key(provider, session_id) 工具函数，所有入口都用此函数生成/查找 key。
- 确保全局只用一个 BrowserSessionPool 实例（如 _open_pool 单例），禁止多处 new。
- 所有页面都通过 pool.get_page 打开，禁止直接 new_page。
- get_page 增强日志，打印 pool._entries.keys()，便于调试。
- ProviderSessionPoolManager 类型注解全部替换为 str，消除 NameError。

## 处理过程
- 批量修正 session_pool.py，统一 key 生成与查找。
- 增强 get_page 日志，便于追踪页面注册与复用。
- 修正类型注解，保证兼容性。

## 当前状态
- 代码已修正，所有页面都能被唯一监控和复用，日志可追踪。
- 如需进一步批量修正其他入口或前端参数校验，后续可继续跟进。

## 状态
open

---
如有新问题请在本 issue 下追加记录。