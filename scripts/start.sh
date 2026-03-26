#!/bin/bash

# AI Ops 一键启动脚本

# 1. 检查并尝试激活虚拟环境 (仅当 conda 可用时)
if command -v conda &> /dev/null; then
    # 尝试寻找 conda.sh 以便在脚本中使用 activate
    CONDA_BASE=$(conda info --base)
    source "$CONDA_BASE/etc/profile.d/conda.sh"
    conda activate aifree
    echo "[INFO] 已尝试激活 conda 环境: aifree"
fi

# 2. 初始化数据库 (如果不存在则创建)
echo "[INFO] 正在检查/初始化数据库..."
python3 scripts/init_db.py

# 3. 启动主服务 (API + 内部 Worker)
echo "[INFO] 正在启动主服务 (http://0.0.0.0:8000)..."
python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
