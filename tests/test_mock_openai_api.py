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
    db_path = Path("tmp/test_mock_openai_api.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_mock_openai_api.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_mock_openai_status_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routers import mock_openai as router_module

    monkeypatch.setattr(
        router_module,
        "_collect_status",
        lambda host, port: router_module.MockOpenAIStatusResponse(
            running=True,
            pid=5678,
            managed_by_api=True,
            host=host,
            port=port,
            url=f"http://{host}:{port}/",
            message="mock_openai is running",
        ),
    )

    response = client.get("/api/mock-openai/status?host=127.0.0.1&port=8010")
    assert response.status_code == 200
    body = response.json()
    assert body["running"] is True
    assert body["pid"] == 5678
    assert body["host"] == "127.0.0.1"
    assert body["port"] == 8010


def test_mock_openai_start_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routers import mock_openai as router_module

    monkeypatch.setattr(
        router_module,
        "_start_mock_openai",
        lambda host, port, reload_enabled: router_module.MockOpenAIStatusResponse(
            running=True,
            pid=777,
            managed_by_api=True,
            host=host,
            port=port,
            url=f"http://{host}:{port}/",
            message=f"started reload={reload_enabled}",
        ),
    )

    response = client.post(
        "/api/mock-openai/start",
        json={"host": "127.0.0.1", "port": 8011, "reload": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "start"
    assert body["status"]["running"] is True
    assert body["status"]["pid"] == 777
    assert body["status"]["port"] == 8011
    assert body["status"]["message"] == "started reload=True"


def test_mock_openai_stop_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routers import mock_openai as router_module

    monkeypatch.setattr(
        router_module,
        "_stop_mock_openai",
        lambda host, port, force: router_module.MockOpenAIStatusResponse(
            running=False,
            managed_by_api=True,
            host=host,
            port=port,
            url=f"http://{host}:{port}/",
            message=f"stopped force={force}",
        ),
    )

    response = client.post("/api/mock-openai/stop?host=127.0.0.1&port=8010&force=true")
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "stop"
    assert body["status"]["running"] is False
    assert body["status"]["message"] == "stopped force=True"


def test_mock_openai_open_browser_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routers import mock_openai as router_module

    async def _fake_open_page_in_server_browser(*, key: str, url: str, provider: str) -> tuple[bool, str]:
        _ = key
        _ = provider
        return True, f"opened in server browser: {url}"

    monkeypatch.setattr(router_module, "open_page_in_server_browser", _fake_open_page_in_server_browser)

    response = client.post("/api/mock-openai/open-browser?host=127.0.0.1&port=8010")
    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "http://127.0.0.1:8010/"
    assert body["opened_in_server"] is True
