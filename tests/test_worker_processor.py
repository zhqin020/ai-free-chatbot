from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.browser.scheduler import DispatchDecision
from src.browser.session_registry import SessionRegistry
from src.browser.worker import OpenChatTaskProcessor, ProcessResult, SchedulerWorker, TaskProcessor
from src.config import reset_settings_cache
from src.models.session import Provider, SessionConfig
from src.models.task import TaskCreate, TaskStatus
from src.storage.database import init_db
from src.storage.repositories import TaskRepository


class AlwaysFailProcessor(TaskProcessor):
    async def process(self, decision: DispatchDecision) -> ProcessResult:
        _ = decision
        return ProcessResult(ok=False, error_message="fatal", permanent_failure=True)


class ClosableNoopProcessor(TaskProcessor):
    def __init__(self) -> None:
        self.closed = False

    async def process(self, decision: DispatchDecision) -> ProcessResult:
        _ = decision
        return ProcessResult(ok=True)

    async def close(self) -> None:
        self.closed = True


def _setup_db(path: str) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    os.environ["DB_URL"] = f"sqlite:///{path}"
    reset_settings_cache()
    init_db()


@pytest.mark.asyncio
async def test_openchat_processor_rejects_unsupported_provider() -> None:
    processor = OpenChatTaskProcessor()
    result = await processor.process(
        DispatchDecision(
            task_id="t1",
            session_id="s1",
            provider=Provider.GEMINI,
            attempt_id=1,
            attempt_no=1,
            dispatched_at=datetime.now(UTC),
        )
    )
    assert result.ok is False
    assert result.permanent_failure is True


@pytest.mark.asyncio
async def test_worker_marks_failed_on_permanent_failure() -> None:
    _setup_db("tmp/test_worker_permanent_fail.db")

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
    task = task_repo.create(
        TaskCreate(
            prompt="prompt",
            document_text="doc",
            provider_hint=Provider.OPENCHAT,
        )
    )

    worker = SchedulerWorker(processor=AlwaysFailProcessor(), idle_sleep_seconds=0.01)
    consumed = await worker.run_once()
    assert consumed is True

    updated = task_repo.get(task.id)
    assert updated is not None
    assert updated.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_worker_run_forever_closes_processor() -> None:
    processor = ClosableNoopProcessor()
    worker = SchedulerWorker(processor=processor, idle_sleep_seconds=0.0)
    await worker.run_forever(stop_after=1)
    assert processor.closed is True
