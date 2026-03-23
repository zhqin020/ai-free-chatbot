# Chat Selector Optimization Plan

## 目的是什么？
根据用户的提问，当前通过硬编码模板识别聊天页面中的特定元素（比如 reply area）准确率较低，维护成本高。新的思路是在点击“标记就绪”时自动发送一条“hello”消息，然后提取页面的精简 DOM 结构，通过自带的 LLM Provider 识别出相关的 css selector，并将其拆分为独立字段以便独立维护。

## User Review Required
> [!IMPORTANT]
> - 由于数据库 `provider_configs` 结构变更（新增了独立的 `new_chat_selector` 等字段，以及 `dom_sample`），SQLite 不支持直接 drop column，我们计划添加新字段并保留原 `ready_selectors_json` 作为过渡或忽略它。由于 SQLAlchemy metadata 会在启动时 `create_all`，如果表已存在它不会自动创建新增的字段。因此我将在开发阶段通过 SQLite 的 `ALTER TABLE` 命令添加新字段，并在 ORM 模型中更新它们。
> - 系统将依赖系统内部的 `http://127.0.0.1:8000/v1/chat/completions` 这个 API 供 worker 线程去请求内置/默认的模型（或者是用户预设跑得通的 deepseek/mock_openai 等 provider），以进行 selectors 的提取。如果本地并没有默认可以进行推理的模型，这一步 LLM 抽取可能会失败或回退到原始启发式模板提取，这需要提前明确本地可用的模型接口。

## Proposed Changes

### Database Changes
#### [MODIFY] src/storage/database.py
- 为 [ProviderConfigORM](file:///home/watson/work/ai-free-chatbot/src/storage/database.py#51-88) 添加新列：`new_chat_selector`, `input_selector`, `send_button_selector`, `reply_selector`, 以及 `dom_sample`。

#### [MODIFY] src/storage/repositories.py
- 在 [ProviderConfigRepository](file:///home/watson/work/ai-free-chatbot/src/storage/repositories.py#308-437) 中，重构 `update_ready_selectors`，改为 [update_selectors](file:///home/watson/work/ai-free-chatbot/src/storage/repositories.py#309-339)：按单独字段进行更新并将 `dom_sample` 一并入库。
- 扩充 [upsert](file:///home/watson/work/ai-free-chatbot/src/storage/repositories.py#374-429) 方法，使其能正确承载新加的字段。

---
### API / Model Extensions
#### [MODIFY] src/models/provider.py
- 在 [ProviderConfigRead](file:///home/watson/work/ai-free-chatbot/src/models/provider.py#44-60), [ProviderConfigCreate](file:///home/watson/work/ai-free-chatbot/src/models/provider.py#17-29) 和 [ProviderConfigUpdate](file:///home/watson/work/ai-free-chatbot/src/models/provider.py#31-42) 内添加新的 selector 字段与 `dom_sample` 字段，使 API 接口可以传递最新的独立字段。

#### [MODIFY] src/api/routers/providers.py
- 前端请求创建、显示列表与更新 Provider 信息时将新字段带出，实现真正意义上的“独立维护”。

---
### Worker Thread LLM Parsing Logic
#### [MODIFY] src/browser/worker.py
- 修改 `mark_login_ok` 指令流程中的 [auto_extract_chat_selectors](file:///home/watson/work/ai-free-chatbot/src/browser/worker.py#278-401)（或新建函数 `llm_extract_chat_selectors`）：
  - 首先使用基于传统候选 selector 的方法，尝试定位并向页面发出一句 "hello"。
  - 等待几秒钟让可能产生的 reply area 加载。
  - 通过 `page.evaluate()` 提取页面 `document.body.innerHTML` 并剔除所有冗余标签（如 SVG、SCRIPT、STYLE、IMG等）以缩减 token 开销。
  - 通过 [TaskRepository](file:///home/watson/work/ai-free-chatbot/src/storage/repositories.py#153-306) 创建一个内部任务，将 `owner` 设为当前线程池中任意 `READY` 状态的线程。
  - **Prompt 设计**：采用结构化指令，要求返回精确的 JSON 格式（见下文）。
  - Worker 线程在循环中轮询该 Task 的状态直到 `COMPLETED`。
  - 解析 LLM 结果字典，调用 `ProviderConfigRepository.update_selectors` 保存各 selector 以及原始精简版 `dom_sample`。

## Prompt & Output Specification
LLM 将接收以下结构化 Prompt，并被要求严格执行 JSON 输出：
```markdown
# Role: AI Chat Scraper Expert
# Goal: Identify CSS selectors in the provided DOM for Playwright automation.
# Targets:
  - new_chat_selector: Button to reset/start new chat.
  - input_selector: Textarea/input for typing messages.
  - send_button_selector: Button to submit message.
  - reply_selector: Container of AI messages (assistant role).
# Constraints:
  - Return ONLY raw JSON. No markdown.
  - Use empty string if not found.
# Format:
{
  "new_chat_selector": "...",
  "input_selector": "...",
  "send_button_selector": "...",
  "reply_selector": "..."
}
```

---
### Admin UI
#### [MODIFY] src/api/static/admin-settings.html
- 在 Provider Form 中，补充 `input_selector`, `send_button_selector`, `reply_selector`, `new_chat_selector` 的输入框，这使得识别就算出错或者需要微调，依然可以在 Web 后台中人工修改。

#### [MODIFY] src/api/static/admin-settings.js
- 更改 [fillForEdit](file:///home/watson/work/ai-free-chatbot/src/api/static/admin-settings.js#137-155), [readPayload](file:///home/watson/work/ai-free-chatbot/src/api/static/admin-settings.js#198-212), 以及列表渲染等，适配对独立选择器字段的支持与修改。

## Verification Plan
### Automated Tests
- 不存在现成的集成测试涵盖整个 "Mark Ready" 流程。
- 需要编写 Python 临时脚本或者用 API 调试工具，验证新增的 `ALTER TABLE` 能否正确无误更新 DB 结构，以及 SQLAlchemy 能否成功写入各个 selector 字段和 `dom_sample`。

### Manual Verification
1. 启动项目 (`conda activate aifree` -> `python -m src.api.main`)。
2. 通过浏览器配置并选择一个测试 Provider（假设它是可用的对话提供者，或者依靠 [mock_openai](file:///home/watson/work/ai-free-chatbot/src/api/routers/mock_openai.py#313-322)）。
3. 前往 Session 管理页面，点击任意正常可用 session 的 “标记就绪” 按钮。
4. 观察 Worker 日志是否成功发起对内部 LLM`/v1/chat/completions` 接口的请求。
5. 去 Provider 设置(Settings) 页面编辑改该 Provider，检查识别出的选择器是否填在了单独的文本框里，且能够在 UI 直接修改与保存。
