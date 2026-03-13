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
