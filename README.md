# ai-free-chatbot

多浏览器 AI Chat 自动提问与结构化提取服务。

当前已支持：

1. 核心 API：tasks、sessions、test/extract、metrics、logs。
2. 多平台会话管理：openchat、gemini、grok、deepseek。
3. 管理页面：会话管理页与测试提取页。
4. Worker 轮询处理与提取校验链路。

推荐先阅读：

1. 最简任务链路说明：[docs/task-state-machine.md](docs/task-state-machine.md)

## 快速开始 (Quick Start)

### 方案 A：使用 Docker (推荐，一键全环境)

```bash
# 请确保已安装 Docker 和 Docker Compose
cp .env.example .env     # 编辑 .env 设置 API_TOKEN
docker-compose up -d --build
```
访问：[http://localhost:8000/admin/sessions](http://localhost:8000/admin/sessions)

### 方案 B：本地 Conda 开发环境

#### 1. 系统依赖 (WSL 专用)
如果您在 WSL 下运行，需安装 Chrome 和系统字体以支持管理页面自动打开：
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
sudo apt install -y fonts-noto-color-emoji fonts-noto-core fonts-symbola xdg-utils
```

#### 2. 环境初始化
```bash
conda env create -f environment.yml
conda activate aifree
playwright install --with-deps chromium
cp .env.example .env
```

#### 3. 一键协同启动 (API + Worker)
```bash
python -m scripts.run_stack --open-admin-browser
```

默认会先做启动自检：

1. API 端口是否可用。
2. 数据库是否可初始化。
3. （可选）指定平台是否存在可用会话（READY + logged_in）。
4. 先启动 API 并等待 /healthz 就绪，再启动 worker。

可选参数：

python -m scripts.run_stack --no-reload
python -m scripts.run_stack --port 8001
python -m scripts.run_stack --worker-max-loops 10
python -m scripts.run_stack --require-provider-ready openchat
python -m scripts.run_stack --health-timeout-seconds 60
python -m scripts.run_stack --health-poll-interval-seconds 1.0
python -m scripts.run_stack --skip-checks
python -m scripts.run_stack --with-mock-openchat
python -m scripts.run_stack --with-mock-openchat --mock-openchat-port 8010
python -m scripts.run_stack --open-admin-browser
	# 注意：如需测试 mock_openai，请确保 provider 名称与参数一致。
	# 例如：
	# python -m scripts.run_stack --with-mock-openai --open-admin-browser
	# 并在管理页面/session 配置中选择 provider=mock_openai。
	# 若用 --with-mock-openchat，则 provider 应为 mock_openchat。
	# provider 名称不一致会导致“Open Browser”失败或 500 错误。
python -m scripts.run_stack --open-admin-browser --admin-path /admin/sessions
python -m scripts.run_stack --open-admin-browser --open-admin-browser-no-keyring

说明：

1. 在 dev 环境下，run_stack 默认会设置 WORKER_HEADLESS=0，浏览器会弹窗，便于人工登录。
2. 若 worker 检测到会话未登录，会记录 session_login_required 日志并保持会话在 WAIT_LOGIN。
3. 登录后请在 /admin/sessions 点击 Mark Login OK。
4. `--with-mock-openchat` 启用时，run_stack 会先检查 mock_openchat 是否已运行：
	1. 若已运行：记录运行状态和 PID，不重复启动。
	2. 若未运行：自动启动并等待健康检查通过。
5. `--open-admin-browser` 启用后，run_stack 会在 API 健康检查通过后，使用 WSL 环境的 `xdg-open` 打开管理页面（默认 `/admin`）。
6. `--open-admin-browser-no-keyring` 可与 `--open-admin-browser` 搭配使用：
	1. 优先尝试使用 Chromium 类浏览器并附加 `--password-store=basic`。
	2. 用于规避 `Unlock Keyring` 弹窗。
	3. 若未检测到 Chromium 类浏览器，会自动回退到 `xdg-open`。

6. 如需单独启动（调试排障时使用）

API：

#### 3. 启动服务 (API + 内部 Worker)
```bash
python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```
*注：启动 API 后，后台会自动启动任务 Worker 线程。*

---

## 核心特性
1.  **自动化会话管理**：支持主流 AI 平台 (Gemini, DeepSeek, Chaton, Merlin) 的登录维护。
2.  **结构化数据提取**：针对法律文档优化的 LLM 选择器提取与验证链路。
3.  **单进程统一模型**：无需单独启动 Worker，API 内部集成多进程/线程调度。
4.  **可视化管理**：提供 Session 管理与任务测试的管理后台。

---

## 常用命令

| 任务 | 命令 |
| :--- | :--- |
| **一键启动 (Docker)** | `docker-compose up -d --build` |
| **启动主服务 (Local)** | `python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000` |
| **初始化数据库** | `python3 scripts/init_db.py` |
| **运行单元测试** | `pytest tests/` |
| **查看 API 文档** | 启动后访问 `/docs` |

更多详细安装说明请参考 [INSTALL.md](INSTALL.md)。

## 测试策略（当前建议）

当前阶段不建议直接做端到端测试作为主验证手段，优先使用可重复、可定位问题的单元测试与集成测试。

目标：围绕“打开浏览器后，稳定且安全地进入对话窗口”建立分层保障。

1. 单元测试（无网络、无真实站点依赖）：
	- `tests/test_browser_controller.py`：覆盖普通上下文与 persistent profile 启动分支、storage state 保存。
	- `tests/test_session_pool.py`：覆盖页面健康复用与异常重建，避免失效 page 被继续复用。
2. 集成测试（本地数据库 + 处理器协作，不走真实平台）：
	- `tests/test_browser_dialog_integration.py`：覆盖未登录/人机验证分支（应置 WAIT_LOGIN）与已登录对话发送分支。
	- `tests/test_worker_processor.py`、`tests/test_scheduler.py`：覆盖调度和失败状态机，确保 WAIT_LOGIN 不被重复派发。
3. 浏览器驱动集成测试（可选，使用本地 mock 站点）：
	- `tests/test_mock_openchat_playwright_integration.py`：真实浏览器验证 cookie -> verify -> login -> chat -> JSON 输出全流程。
4. 验证命令：

pytest -q tests/test_browser_controller.py tests/test_browser_dialog_integration.py tests/test_session_pool.py tests/test_worker_processor.py tests/test_scheduler.py

RUN_UI_E2E=1 pytest -q tests/test_mock_openchat_playwright_integration.py

说明：端到端验证可作为后置冒烟检查，不应替代上述分层测试。

## 伪 OpenChat 站点（推荐先验收）

为避免真实站点带来的不稳定因素（Cloudflare、账号状态、网络波动），建议先通过本地伪站点验收浏览器交互链路，再连接正式站点。

启动命令：

python -m scripts.run_mock_openchat --port 8010

访问地址：

http://127.0.0.1:8010/

站点行为（用于测试）：

1. 首屏弹出 Cookie 设置窗口，必须点击同意。
2. 然后弹出 Cloudflare 验证窗口，点击 `Verify you are human`。
3. 再弹出登录窗口，用户名密码可任意输入。
4. 登录后进入对话窗口；发送任意内容，助手返回符合模板的 JSON。

人工验收（强制人工输入）建议：

python -m scripts.manual_mock_openchat_e2e

该脚本会启动真实浏览器并分步骤暂停，必须由人工在页面完成以下动作后按回车继续：

1. 点击 Cookie 同意。
2. 点击 Verify you are human。
3. 手工输入用户名密码并点击 Sign in。
4. 手工输入消息并发送。

只有上述步骤都完成且返回 JSON 校验通过，脚本才会输出 PASS。

容错能力说明：

1. 若页面缺少某个弹窗（例如没有 Verify 或没有 Cookie），脚本会自动识别并跳过该步骤。
2. 若页面已直接进入对话状态，脚本会跳过登录前步骤并直接进入消息发送与结果校验。
3. 若步骤校验失败，脚本不会立刻退出，而是提示重试（`r`）或退出（`q`）。
4. 脚本会采集 chat 返回内容并解析 JSON，终端会打印标准化后的 JSON 结果。

会话持久化说明：

1. mock_openchat 会将 cookie/verify/login 状态保存在浏览器本地存储（localStorage）。
2. `manual_mock_openchat_e2e` 默认使用持久化 profile 目录 `tmp/manual_mock_profile`。
3. `manual_mock_openchat_e2e` 默认固定端口 `8010`（可用 `--port` 覆盖），避免 origin 变化导致 localStorage 丢失。
4. mock_openchat 同时将会话状态写入 Cookie（按 host 生效，不区分端口），因此切换端口时也可恢复已登录状态。
5. 在同一 profile 下再次打开时，可直接恢复到已登录对话状态，无需重复登录。
6. 如需使用不同 profile，可传参：`python -m scripts.manual_mock_openchat_e2e --user-data-dir tmp/another_profile`。
7. 如需强制从全新会话开始（清空 profile，重新走登录流程）：`python -m scripts.manual_mock_openchat_e2e --force-fresh`。

manual_openai_e2e 验收链路（补齐端到端缺失环节）：

1. 先打 mock 站点（默认）：`python -m scripts.manual_openai_e2e --target mock_site`
2. 脚本会自动启动本地 mock 站点、发送请求、采集并校验返回 JSON。
3. mock 链路通过后，再切真实站点：`python -m scripts.manual_openai_e2e --target real_site`
4. 真实站点模式下，脚本会打开 `https://chatgpt.com/`（可用 `--chat-url` 覆盖），你先手工完成登录/验证后继续。
5. 可通过 `--user-data-dir` 复用会话，`--force-fresh` 强制重新登录。
6. 若 Cloudflare 验证窗口反复弹出，可提高人工重试次数：`--max-manual-retries 10`。

DeepSeek 直连页面验收基线（已验证通过）：

1. 推荐命令：

	`python -m scripts.manual_openai_e2e --target real_site --chat-url https://chat.deepseek.com/ --user-data-dir tmp/manual_deepseek_profile --max-manual-retries 10`

2. 预期关键日志（示例）：

	`[INFO] OpenAI 页面已就绪，直接进入发送阶段。`

	`[INFO] 已发送消息，等待 assistant 返回...`

	`[INFO] 捕获到回复，selector=div.ds-markdown, text_len=...`

	`[INFO] 已采集并解析返回 JSON：{...}`

	`[PASS] E2E 发送与返回校验通过。`

3. 预期 JSON 口径：

	- `case_status`: `Closed|On-Going`
	- `hearing`: `true|false`

兼容说明：旧参数 `--target openai` / `--target mock_openai` 仍可用。

Cloudflare 反复验证建议：

1. 保持同一 `--user-data-dir` 复用会话，不要频繁切换 profile。
2. 尽量固定网络环境（避免频繁切换代理/IP）。
3. 使用 `python -m scripts.manual_openai_e2e --target real_site --max-manual-retries 10`，按提示多轮完成验证直至聊天输入框稳定可用。

与现有自动化兼容点：

1. 输入框：`textarea[data-testid='chat-input']`
2. 发送按钮：`button[data-testid='send-button']`
3. 回复消息：`[data-testid='assistant-message']`

建议接入顺序：

1. 在 `/api/sessions` 将 openchat 会话 `chat_url` 先设置为 `http://127.0.0.1:8010/`。
2. 跑单元/集成测试与 worker 本地验证，确认流程稳定。
3. 再将 `chat_url` 切回正式站点进行冒烟验证。

## 常见排查

1. API 无法访问：先检查 http://127.0.0.1:8000/healthz 是否返回 status=ok。
2. 数据库文件不存在：确认 DB_URL 使用 sqlite:///data/app.db，并先执行 python -m scripts.init_db。
3. Worker 无任务处理：确认 API 已创建任务，且 worker 进程正在运行。
4. 页面打不开：确认 API 服务在 8000 端口启动，访问 /admin/sessions 或 /admin/test-extract。
5. 任务创建立即失败并返回 503：通常是浏览器内核缺失。请执行 playwright install chromium。
6. 浏览器反复出现 Verify you are human：系统会将会话置为 WAIT_LOGIN 并暂停调度。请在弹出的浏览器中完成 Cloudflare 验证/登录，然后到 /admin/sessions 点击 Mark Login OK。
7. Provider Settings 图标显示为方块或空白：在 WSL 中安装 emoji 字体（`fonts-noto-color-emoji`、`fonts-noto-core`、`fonts-symbola`）并执行 `fc-cache -f -v`，然后重启 WSL 会话与浏览器。

## 文档

1. 技术设计: [docs/technical-design.md](docs/technical-design.md)
2. 实施计划: [docs/implementation-plan.md](docs/implementation-plan.md)

