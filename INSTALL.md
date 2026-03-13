# AI-Free-Chatbot 部署与安装指南

## 1. 安装指南（Install Guide）

### 环境要求

- 操作系统：WSL2 (推荐 Ubuntu 20.04/22.04)
- Python 3.10+（建议使用 Miniconda/Anaconda 管理环境）
- 推荐 4GB+ 内存

### 步骤

#### 1. 安装 Miniconda（如未安装）

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh
bash ~/miniconda.sh -b -p $HOME/miniconda
echo 'export PATH="$HOME/miniconda/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

#### 2. 克隆项目代码

```bash
git clone <your-repo-url> ~/ai-free-chatbot
cd ~/ai-free-chatbot
```

#### 3. 创建并激活 conda 虚拟环境

```bash
conda create -n aifree python=3.12 -y
conda activate aifree
```

#### 4. 安装依赖

```bash
pip install -r requirements.txt
```

#### 5. 初始化目录结构（可选，推荐）

```bash
mkdir -p docs logs issues tests data tmp src/output
```

#### 6. 初始化数据库（如有需要）

```bash
python scripts/init_db.py
```

#### 7. 启动 API 服务端

```bash
conda activate aifree
python -m src.api.main
```

#### 8. 启动 Worker

另开一个终端，激活环境后运行：

```bash
conda activate aifree
python scripts/run_worker.py
```

#### 9. 运行示例/测试

```bash
conda activate aifree
python examples/example_test_extract_api.py
```

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
echo "  conda activate aifree && python scripts/run_worker.py"
```

---

如需适配特定 WSL 发行版或有特殊依赖，请补充说明！
