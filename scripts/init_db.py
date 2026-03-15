from __future__ import annotations

import argparse

from src.config import get_settings
from src.logging_mp import setup_logging

from src.storage.database import init_db
from src.models import pool_entry  # 确保 pool_entries 表被注册


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize database schema")
    parser.add_argument("--echo", action="store_true", help="Enable SQLAlchemy echo logs")
    args = parser.parse_args()

    settings = get_settings()
    effective_level = settings.log_level.upper()
    if settings.app_env.lower() == "dev" and effective_level == "INFO":
        effective_level = "DEBUG"
    setup_logging(
        name="init_db",
        cfg_json_str=(
            '{"level":"'
            + effective_level
            + '","output":"file, console","log_file":"init_db"}'
        ),
    )
    print("[INFO] 正在初始化数据库表结构。当前系统仅保留 sessions 主表，已无 session_name、enabled 字段，也无 session_tracking 表。")
    print("[INFO] 如果你是从旧版本升级，需依次运行：\n"
        "  scripts/migrate_sessions_provider_to_string.sql\n"
        "  scripts/migrate_sessions_table.sql\n"
        "  scripts/migrate_sessions_drop_enabled.sql\n"
        "以完成 provider 字段、会话表结构、enabled 字段的全部迁移！")
    init_db(echo=args.echo)


if __name__ == "__main__":
    main()
