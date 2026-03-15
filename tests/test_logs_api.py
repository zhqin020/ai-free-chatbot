from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from src.config import reset_settings_cache

from src.storage.database import init_db
from src.storage.repositories import LogRepository


@pytest.fixture
def client() -> Iterator[TestClient]:
    db_path = Path("tmp/test_logs_api.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_logs_api.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def _seed_logs() -> None:
    repo = LogRepository()
    repo.add_log(
        level="INFO",
        provider="openchat",
        task_id="task-1",
        session_id="session-1",
        event="task_dispatched",
        message="attempt=1",
    )
    repo.add_log(
        level="ERROR",
        provider="gemini",
        task_id="task-2",
        session_id="session-2",
        event="task_failed",
        message="response timeout",
    )
    repo.add_log(
        level="WARNING",
        provider="openchat",
        task_id="task-1",
        session_id="session-1",
        event="extract_retry_scheduled",
        message="attempt_no=1",
    )


def test_logs_query_all(client: TestClient) -> None:
    _seed_logs()
    response = client.get("/api/logs")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_logs_filter_by_level_and_provider(client: TestClient) -> None:
    _seed_logs()
    response = client.get("/api/logs", params={"level": "error", "provider": "gemini"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["level"] == "ERROR"
    assert body["items"][0]["provider"] == "gemini"


def test_logs_pagination(client: TestClient) -> None:
    _seed_logs()
    response = client.get("/api/logs", params={"page": 1, "page_size": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_logs_filter_start_at_includes_all_recent(client: TestClient) -> None:
    _seed_logs()
    start_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    response = client.get("/api/logs", params={"start_at": start_at})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3


def test_logs_filter_future_window_returns_empty(client: TestClient) -> None:
    _seed_logs()
    start_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    end_at = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    response = client.get("/api/logs", params={"start_at": start_at, "end_at": end_at})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_logs_filter_by_trace_id(client: TestClient) -> None:
    repo = LogRepository()
    trace_a = "trace-a"
    trace_b = "trace-b"
    repo.add_log(
        trace_id=trace_a,
        level="INFO",
        provider="openchat",
        task_id="task-a",
        session_id="session-a",
        event="task_dispatched",
        message="attempt=1",
    )
    repo.add_log(
        trace_id=trace_a,
        level="INFO",
        provider="openchat",
        task_id="task-a",
        session_id="session-a",
        event="task_completed",
        message="latency_ms=10",
    )
    repo.add_log(
        trace_id=trace_b,
        level="ERROR",
        provider="gemini",
        task_id="task-b",
        session_id="session-b",
        event="task_failed",
        message="timeout",
    )

    response = client.get("/api/logs", params={"trace_id": trace_a})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert {item["trace_id"] for item in body["items"]} == {trace_a}
