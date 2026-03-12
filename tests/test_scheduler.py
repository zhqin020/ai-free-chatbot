from __future__ import annotations

import os

from src.browser.scheduler import WeightedRoundRobinScheduler
from src.browser.session_registry import SessionRegistry
from src.models.session import Provider, SessionConfig
from src.models.task import TaskCreate
from src.storage.database import init_db
from src.storage.repositories import TaskRepository


def _setup_test_db() -> None:
    os.environ["DB_URL"] = "sqlite:///tmp/test_scheduler.db"
    init_db()


def test_registry_register_and_list() -> None:
    _setup_test_db()
    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-1",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=50,
        )
    )

    sessions = registry.list_all(enabled_only=True)
    assert any(s.id == "s-openchat-1" for s in sessions)


def test_scheduler_dispatch_one_task() -> None:
    _setup_test_db()
    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-1",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )
    registry.mark_ready("s-openchat-1")

    task_repo = TaskRepository()
    task_repo.create(
        TaskCreate(
            prompt="提取关键字段",
            document_text="示例文书",
            provider_hint=Provider.OPENCHAT,
        )
    )

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30, max_retries=3)
    decision = scheduler.dispatch_next()

    assert decision is not None
    assert decision.session_id == "s-openchat-1"
