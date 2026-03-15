from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from src.config import reset_settings_cache
from src.models.session import SessionConfig
from src.models.task import TaskCreate, TaskStatus
from src.storage.database import init_db
from src.storage.repositories import (
    AttemptRepository,
    SessionRepository,
    TaskRepository,
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    db_path = Path("tmp/test_metrics_api.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_metrics_api.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def _seed_metrics_data() -> None:
    session_repo = SessionRepository()
    task_repo = TaskRepository()
    attempt_repo = AttemptRepository()

    session_repo.upsert(
        SessionConfig(
            id="s-openchat-1",
            provider="openchat",
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )
    session_repo.upsert(
        SessionConfig(
            id="s-gemini-1",
            provider="gemini",
            chat_url="https://example.com/gemini",
            enabled=True,
            priority=20,
        )
    )

    t1 = task_repo.create(TaskCreate(prompt="p1", document_text="d1", provider_hint="openchat"))
    t2 = task_repo.create(TaskCreate(prompt="p2", document_text="d2", provider_hint="openchat"))
    t3 = task_repo.create(TaskCreate(prompt="p3", document_text="d3", provider_hint="gemini"))

    task_repo.mark_status(t1.id, TaskStatus.COMPLETED)
    task_repo.mark_status(t2.id, TaskStatus.FAILED)
    task_repo.mark_status(t3.id, TaskStatus.PENDING)

    a1 = attempt_repo.start_attempt(t1.id, "s-openchat-1", 1)
    attempt_repo.finish_attempt(a1.id, "SUCCESS", latency_ms=120)

    a2 = attempt_repo.start_attempt(t2.id, "s-openchat-1", 1)
    attempt_repo.finish_attempt(a2.id, "FAILED", latency_ms=300, error_message="response timeout")

    task_repo.save_extracted_result(t1.id, valid_schema=True, case_status="Closed", judgment_result="dismiss")
    task_repo.save_extracted_result(t2.id, valid_schema=False, extraction_error="validate_error")


def test_metrics_summary(client: TestClient) -> None:
    _seed_metrics_data()

    response = client.get("/api/metrics/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_tasks"] == 3
    assert body["completed_tasks"] == 1
    assert body["failed_tasks"] == 1
    assert body["pending_tasks"] == 1
    assert body["timeout_count"] == 1
    assert body["schema_valid_count"] == 1
    assert body["schema_invalid_count"] == 1


def test_metrics_providers(client: TestClient) -> None:
    _seed_metrics_data()

    response = client.get("/api/metrics/providers")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2

    openchat = next(r for r in rows if r["provider"] == "openchat")
    assert openchat["total_tasks"] == 2
    assert openchat["completed_tasks"] == 1
    assert openchat["failed_tasks"] == 1
    assert openchat["timeout_count"] == 1
