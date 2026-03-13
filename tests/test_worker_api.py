from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from src.config import reset_settings_cache
from src.storage.database import init_db


@pytest.fixture
def client() -> Iterator[TestClient]:
    db_path = Path("tmp/test_worker_api.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_worker_api.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_worker_status_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routers import worker as worker_router

    monkeypatch.setattr(
        worker_router,
        "_collect_worker_status",
        lambda: worker_router.WorkerStatusResponse(
            running=True,
            pid=12345,
            managed_by_api=True,
            message="worker is running",
        ),
    )

    response = client.get("/api/worker/status")
    assert response.status_code == 200
    body = response.json()
    assert body["running"] is True
    assert body["pid"] == 12345
    assert body["managed_by_api"] is True


def test_worker_start_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routers import worker as worker_router

    monkeypatch.setattr(
        worker_router,
        "_start_managed_worker",
        lambda: worker_router.WorkerStatusResponse(
            running=True,
            pid=333,
            managed_by_api=True,
            message="worker started",
        ),
    )

    response = client.post("/api/worker/start")
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "start"
    assert body["status"]["running"] is True
    assert body["status"]["pid"] == 333


def test_worker_stop_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routers import worker as worker_router

    monkeypatch.setattr(
        worker_router,
        "_stop_active_worker",
        lambda force: worker_router.WorkerStatusResponse(
            running=False,
            pid=None,
            managed_by_api=True,
            message=f"stopped force={force}",
        ),
    )

    response = client.post("/api/worker/stop?force=true")
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "stop"
    assert body["status"]["running"] is False
    assert body["status"]["message"] == "stopped force=True"
