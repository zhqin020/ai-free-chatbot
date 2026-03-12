from __future__ import annotations

import argparse

from src.config import get_settings
from src.logging_mp import setup_logging
from src.storage.database import init_db


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
    init_db(echo=args.echo)


if __name__ == "__main__":
    main()
