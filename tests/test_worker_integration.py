from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.browser.session_registry import SessionRegistry
from src.browser.worker import MockTaskProcessor, SchedulerWorker
from src.config import reset_settings_cache
from src.models.session import Provider, SessionConfig
from src.storage.database import init_db
from src.storage.repositories import TaskRepository


@pytest.mark.asyncio
async def test_worker_consumes_task_created_by_api() -> None:
    db_path = Path("tmp/test_worker_integration.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_worker_integration.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/tasks",
            json={
                "prompt": "提取结构化字段",
                "document_text": "案件文书正文",
                "provider_hint": "openchat",
            },
        )
        assert response.status_code == 201
        create_body = response.json()
        task_id = create_body["id"]
        assert create_body["latest_trace_id"] is None

    registry = SessionRegistry()
    registry.register(
        SessionConfig(
            id="session-openchat-1",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )
    registry.mark_ready("session-openchat-1")

    worker = SchedulerWorker(processor=MockTaskProcessor(), idle_sleep_seconds=0.01)
    consumed = await worker.run_once()

    assert consumed is True
    task = TaskRepository().get(task_id)
    assert task is not None
    assert task.status.value == "COMPLETED"

    with TestClient(create_app()) as client:
        get_response = client.get(f"/api/tasks/{task_id}")
        assert get_response.status_code == 200
        get_body = get_response.json()
        assert get_body["latest_trace_id"]
