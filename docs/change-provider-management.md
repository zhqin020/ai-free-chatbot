# Add Provider Parameters

## proposed Changes

需要在provider管理页面增加几个功能：
每个provider 增加三个参数：
是否需要登录： 默认需要登录，如果选择不需要登录，则每次打开页面时，都需要清空cookie
enable/disable: 如果禁用，则启动服务时，不能启动会话，也不能进行打开页面的操作
lock/unlock: 锁定后，该记录被保护，不能被删除

### [Models & Database]

#### [MODIFY] src/storage/database.py

- Add `need_login`, `enable`, `lock` columns to [ProviderConfigORM](file:///home/watson/work/ai-free-chatbot/src/storage/database.py#51-75) with `BOOLEAN NOT NULL` and default values.

#### [MODIFY] src/models/provider.py

- Extend [ProviderConfigCreate](file:///home/watson/work/ai-free-chatbot/src/models/provider.py#17-21), [ProviderConfigUpdate](file:///home/watson/work/ai-free-chatbot/src/models/provider.py#23-26), [ProviderConfigRead](file:///home/watson/work/ai-free-chatbot/src/models/provider.py#28-36) Pydantic models with `need_login` (default True), `enable` (default True), and `lock` (default False).

#### [NEW] scripts/migrate_provider_flags.sql

- Create a SQL migration script containing the `ALTER TABLE` commands for `provider_configs`:
  ```sql
  ALTER TABLE provider_configs ADD COLUMN need_login BOOLEAN NOT NULL DEFAULT 1;
  ALTER TABLE provider_configs ADD COLUMN enable BOOLEAN NOT NULL DEFAULT 1;
  ALTER TABLE provider_configs ADD COLUMN lock BOOLEAN NOT NULL DEFAULT 0;
  ```

### [Backend Logic & API]

#### [MODIFY] src/storage/repositories.py

- Update `ProviderConfigRepository.upsert` to save `need_login`, `enable`, `lock`.
- Update `DEFAULTS` dictionary to include default bool states for built-in providers.

#### [MODIFY] src/api/routers/providers.py

- Update [delete_provider](file:///home/watson/work/ai-free-chatbot/src/api/routers/providers.py#89-104) to raise `HTTPException(status_code=403)` if `row.lock` is True.
- Update [open_provider](file:///home/watson/work/ai-free-chatbot/src/api/routers/providers.py#106-143) to raise `HTTPException(status_code=403)` if `row.enable` is False.

#### [MODIFY] src/browser/worker.py

- In [start_all_worker_threads](file:///home/watson/work/ai-free-chatbot/src/browser/worker.py#98-119), filter [providers](file:///home/watson/work/ai-free-chatbot/src/api/routers/providers.py#44-48) to only start thread for enabled ones.

#### [MODIFY] src/browser/session_pool.py

- In [get_page](file:///home/watson/work/ai-free-chatbot/src/browser/session_pool.py#94-163) and [get_or_create_provider_session](file:///home/watson/work/ai-free-chatbot/src/browser/session_pool.py#228-251), fetch the [ProviderConfigORM](file:///home/watson/work/ai-free-chatbot/src/storage/database.py#51-75) by [provider](file:///home/watson/work/ai-free-chatbot/src/browser/worker.py#666-673). If `row.need_login` is `False`, execute `await controller.context.clear_cookies()` before opening the page.

### [Frontend/UI]

#### [MODIFY] src/api/static/admin-settings.html

- Add three checkbox inputs (`id="provider-need-login"`, `id="provider-enable"`, `id="provider-lock"`) inside the `Provider form` grid.
- Update the Providers table headers to include new columns or a combined status/flags column.

#### [MODIFY] src/api/static/admin-settings.js

- In [readPayload()](file:///home/watson/work/ai-free-chatbot/src/api/static/admin-settings.js#166-173), include `need_login`, `enable`, `lock` from checkbox state.
- In [fillForEdit()](file:///home/watson/work/ai-free-chatbot/src/api/static/admin-settings.js#121-131), populate the checkboxes based on the row data.
- In [resetForm()](file:///home/watson/work/ai-free-chatbot/src/api/static/admin-settings.js#110-120), reset to default state (`need_login=true`, `enable=true`, `lock=false`).
- In [renderRows()](file:///home/watson/work/ai-free-chatbot/src/api/static/admin-settings.js#132-160), visualize the properties using status indicators (e.g. `✅ / ❌`, or badges).

## Verification Plan

### Automated Tests

- Run backend unit tests (`pytest tests/test_providers_api.py`) if they exist. We might need to mock or add a quick test handling the `lock` and `enable` errors.

### Manual Verification

1. Apply the migration using SQLite.
2. Start the API/UI. Create a testing provider with `need_login=False`, `enable=True`, `lock=True`.
3. Try deleting it -> Should show 403 Forbidden.
4. Open the Provider page -> Observe that cookies are cleared upon start by checking Playwright context manually or using a site that drops a cookie.
5. Change to `enable=False` -> Try opening the browser -> Should give 403.
6. Check that built-in providers keep functionality as expected.
