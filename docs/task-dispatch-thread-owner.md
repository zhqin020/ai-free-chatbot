# 任务分派去中心化方案（thread-owner 绑定）

## 方案背景

为彻底避免 Playwright page/session_pool 跨线程复用风险，提升任务分派灵活性，采用“去中心化调度”方案：
- 可取消统一调度器（如 WeightedRoundRobinScheduler）模块，但在选择 worker 线程时，仍需保留“轮询分配”和“按优先级分配”两种方法，供 API 层分配任务 owner 时选择。
- 任务 owner 绑定 thread-id，API 层直接分配
- worker 线程只处理 owner=自己 thread-id 的任务
- 全局 task_pool 线程安全，所有线程可读写

## 方案要点
1. **API 层任务分派**
   - API 收到任务请求时，遍历 session_pool，选健康 session，获取其 thread-id
   - 任务 owner 字段设为 thread-id，写入全局 task_pool
   - 若无可用 session，直接返回 CRITICAL error

2. **worker 线程处理**
   - 每个 worker 线程定期扫描 task_pool，拉取 owner=自己 thread-id 的任务
   - 处理完成后，原子更新任务状态

3. **客户端查询**
   - 客户端通过 API 轮询查询任务状态，直到完成/失败

4. **线程安全**
   - task_pool 必须线程安全（如数据库表、线程安全队列、加锁等）
   - 任务 owner 字段唯一标识线程（thread.ident 或 worker_id）

## 计划步骤
1. 设计并补充 task_pool 结构，增加 owner 字段
2. 修改 API 层任务分派逻辑，分配 owner=thread-id
3. 修改 worker 线程主循环，只处理 owner=自己 thread-id 的任务
4. 保证 task_pool 线程安全，所有状态变更原子
5. 移除原有调度器/dispatch_next 相关逻辑
6. 测试端到端流程，确保无跨线程 page 复用
7. 更新文档与注释，同步开发规范

## 兼容性与扩展
- 支持多 worker/多线程/多进程横向扩展
- 任务分派策略可灵活调整（如优先级、负载均衡等）
- 兼容现有 API 查询与任务状态流转

---
如需分布式/多机扩展，可进一步将 task_pool 升级为分布式队列/数据库。
