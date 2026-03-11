from __future__ import annotations

import argparse

from src.config import get_settings
from src.logger import setup_logging
from src.storage.database import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize database schema")
    parser.add_argument("--echo", action="store_true", help="Enable SQLAlchemy echo logs")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(level=settings.log_level)
    init_db(echo=args.echo)


if __name__ == "__main__":
    main()
