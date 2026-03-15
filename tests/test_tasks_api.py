from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from src.config import reset_settings_cache

from src.models.task import TaskStatus
from src.storage.repositories import TaskRepository
from src.storage.database import init_db


@pytest.fixture
def client() -> Iterator[TestClient]:
    db_path = Path("tmp/test_tasks_api.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_tasks_api.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_create_task(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={
            "external_id": "ext-1",
            "prompt": "请提取要点",
            "document_text": "这是文书正文",
            "provider_hint": "openchat",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["status"] == "PENDING"
    assert body["provider_hint"] == "openchat"
    assert body["latest_trace_id"] is None


def test_get_task_by_id(client: TestClient) -> None:
    create_response = client.post(
        "/api/tasks",
        json={
            "prompt": "提取",
            "document_text": "正文",
            "provider_hint": "openchat",
        },
    )
    task_id = create_response.json()["id"]

    get_response = client.get(f"/api/tasks/{task_id}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["id"] == task_id
    assert body["latest_trace_id"] is None
    assert body["raw_response"] is None
    assert body["extracted_json"] is None
    assert body["error_message"] is None


def test_get_task_not_found(client: TestClient) -> None:
    response = client.get("/api/tasks/not-exists")
    assert response.status_code == 404


def test_create_task_ignores_runtime_health_check(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={
            "external_id": "ext-runtime-fail",
            "prompt": "请提取要点",
            "document_text": "这是文书正文",
            "provider_hint": "openchat",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"


def test_get_task_result_without_raw_response(client: TestClient) -> None:
    create_response = client.post(
        "/api/tasks",
        json={
            "prompt": "提取",
            "document_text": "正文",
            "provider_hint": "openchat",
        },
    )
    task_id = create_response.json()["id"]

    response = client.get(f"/api/tasks/{task_id}/result")
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task_id
    assert body["status"] == "PENDING"
    assert body["provider"] == "openchat"
    assert body["raw_response"] is None
    assert body["extracted_json"] is None
    assert body["error_message"] is None
    assert body["retry_count"] == 0


def test_get_task_result_with_parsed_raw_response(client: TestClient) -> None:
    create_response = client.post(
        "/api/tasks",
        json={
            "prompt": "提取",
            "document_text": "正文",
            "provider_hint": "openchat",
        },
    )
    task_id = create_response.json()["id"]

    repo = TaskRepository()
    repo.save_raw_response(
        task_id=task_id,
        provider=Provider.OPENCHAT,
        response_text=(
            '{"case_id":"IMM-3-24","case_status":"Closed","judgment_result":"dismiss",'
            '"hearing":"false","timeline":{"filing_date":"2024-01-01"}}'
        ),
    )
    repo.mark_status(task_id, TaskStatus.COMPLETED)

    response = client.get(f"/api/tasks/{task_id}/result")
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task_id
    assert body["status"] == "COMPLETED"
    assert body["provider"] == "openchat"
    assert body["raw_response"] is not None
    assert body["extracted_json"]["case_id"] == "IMM-3-24"
    assert body["extracted_json"]["case_status"] == "Closed"
    assert body["error_message"] is None


def test_get_task_by_id_includes_result_when_completed(client: TestClient) -> None:
    create_response = client.post(
        "/api/tasks",
        json={
            "prompt": "提取",
            "document_text": "正文",
            "provider_hint": "openchat",
        },
    )
    task_id = create_response.json()["id"]

    repo = TaskRepository()
    repo.save_raw_response(
        task_id=task_id,
        provider=Provider.OPENCHAT,
        response_text='{"ok":true,"case_id":"A-1"}',
    )
    repo.mark_status(task_id, TaskStatus.COMPLETED)

    response = client.get(f"/api/tasks/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["raw_response"] is not None
    assert body["extracted_json"]["ok"] is True
    assert body["error_message"] is None
