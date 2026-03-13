from __future__ import annotations

import os
from pathlib import Path

from src.browser.scheduler import WeightedRoundRobinScheduler
from src.browser.session_registry import SessionRegistry
from src.models.session import Provider, SessionConfig, SessionState
from src.models.task import TaskCreate, TaskStatus
from src.storage.database import init_db
from src.config import reset_settings_cache
from src.storage.repositories import SessionRepository, TaskDispatchConfigRepository, TaskRepository
from datetime import UTC, datetime, timedelta
from src.storage.database import session_scope, SessionORM


def _setup_test_db() -> None:
    db_path = Path("tmp/test_scheduler.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    os.environ["DB_URL"] = f"sqlite:///{db_path}"
    reset_settings_cache()
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

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)
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

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)
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
    assert updated_task.status == TaskStatus.FAILED

    session_row = SessionRepository().get("s-openchat-verify")
    assert session_row is not None
    assert session_row.state.value == "WAIT_LOGIN"
    assert session_row.login_state == "need_login"


def test_scheduler_marks_wait_login_on_chat_window_not_ready_error() -> None:
    _setup_test_db()
    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-not-ready",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )
    registry.mark_ready("s-openchat-not-ready")

    task_repo = TaskRepository()
    task = task_repo.create(
        TaskCreate(
            prompt="提取关键字段",
            document_text="示例文书",
            provider_hint=Provider.OPENCHAT,
        )
    )

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)
    decision = scheduler.dispatch_next()
    assert decision is not None

    scheduler.mark_attempt_failed(
        task_id=decision.task_id,
        session_id=decision.session_id,
        attempt_id=decision.attempt_id,
        error_message="chat window is not ready; input selector not found",
    )

    updated_task = task_repo.get(task.id)
    assert updated_task is not None
    assert updated_task.status == TaskStatus.FAILED

    session_row = SessionRepository().get("s-openchat-not-ready")
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

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)
    decision = scheduler.dispatch_next()
    assert decision is None


def test_scheduler_marks_unhealthy_on_runtime_display_error() -> None:
    _setup_test_db()
    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-runtime",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )
    registry.mark_ready("s-openchat-runtime")

    task_repo = TaskRepository()
    task = task_repo.create(
        TaskCreate(
            prompt="提取关键字段",
            document_text="示例文书",
            provider_hint=Provider.OPENCHAT,
        )
    )

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)
    decision = scheduler.dispatch_next()
    assert decision is not None

    scheduler.mark_attempt_failed(
        task_id=decision.task_id,
        session_id=decision.session_id,
        attempt_id=decision.attempt_id,
        error_message="Looks like you launched a headed browser without having a XServer running",
    )

    updated_task = task_repo.get(task.id)
    assert updated_task is not None
    assert updated_task.status == TaskStatus.FAILED

    session_row = SessionRepository().get("s-openchat-runtime")
    assert session_row is not None
    assert session_row.state.value == "UNHEALTHY"
    assert session_row.login_state == "runtime_error"


def test_scheduler_marks_unhealthy_on_connection_refused_error() -> None:
    _setup_test_db()
    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-conn-refused",
            provider=Provider.OPENCHAT,
            chat_url="http://127.0.0.1:8010/",
            enabled=True,
            priority=10,
        )
    )
    registry.mark_ready("s-openchat-conn-refused")

    task_repo = TaskRepository()
    task = task_repo.create(
        TaskCreate(
            prompt="提取关键字段",
            document_text="示例文书",
            provider_hint=Provider.OPENCHAT,
        )
    )

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)
    decision = scheduler.dispatch_next()
    assert decision is not None

    scheduler.mark_attempt_failed(
        task_id=decision.task_id,
        session_id=decision.session_id,
        attempt_id=decision.attempt_id,
        error_message="Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:8010/",
    )

    updated_task = task_repo.get(task.id)
    assert updated_task is not None
    assert updated_task.status == TaskStatus.FAILED

    session_row = SessionRepository().get("s-openchat-conn-refused")
    assert session_row is not None
    assert session_row.state.value == "UNHEALTHY"
    assert session_row.login_state == "runtime_error"


