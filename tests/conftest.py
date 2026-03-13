import sys
import os

# 确保 src 目录加入 sys.path，便于测试直接 import src.*
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
