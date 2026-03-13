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
    db_path = Path("tmp/test_providers_api.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_providers_api.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_builtin_providers_exist(client: TestClient) -> None:
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    rows = resp.json()

    names = {row["name"] for row in rows}
    assert "mock_openai" in names
    assert "deepseek" in names


def test_provider_crud_and_actions(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routers import providers as providers_router

    async def _fake_open_page_in_server_browser(*, key: str, url: str, provider: str) -> tuple[bool, str]:
        _ = key
        _ = provider
        return True, f"opened in server browser: {url}"

    monkeypatch.setattr(providers_router, "open_page_in_server_browser", _fake_open_page_in_server_browser)

    create_resp = client.post(
        "/api/providers",
        json={
            "name": "gemini_custom",
            "url": "https://gemini.google.com/",
            "icon": "✨",
        },
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["name"] == "gemini_custom"

    update_resp = client.put(
        "/api/providers/gemini_custom",
        json={
            "url": "https://example.com/gemini",
            "icon": "🛰️",
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["url"].endswith("/gemini")

    open_resp = client.post("/api/providers/deepseek/open-browser")
    assert open_resp.status_code == 200
    assert "deepseek" in open_resp.json()["url"]
    assert "opened_in_server" in open_resp.json()

    target_resp = client.get("/api/providers/deepseek/session-target")
    assert target_resp.status_code == 200
    assert target_resp.json()["sessions_url"] == "/admin/sessions?provider=deepseek"

    delete_resp = client.delete("/api/providers/gemini_custom")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True


def test_clear_sessions_by_provider_mapping(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    clear_resp = client.post("/api/providers/mock_openai/clear-sessions")
    assert clear_resp.status_code == 200
    assert clear_resp.json()["session_provider"] == "openchat"
    assert clear_resp.json()["cleared_count"] == 1

    list_resp = client.get("/api/sessions")
    assert list_resp.status_code == 200
    ids = {row["id"] for row in list_resp.json()}
    assert "s-mock_openai-1" not in ids
    assert "s-deepseek-1" in ids


def test_dispatch_mode_get_and_update(client: TestClient) -> None:
    get_resp = client.get("/api/providers/dispatch-mode")
    assert get_resp.status_code == 200
    assert get_resp.json()["mode"] in {"round_robin", "priority"}

    update_resp = client.put("/api/providers/dispatch-mode", json={"mode": "priority"})
    assert update_resp.status_code == 200
    assert update_resp.json()["mode"] == "priority"

    get_after = client.get("/api/providers/dispatch-mode")
    assert get_after.status_code == 200
    assert get_after.json()["mode"] == "priority"


def test_builtin_provider_cannot_be_deleted(client: TestClient) -> None:
    resp = client.delete("/api/providers/deepseek")
    assert resp.status_code == 403
    assert "builtin provider cannot be deleted" in resp.json()["detail"]
