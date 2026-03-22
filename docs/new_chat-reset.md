# Auto-Reset Chat Feature Implementation Plan

## User Review Required
- **Schema Migrations**: I will execute `ALTER TABLE` to add `max_chat_rounds` to the `task_dispatch_config` table and `chat_rounds` to the [sessions](file:///home/watson/work/ai-free-chatbot/src/browser/worker.py#688-705) table.
- **UI Modifications**: I will add a "最大连续对话轮数 (Max Chat Rounds)" input field to the "Task Dispatch Mode" form in the Provider Settings Console.
- **Worker Logic**: After a task completes successfully, if the number of rounds for that session exceeds the configured threshold, the worker will automatically attempt to click the `new_chat_selector`. 

## Proposed Changes

### Database Schema and Models
#### [MODIFY] src/storage/database.py
- Add `max_chat_rounds` to [TaskDispatchConfigORM](file:///home/watson/work/ai-free-chatbot/src/storage/database.py#76-87).
- Add `chat_rounds` to [SessionORM](file:///home/watson/work/ai-free-chatbot/src/storage/database.py#24-48).

#### [MODIFY] src/models/provider.py
- Add `max_chat_rounds: int = 0` to [TaskDispatchConfigRead](file:///home/watson/work/ai-free-chatbot/src/models/provider.py#57-60) and [TaskDispatchConfigUpdate](file:///home/watson/work/ai-free-chatbot/src/models/provider.py#62-64).

#### [MODIFY] src/storage/repositories.py
- Update [TaskDispatchConfigRepository](file:///home/watson/work/ai-free-chatbot/src/storage/repositories.py#369-405) to read/write `max_chat_rounds`.
- Update [SessionRepository](file:///home/watson/work/ai-free-chatbot/src/storage/repositories.py#26-135) to add `increment_chat_rounds(session_id)` and `reset_chat_rounds(session_id)` methods.

---
### UI and API
#### [MODIFY] src/api/routers/providers.py
- Update [update_dispatch_mode](file:///home/watson/work/ai-free-chatbot/src/api/routers/providers.py#56-60) to handle `max_chat_rounds`.

#### [MODIFY] src/api/static/admin-settings.html
- Add input `<input id="dispatch-max-rounds" type="number" min="0" value="0" />` to the dispatch form.

#### [MODIFY] src/api/static/admin-settings.js
- Read `max_chat_rounds` in [loadDispatchMode()](file:///home/watson/work/ai-free-chatbot/src/api/static/admin-settings.js#173-179).
- Send `max_chat_rounds` in [handleDispatchSubmit()](file:///home/watson/work/ai-free-chatbot/src/api/static/admin-settings.js#180-186).

---
### Worker Logic
#### [MODIFY] src/browser/worker.py
- In [run_once](file:///home/watson/work/ai-free-chatbot/src/browser/worker.py#423-469) / `_process_task`: After a successful response, call `session_repo.increment_chat_rounds(session_id)`.
- If rounds >= `max_chat_rounds` (and > 0), trigger `new_chat_selector` via Playwright and call `session_repo.reset_chat_rounds(session_id)`.

## Verification Plan
### Automated SQL Setup
- Run `sqlite3 data/app.db "ALTER TABLE task_dispatch_config ADD COLUMN max_chat_rounds INTEGER NOT NULL DEFAULT 0;"`
- Run `sqlite3 data/app.db "ALTER TABLE sessions ADD COLUMN chat_rounds INTEGER NOT NULL DEFAULT 0;"`

### Manual Verification
- Ask the USER to go to the UI at `/admin/settings`, observe the new parameter field, and set it to 1.
- Run the extraction test script ([example_test_extract_api.py](file:///home/watson/work/ai-free-chatbot/examples/example_test_extract_api.py)) with multiple requests.
- Verify in worker logs that `new_chat_selector` is clicked after 1 round, allowing the context to reset.
