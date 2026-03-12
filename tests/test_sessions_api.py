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
    db_path = Path("tmp/test_sessions_api.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_sessions_api.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_sessions_crud(client: TestClient) -> None:
    create_resp = client.post(
        "/api/sessions",
        json={
            "id": "s-openchat-1",
            "provider": "openchat",
            "chat_url": "https://example.com/openchat",
            "enabled": True,
            "priority": 10,
        },
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["id"] == "s-openchat-1"

    list_resp = client.get("/api/sessions")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = client.get("/api/sessions/s-openchat-1")
    assert get_resp.status_code == 200
    assert get_resp.json()["provider"] == "openchat"

    update_resp = client.put(
        "/api/sessions/s-openchat-1",
        json={
            "provider": "openchat",
            "chat_url": "https://example.com/openchat/v2",
            "enabled": False,
            "priority": 99,
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["enabled"] is False
    assert update_resp.json()["chat_url"].endswith("/v2")

    delete_resp = client.delete("/api/sessions/s-openchat-1")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    missing_resp = client.get("/api/sessions/s-openchat-1")
    assert missing_resp.status_code == 404


def test_session_actions(client: TestClient) -> None:
    client.post(
        "/api/sessions",
        json={
            "id": "s-gemini-1",
            "provider": "gemini",
            "chat_url": "https://example.com/gemini",
            "enabled": True,
            "priority": 20,
        },
    )

    open_resp = client.post("/api/sessions/s-gemini-1/open")
    assert open_resp.status_code == 200
    assert open_resp.json()["chat_url"] == "https://example.com/gemini"

    mark_resp = client.post("/api/sessions/s-gemini-1/mark-login-ok")
    assert mark_resp.status_code == 200
    assert mark_resp.json()["state"] == "READY"
    assert mark_resp.json()["login_state"] == "logged_in"
