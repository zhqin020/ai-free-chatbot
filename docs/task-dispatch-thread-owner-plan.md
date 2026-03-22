# 任务分派去中心化 thread-owner 方案

## 近期更新计划

1. 设计并补充 task_pool 结构，增加 owner 字段（thread-id/worker-id）
2. 修改 API 层任务分派逻辑：
   - 遍历 session_pool，选健康 session，owner 设为 thread-id
   - 若无可用 session，直接返回 CRITICAL error
3. 修改 worker 线程主循环：
   - 只拉取 owner=自己 thread-id 的任务
   - 处理完成后原子更新任务状态
4. 保证 task_pool 线程安全，所有状态变更原子
5. 移除原有调度器/dispatch_next 相关逻辑
6. 测试端到端流程，确保无跨线程 page 复用
7. 更新文档与注释，规范开发流程

---
如需分布式/多机扩展，后续可将 task_pool 升级为分布式队列/数据库。
