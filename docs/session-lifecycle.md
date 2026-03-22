# Session 生命周期梳理

## 1. 创建

**前提：** 仅当当前 provider 没有对应 session 时，才会创建新 session。

### 主要创建场景：
1. **自动发现**：通过 `/api/sessions/discover`，遍历所有 provider，自动为每个 provider 创建默认 session（如 `s-provider-1`），初始状态为 READY。
2. **Provider 页面 “open browser” 操作**：在 provider 管理页面点击“open browser”时，若该 provider 没有 session，则会拉起浏览器并创建 session，随后自动异步检测页面状态，若可用则标记为 READY。
3. **服务启动时自动拉起**：worker 线程启动后，自动为每个 provider 拉起浏览器并创建 session，后续检测页面状态，流程同“open browser”。
4. **会话管理页面“发现并刷新”按钮**：点击“发现并刷新”时，若某 provider 尚无会话，则自动拉起浏览器并创建 session。
5. **provider 新增时**：自动为新 provider 创建对应 session。
6. **手动创建**：通常被禁用，仅用于特殊场景（如测试），通过 API 或后台管理手动添加 session。

## 2. 更改

### 后台自动更改：
- 状态变更：通过任务分配、登录、验证、异常等操作，session 状态可在 READY、BUSY、WAIT_LOGIN、UNHEALTHY、RECOVERING 间切换。
  - 任务分配：分配任务后，状态变为 BUSY。
  - 登录成功：标记为 READY，`/api/sessions/{session_id}/mark-login-ok`。
  - 登录/验证失败：变为 WAIT_LOGIN 或 UNHEALTHY。
  - 自动恢复：RECOVERING 状态，后台自动尝试恢复。
- 属性变更：如 chat_url、login_state、优先级等，可通过 API 更新。

### Web 界面操作更改：
1. **“发现并刷新”/“验证会话”**：
   - 对于已存在的 session，主动检查浏览器页面真实状态，并根据检测结果更新 http session、状态等。
   - 如果会话已失效（如过期、浏览器关闭、异常），会自动重置 session 对象，重新拉起浏览器并更新会话记录。
2. **“标记就绪”**：
   - 用于人工强制将 session 状态设置为 READY，便于任务分派。
   - 适用于程序无法自动确认页面状态时，由操作人员手动确认。
   - 若浏览器对象或会话记录异常，操作时应显示详细信息，便于人工判断（如需人工登录或关闭浏览器后重试）。

## 3. 删除
- provider 删除时：自动删除所有关联 session。
- 手动删除：通过 `/api/sessions/{session_id}` DELETE 或后台管理操作。
- 自动清理：如 session 长期 UNHEALTHY 或失效，后台可定期清理。

## 4. 典型流程
- provider 新增 → 自动创建 session（READY）
- 用户登录/验证 → session 状态变为 READY
- 任务分配 → session 状态变为 BUSY
- 任务完成 → session 状态恢复为 READY
- 登录失效/异常 → session 状态变为 WAIT_LOGIN/UNHEALTHY
- provider 删除 → session 自动删除

---
如需详细代码入口或具体 API 路径，请补充说明。