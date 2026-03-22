import sys
import os
import sqlite3
import pytest
from src.storage.database import Base, get_settings
from sqlalchemy import create_engine

# 确保 src 目录加入 sys.path，便于测试直接 import src.*
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# pytest fixture：每次测试前自动初始化 tmp 测试数据库表结构
@pytest.fixture(autouse=True, scope="session")
def init_test_db():
    db_path = os.environ.get("DB_URL", "sqlite:///tmp/test_worker_api.db")
    if db_path.startswith("sqlite:///"):
        db_file = db_path[len("sqlite:///") :]
        if os.path.exists(db_file):
            os.remove(db_file)
        conn = sqlite3.connect(db_file)
        # 创建 provider_configs 表
        conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            url TEXT,
            config TEXT
        );
        """)
        # 创建 tasks 表
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            prompt_text TEXT,
            document_text TEXT,
            status TEXT
        );
        """)
        # 创建 sessions 表
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            provider TEXT,
            chat_url TEXT,
            state TEXT
        );
        """)
        conn.commit()
        conn.close()

# pytest fixture：自动创建所有表，彻底解决 worker 线程表缺失问题
@pytest.fixture(autouse=True, scope="session")
def orm_init_test_db():
    db_url = "sqlite:///tmp/test_worker_api.db"
    os.environ["DB_URL"] = db_url
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
