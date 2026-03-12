# ai-free-chatbot

多浏览器 AI Chat 自动提问与结构化提取服务。

当前已完成 Day 1 工程骨架：

1. 配置模块（`src/config.py`）
2. 日志模块（`src/logger.py`）
3. 核心数据模型（`src/models/`）
4. SQLite 数据表定义与初始化（`src/storage/database.py`, `scripts/init_db.py`）

## 快速开始

1. 激活环境

```bash
conda activate aifree
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 初始化数据库

```bash
python -m scripts.init_db
```

4. 启动调度 worker（消费 API 创建的任务）

```bash
python -m scripts.run_worker
```

调试模式（只跑固定轮询次数）：

```bash
python -m scripts.run_worker --max-loops 10
```

## 可选环境变量

```bash
export APP_NAME=ai-free-chatbot
export APP_ENV=dev
export LOG_LEVEL=INFO
export DB_URL=sqlite:///data/app.db
export API_TOKEN=your-token
```

## 文档

1. 技术设计: `docs/technical-design.md`
2. 实施计划: `docs/implementation-plan.md`

