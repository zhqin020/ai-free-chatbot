# 任务计划：多线程会话池重构

## 目标
- 实现每线程独占一个浏览器会话，彻底解决多进程 session pool 不一致问题。

## 步骤
1. 设计全局 session pool 单例，支持线程安全 get_or_create_session。
2. 新增 worker 线程池管理模块，每线程独占会话。
3. 任务分发机制调整，按 session_id/provider 分配到线程。
4. Playwright 对象管理调整，禁止跨线程传递。
5. API/worker 合并进程，所有操作共享 session pool。
6. 测试高并发和异常回收。

## 跟踪
- [ ] 设计文档已保存 docs/threaded-session-pool-design.md
- [ ] session_pool 单例实现
- [ ] worker 线程池实现
- [ ] 任务分发与线程绑定
- [ ] Playwright 对象隔离
- [ ] API/worker 合并与验证
- [ ] 并发与异常测试

## 负责人
- watson

## 期望完成时间
- 2026-03-20
