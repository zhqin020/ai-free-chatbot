# 多线程会话池方案设计

## 目标
- 每个 worker 线程独占一个浏览器会话（Page/Context），线程与会话一一对应。
- 彻底避免多进程下 session pool 不一致、浏览器对象无法复用的问题。
- 支持高并发、线程安全、易于扩展。

## 架构要点
1. 主进程维护全局 session pool（dict 或 BrowserSessionPool 单例）。
2. 启动 N 个 worker 线程，每个线程只操作自己分配的 session/page。
3. 线程与会话一一绑定，互不干扰，无需加锁。
4. 任务分发时按 session_id/provider 分配到对应线程。
5. 线程启动时拉起浏览器会话，结束时关闭。
6. API/worker 合并进程，所有操作共享同一 session pool。

## 关键实现点
- session_pool.py：线程安全管理所有会话，提供 get_or_create_session(session_id)。
- worker_manager.py/worker.py：线程池管理，每线程独占会话。
- 任务分发：按 session_id 分配到线程，线程安全队列管理。
- Playwright 对象：每线程独占，禁止跨线程传递。
- API 直接操作全局 session pool。

## 迁移建议
- 先实现单进程多线程 worker，验证无多进程问题后再考虑横向扩展。
- 如需多进程，需引入专用浏览器服务进程或远程控制。
