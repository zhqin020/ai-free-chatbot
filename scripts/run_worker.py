from __future__ import annotations

import argparse
import asyncio

from src.browser.worker import SchedulerWorker
from src.config import get_settings
from src.logger import setup_logging
from src.storage.database import init_db


async def _main(max_loops: int | None) -> None:
    worker = SchedulerWorker()
    await worker.run_forever(stop_after=max_loops)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scheduler worker loop")
    parser.add_argument(
        "--max-loops",
        type=int,
        default=None,
        help="Optional max loop count for debug/testing",
    )
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(level=settings.log_level)
    init_db()
    asyncio.run(_main(max_loops=args.max_loops))


if __name__ == "__main__":
    main()
