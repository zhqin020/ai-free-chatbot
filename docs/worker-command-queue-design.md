# Worker线程安全页面操作与命令队列方案

## 设计原则
- FastAPI 线程绝不直接操作 Playwright/page 对象。
- 所有页面相关操作（如拉起浏览器、读取页面内容、执行交互）必须由对应 worker 线程完成。
- 采用线程安全的命令队列实现 FastAPI 与 worker 线程间的异步通信。
- 支持轻量级消息队列（如 Python Queue、multiprocessing.Queue、sqlite/文件队列等），避免 Redis 这类重型依赖。

## 推荐流程
1. FastAPI 线程接收前端请求，仅读取 session/task 信息，不直接操作页面。
2. FastAPI 线程根据请求内容，生成命令消息（包含命令类型、参数、目标 session、目标 worker 线程 id）。
3. 命令消息写入全局线程安全命令队列。
4. 各 worker 线程轮询/监听命令队列，只处理 owner=自己 thread-id 的命令，执行页面操作。
5. worker 执行完毕后，将结果写回结果队列（或命令消息内结果字段）。
6. FastAPI 线程轮询/等待结果，获取后返回 API 响应。

## 轻量级队列选型建议
- Python 标准库 queue.Queue（适合单进程多线程）
- multiprocessing.Queue（适合多进程）
- sqlite/本地文件队列（适合持久化、进程间通信）
- 仅在高并发/分布式场景下再考虑 Redis/RabbitMQ

## 消息结构建议
- command_id: 唯一标识
- command_type: 操作类型（如 verify_session, reload_page, extract_selector 等）
- params: 具体参数
- target_thread_id: 目标 worker 线程 id
- session_id/task_id: 关联对象
- status/result: 执行状态与结果

## 实施计划
1. 设计命令消息结构与全局线程安全队列接口
2. FastAPI 层所有页面相关 API 改为写入命令队列并等待结果
3. worker 线程主循环增加命令队列轮询与处理逻辑
4. 结果回写与 API 响应机制
5. 端到端测试，确保无跨线程 page 复用
6. 文档与注释完善，开发流程规范化

---
如需具体代码模板或接口定义，请补充需求。
