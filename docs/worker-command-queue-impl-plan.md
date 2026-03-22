# 命令队列与线程安全页面操作改造计划

## 目标
- 使用 Python 标准库 queue.Queue 实现 FastAPI 与 worker 线程间的命令异步通信。
- FastAPI 线程不再直接操作 page/playwright，只写入命令队列并等待结果。
- worker 线程轮询命令队列，执行页面操作并写回结果。

## 步骤

1. 在 src/browser/worker.py 新增全局线程安全命令队列和结果队列（queue.Queue）。
2. 设计命令消息结构（command_id, command_type, params, target_thread_id, status, result 等）。
3. FastAPI 层（src/api/routers/worker.py）页面相关 API 改为写入命令队列并等待结果，不再直接 get_page。
4. worker 线程主循环增加命令队列轮询与处理逻辑，只处理 owner=自己 thread-id 的命令。
5. worker 执行命令后将结果写回结果队列，FastAPI 线程轮询/等待结果后响应前端。
6. 端到端测试，确保无跨线程 page 复用。
7. 更新文档与注释，规范开发流程。

## 代码分工建议
- 命令队列/消息结构定义：src/browser/worker.py
- FastAPI API改造：src/api/routers/worker.py
- worker主循环命令处理：src/browser/worker.py
- 结果队列与API响应：src/api/routers/worker.py

---
如需具体代码模板或接口定义，请补充需求。