def test_scheduler_recovers_stale_busy_session() -> None:
    _setup_test_db()
    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-stale-busy",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )

    # Force session to BUSY and stale enough to be auto-recovered.
    SessionRepository().update_state("s-openchat-stale-busy", state=SessionState.BUSY, login_state="logged_in")
    with session_scope() as session:
        row = session.get(SessionORM, "s-openchat-stale-busy")
        assert row is not None
        row.updated_at = datetime.now(UTC) - timedelta(seconds=300)

    task_repo = TaskRepository()
    task_repo.create(
        TaskCreate(
            prompt="提取关键字段",
            document_text="示例文书",
            provider_hint=Provider.OPENCHAT,
        )
    )

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)
    decision = scheduler.dispatch_next()
    assert decision is not None
    assert decision.session_id == "s-openchat-stale-busy"


def test_scheduler_stops_redispatch_after_failed_attempt() -> None:
    _setup_test_db()
    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-max-fail",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )
    registry.mark_ready("s-openchat-max-fail")

    task_repo = TaskRepository()
    task = task_repo.create(
        TaskCreate(
            prompt="提取关键字段",
            document_text="示例文书",
            provider_hint=Provider.OPENCHAT,
        )
    )

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)

    decision_first = scheduler.dispatch_next()
    assert decision_first is not None
    scheduler.mark_attempt_failed(
        task_id=decision_first.task_id,
        session_id=decision_first.session_id,
        attempt_id=decision_first.attempt_id,
        error_message="temporary response timeout",
    )

    task_after_first = task_repo.get(task.id)
    assert task_after_first is not None
    assert task_after_first.status == TaskStatus.FAILED

    decision_second = scheduler.dispatch_next()
    assert decision_second is None


def test_scheduler_round_robin_mode_ignores_priority() -> None:
    _setup_test_db()
    TaskDispatchConfigRepository().set_mode("round_robin")

    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-a",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat-a",
            enabled=True,
            priority=200,
        )
    )
    registry.register(
        SessionConfig(
            id="s-openchat-b",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat-b",
            enabled=True,
            priority=1,
        )
    )
    registry.mark_ready("s-openchat-a")
    registry.mark_ready("s-openchat-b")

    task_repo = TaskRepository()
    for _ in range(3):
        task_repo.create(
            TaskCreate(
                prompt="提取关键字段",
                document_text="示例文书",
                provider_hint=Provider.OPENCHAT,
            )
        )

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)
    order: list[str] = []
    for _ in range(3):
        decision = scheduler.dispatch_next()
        assert decision is not None
        order.append(decision.session_id)
        scheduler.mark_attempt_failed(
            task_id=decision.task_id,
            session_id=decision.session_id,
            attempt_id=decision.attempt_id,
            error_message="temporary provider error",
        )

    assert order == ["s-openchat-a", "s-openchat-b", "s-openchat-a"]


def test_scheduler_priority_mode_prefers_higher_priority() -> None:
    _setup_test_db()
    TaskDispatchConfigRepository().set_mode("priority")

    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="s-openchat-low-priority",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat-low",
            enabled=True,
            priority=200,
        )
    )
    registry.register(
        SessionConfig(
            id="s-openchat-high-priority",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat-high",
            enabled=True,
            priority=1,
        )
    )
    registry.mark_ready("s-openchat-low-priority")
    registry.mark_ready("s-openchat-high-priority")

    task_repo = TaskRepository()
    task_repo.create(
        TaskCreate(
            prompt="提取关键字段",
            document_text="示例文书",
            provider_hint=Provider.OPENCHAT,
        )
    )

    scheduler = WeightedRoundRobinScheduler(timeout_seconds=30)
    decision = scheduler.dispatch_next()
    assert decision is not None
    assert decision.session_id == "s-openchat-high-priority"
