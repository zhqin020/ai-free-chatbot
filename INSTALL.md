# AI-Free-Chatbot 部署与安装指南

## 1. 安装指南（Install Guide）

### 环境要求

- 操作系统：WSL2 (推荐 Ubuntu 20.04/22.04)
- Python 3.10+（建议使用 Miniconda/Anaconda 管理环境）
- 推荐 4GB+ 内存

### 1. 系统依赖 (WSL 专用)

如果您在 WSL (Ubuntu) 下运行，建议安装以下工具以支持管理页面浏览器自动打开及 Emoji 显示：

```bash
# 1. 安装 Chrome (支持 run_stack.py 的 --open-admin-browser 功能)
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb

# 2. 安装 Emoji 字体 (避免界面图标乱码)
sudo apt update
sudo apt install -y fonts-noto-color-emoji fonts-noto-core fonts-symbola
fc-cache -f -v

# 3. 安装 xdg-utils (支持 xdg-open)
sudo apt install -y xdg-utils
```

### 2. 本地化部署步骤

#### 1. 创建环境

```bash
conda env create -f environment.yml
conda activate aifree
```

#### 2. 安装浏览器内核

```bash
# 安装 Playwright 的浏览器内核及系统底层依赖
playwright install --with-deps chromium
```

#### 3. 配置环境

```bash
cp .env.example .env
# 编辑 .env 文件，按需修改 DB_URL (默认 sqlite:///data/app.db)
```

#### 4. 初始化与启动

主服务采用单进程模型，API 启动后会自动在后台线程中运行任务 Worker：

```bash
# 初始化数据库 (仅第一次或版本升级时)
python scripts/init_db.py

# 启动服务
python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

访问管理后台：[http://localhost:8000/admin](http://localhost:8000/admin)

---

## 2. 安装脚本（install.sh）

将以下内容保存为 `install.sh`，在项目根目录下运行 `bash install.sh` 即可自动完成上述步骤（需手动输入 conda init/y/n 等确认）：

```bash
#!/bin/bash
set -e

# 1. 安装 Miniconda（如已安装可跳过）
if ! command -v conda &> /dev/null; then
  echo "Installing Miniconda..."
  wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh
  bash ~/miniconda.sh -b -p $HOME/miniconda
  echo 'export PATH="$HOME/miniconda/bin:$PATH"' >> ~/.bashrc
  source ~/.bashrc
fi

# 2. 克隆项目（如已存在可跳过）
if [ ! -d "$HOME/ai-free-chatbot" ]; then
  echo "Cloning project..."
  git clone <your-repo-url> $HOME/ai-free-chatbot
fi
cd $HOME/ai-free-chatbot

# 3. 创建 conda 环境
echo "Creating conda environment..."
conda create -n aifree python=3.12 -y

# 4. 激活环境并安装依赖
source ~/.bashrc
conda activate aifree
pip install -r requirements.txt

# 5. 初始化目录结构
mkdir -p docs logs issues tests data tmp src/output

# 6. 初始化数据库
python scripts/init_db.py

echo "安装完成！"
echo "请分别运行以下命令启动服务端和 worker："
echo "  conda activate aifree && python -m src.api.main"
```

---

## 3. 容器化部署 (Docker Deployment)

对于希望快速、无污染部署的用户，推荐使用 Docker 和 Docker Compose。

### 准备工作

1.  **安装 Docker**: 请参考 [Docker 官方指南](https://docs.docker.com/get-docker/)。
2.  **配置环境**:
    ```bash
    cp .env.example .env
    # 编辑 .env 文件，设置 API_TOKEN 等参数
    ```

### 启动服务

在项目根目录下运行：

```bash
docker-compose up -d --build
```

该命令会：

- 构建包含 Playwright 及其所有依赖的镜像。
- 同时启动 API 服务 (`ai-free-chatbot-api`) 和 Worker 服务 (`ai-free-chatbot-worker`)。
- 自动挂载 `data/` 和 `logs/` 目录以实现数据持久化。

### 查看日志

```bash
docker-compose logs -f
```

### 停止并移除容器

```bash
docker-compose down
```

---

## 4. 常见问题 (Troubleshooting)

- **数据库锁定 (Database Lock)**: 如果多个进程同时写入 SQLite 可能会导致锁定。Docker 部署中已通过独立容器和服务解耦降低了此类冲突的概率。
- **Playwright 依赖**: 本项目 `Dockerfile` 已内置了 Chromium 及其所需的系统库。

如需适配特定环境或有特殊扩展需求，请补充说明！
