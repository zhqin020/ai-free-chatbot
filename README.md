# AI Ops: 多浏览器 AI Chat 自动化与结构化提取平台

AI Ops 是一个高效的 AI 自动化服务，旨在通过 Playwright 驱动多个浏览器实例，利用主流 AI 平台（DeepSeek, Gemini, Grok, Chaton 等）实现非 API 模式下的对话自动化与大规模法律文书结构化提取。

## 🚀 核心特性

-   **单进程统一架构**: 基于 FastAPI 的单服务化设计，API 内部集成任务调度与 Worker 线程，一键完成全流程部署。
-   **高能管理后台**: 
    -   **双栏脚本中心**: 专业的提示词/代码对照工作区，支持实时测试与模板保存。
    -   **全屏宽视野**: 彻底取消展示宽度限制，最大限度利用有效屏幕空间，提升分析效率。
-   **鲁棒的会话管理**: 自动维护浏览器 Persistent Profile，支持持久化登录状态，并提供极简的“标记码登录成功”交互。
-   **开发者友好**: 提供完整的 Python 集成示例，支持通过标准 HTTP 接口快速接入现有业务系统。

## 🛠️ 快速开始

### 方式 A：Docker 部署 (推荐)

```bash
cp .env.example .env     # 编辑 .env 设置必要参数
docker-compose up -d --build
```
访问：`http://localhost:8000/admin` 进入管理台。

### 方式 B：本地开发环境 (WSL/Linux)

1.  **准备环境**:
    ```bash
    conda activate aifree
    pip install -r requirements.txt
    playwright install chromium --with-deps
    ```
2.  **启动服务**:
    ```bash
    ./scripts/start.sh
    ```
    *(该脚本会自动重连 Conda 环境、初始化数据库并启动主服务)*

---

## 🔗 第三方集成

如果您需要在自己的程序中调用本服务，请参考 [examples/README.md](examples/README.md)。

本项目提供了：
-   `examples/client_common.py`: 封装好的 ApiClient 工具类。
-   `example_tasks_api.py`: 异步任务创建与轮询流程。
-   `example_test_extract_api.py`: 针对法律文书提取的 Prompt 与 JSON 模板最佳实践。

---

## 🧪 测试与质量保障

```bash
# 运行核心逻辑与集成测试
pytest tests/
```

系统内部采用分层测试策略：
-   **单元测试**: 覆盖控制器、Session 池与状态机逻辑。
-   **集成测试**: 模拟浏览器交互链路。
-   **Mock 支持**: 提供本地 Mock 站点（`scripts/run_mock_openchat.py`）用于闭环测试，无需依赖真实网络。

---

## 📂 项目结构

-   `src/api/`: FastAPI 路由、Lifespan 管理与核心业务。
-   `src/browser/`: Playwright 驱动、Session 池与浏览器自动化逻辑。
-   `src/storage/`: 数据库模型、Session 管理与持久化。
-   `src/static/`: 现代化的 Admin UI 静态资源。
-   `examples/`: 开发者集成示例与指南。

---

## 👨‍💻 维护与支持

更多详细资料请参考 [docs/](docs/) 目录下的技术设计文档。
如有问题，请查阅 [INSTALL.md](INSTALL.md) 中的常见排查。
