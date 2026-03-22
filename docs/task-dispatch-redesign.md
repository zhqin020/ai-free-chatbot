# 任务分派与处理流程重设计方案

## 1. FastAPI 收到请求
- 校验参数（如 prompt、message、用户标识等业务必需字段）。
- 若参数缺失或非法，直接返回 400/422。
- 客户端请求不包含 provider、session_id，由 API 层自动分派。

## 2. API 读取全局 session-pool，分派 session
- 查询 session-pool，获取所有可用 session。
- 按策略（轮询、优先级、负载等）选出最佳 session。
- 异常分支：
  1. 如果所有的会话都为 UNHEALTHY 或 session_pool 为空，则返回状态：CRITICAL。
  2. 其他错误（如部分 session 状态异常、分派策略异常等），返回失败 FAIL。

## 3. 根据 session.owner 创建 task，写入 owner
- 取 session.owner（thread-id），若 owner 为空或无效，返回 500。
- 创建 task，owner 字段填 session.owner，补全 session_id、provider 等。
- 异常分支：
  - owner 为空/无效：返回 500，提示“session owner 不可用”。
  - 数据库写入失败：返回 500，记录详细错误。

## 4. 将 task 加入全局 task-pool，状态=ASSIGNED
- 任务入库，状态设为 ASSIGNED。
- 异常分支：
  - task-pool 写入失败（如唯一约束、连接异常）：返回 500，记录日志。

## 5. worker 线程拉取 owner=自己且状态=ASSIGNED 的 task
- worker 线程定期拉取 owner=自己且 status=ASSIGNED 的任务。
- 拉取后原子更新为 BUSY，防止并发重复处理。
- 异常分支：
  - 状态流转失败（如并发冲突）：重试或记录警告。
  - 任务数据不完整：跳过并报警。

## 6. worker 处理完成，设置状态为 COMPLETED
- 处理成功，原子更新为 COMPLETED，写入结果。
- 处理失败，更新为 FAILED，记录错误信息。
- 异常分支：
  - 处理超时/异常：更新为 FAILED，写入异常详情。
  - 结果写入失败：重试或报警。

## 7. 客户端查询任务状态
- GET /api/tasks/{task_id} 返回任务详情。
- 异常分支：
  - 任务不存在：返回 404。
  - 任务数据不完整：返回 500，记录日志。

## 8. task-pool 检查要点
- 必须有 owner 字段，且为有效 thread-id。
- 必须有 session_id、provider 字段，且与 session-pool一致。
- 状态字段需支持 ASSIGNED、BUSY、COMPLETED、FAILED 等。
- 支持 owner+status 多条件高效查询。
- 状态流转需原子（如用数据库事务或乐观锁）。
- 任务唯一性、幂等性需保证（如 task_id 唯一）。

---

如需进一步细化分派策略、异常兜底、监控告警等，可在此文档基础上补充。