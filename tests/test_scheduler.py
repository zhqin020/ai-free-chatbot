from __future__ import annotations

import os

from src.browser.scheduler import WeightedRoundRobinScheduler
from src.browser.session_registry import SessionRegistry
from src.models.session import Provider, SessionConfig, SessionState
from src.models.task import TaskCreate, TaskStatus
from src.storage.database import init_db
from src.storage.repositories import SessionRepository, TaskRepository


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


def test_scheduler_marks_wait_login_on_human_verification_error() -> None:
    _setup_test_db()
    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-verify",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )
    registry.mark_ready("s-openchat-verify")

    task_repo = TaskRepository()
    task = task_repo.create(
        TaskCreate(
            prompt="提取关键字段",
            document_text="示例文书",
            provider_hint=Provider.OPENCHAT,
        )
    )

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30, max_retries=3)
    decision = scheduler.dispatch_next()
    assert decision is not None

    scheduler.mark_attempt_failed(
        task_id=decision.task_id,
        session_id=decision.session_id,
        attempt_id=decision.attempt_id,
        error_message="human verification required (Cloudflare)",
    )

    updated_task = task_repo.get(task.id)
    assert updated_task is not None
    assert updated_task.status == TaskStatus.PENDING

    session_row = SessionRepository().get("s-openchat-verify")
    assert session_row is not None
    assert session_row.state.value == "WAIT_LOGIN"
    assert session_row.login_state == "need_login"


def test_scheduler_does_not_dispatch_wait_login_session() -> None:
    _setup_test_db()
    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-wait",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )

    # Start in WAIT_LOGIN to emulate unresolved Cloudflare/login challenge.
    from src.storage.repositories import SessionRepository

    SessionRepository().update_state("s-openchat-wait", state=SessionState.WAIT_LOGIN, login_state="need_login")

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
    assert decision is None
