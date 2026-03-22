
# 任务与会话状态机（2026架构梳理版）

## 设计原则

1. 客户端只做两件事：创建任务、轮询状态。
2. 服务端任务分发与会话状态解耦，worker 只消费 READY 会话。
3. 任务失败不自动重试，重试由客户端决定。
4. 会话状态严格区分 READY/BUSY/WAIT_LOGIN/UNHEALTHY，调度只分配 READY。

## 任务状态（TaskStatus）

- PENDING：任务已入队，等待分发。
- DISPATCHED：worker 已认领，正在执行。
- EXTRACTING：收到 provider 响应，做 JSON 提取。
- COMPLETED：提取到合法 JSON，任务完成。
- FAILED：处理失败（超时、页面未就绪、响应非 JSON、解析失败）。

## 会话状态（SessionState）

- READY：可用，允许分配任务。
- BUSY：已分配任务，未完成前不可再分配。
- WAIT_LOGIN：需人工登录/验证。
- UNHEALTHY：不可用，需人工干预。
- RECOVERING：自动恢复中。

## 状态流转链路

### 任务流转

1. 创建任务：PENDING
2. 调度分配 READY 会话：PENDING → DISPATCHED，session.state: READY → BUSY
3. worker 执行任务，收到 provider 响应：DISPATCHED → EXTRACTING
4. JSON 提取成功：EXTRACTING → COMPLETED，session.state: BUSY → READY
5. 任一步失败：DISPATCHED/EXTRACTING → FAILED，session.state: BUSY → READY/WAIT_LOGIN/UNHEALTHY（视失败类型）

### 会话流转

- READY → BUSY：被调度分配任务时
- BUSY → READY：任务完成或失败（非致命错误）
- BUSY → WAIT_LOGIN：遇到登录/验证/人工干预需求
- BUSY → UNHEALTHY：遇到致命运行时错误
- WAIT_LOGIN/UNHEALTHY → READY：人工干预后恢复

## 关键实现要点

- 只有 READY 会话可被调度，BUSY/WAIT_LOGIN/UNHEALTHY 均不可分配。
- worker 任务完成/失败后，必须显式回写 session 状态（见 scheduler.mark_attempt_success/failed）。
- recover_stuck_busy_sessions 定期将长时间 BUSY 的会话恢复为 READY，防止死锁。
- 任务状态推进与会话状态推进解耦，任何异常都应保证最终 session 状态可恢复。

## 常见问题与排查

- 任务一直 PENDING：无 READY 会话或 worker 未运行。
- 任务直接 FAILED：会话 WAIT_LOGIN/UNHEALTHY，或 provider 响应异常。
- 会话卡 BUSY：worker 异常未回写状态，或进程崩溃，需 recover_stuck_busy_sessions 兜底。
