from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.browser.session_registry import SessionRegistry
from src.browser.worker import ProcessResult, SchedulerWorker, TaskProcessor
from src.config import reset_settings_cache
from src.models.session import SessionConfig
from src.models.task import TaskCreate, TaskStatus
from src.storage.database import init_db
from src.storage.repositories import TaskRepository


class GoodJsonProcessor(TaskProcessor):
    async def process(self, decision):
        _ = decision
        return ProcessResult(
            ok=True,
            raw_response='{"case_id":"IMM-3-24","case_status":"Closed","judgment_result":"dismiss","hearing":"false","timeline":{"filing_date":"2024-01-01","Applicant_file_completed":"2024-04-02","reply_memo":"2024-05-01","Sent_to_Court":"2024-06-14","judgment_date":"2024-10-01"}}',
        )


class BadJsonProcessor(TaskProcessor):
    async def process(self, decision):
        _ = decision
        return ProcessResult(ok=True, raw_response="not json")


def _setup_db(path: str) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    os.environ["DB_URL"] = f"sqlite:///{path}"
    reset_settings_cache()
    init_db()


@pytest.mark.asyncio
async def test_worker_marks_completed_after_extraction_success() -> None:
    _setup_db("tmp/test_worker_extract_ok.db")

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

    repo = TaskRepository()
    task = repo.create(
        TaskCreate(prompt="提取", document_text="正文", provider_hint=Provider.OPENCHAT)
    )

    worker = SchedulerWorker(processor=GoodJsonProcessor(), idle_sleep_seconds=0.0)
    consumed = await worker.run_once()
    assert consumed is True

    updated = repo.get(task.id)
    assert updated is not None
    assert updated.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_worker_fails_on_extraction_failure_without_retry() -> None:
    _setup_db("tmp/test_worker_extract_retry.db")

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

    repo = TaskRepository()
    task = repo.create(
        TaskCreate(prompt="提取", document_text="正文", provider_hint=Provider.OPENCHAT)
    )

    worker = SchedulerWorker(processor=BadJsonProcessor(), idle_sleep_seconds=0.0)
    consumed = await worker.run_once()
    assert consumed is True

    updated = repo.get(task.id)
    assert updated is not None
    assert updated.status == TaskStatus.FAILED
    assert "[FORMAT_RETRY]" not in updated.prompt_text
