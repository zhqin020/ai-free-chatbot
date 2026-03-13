from __future__ import annotations

import os
import json
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


def test_manual_session_crud_is_disabled(client: TestClient) -> None:
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
    assert create_resp.status_code == 403

    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200
    assert len(discover_resp.json()) >= 1

    update_resp = client.put(
        "/api/sessions/s-mock_openai-1",
        json={
            "provider": "openchat",
            "chat_url": "https://example.com/openchat/v2",
            "enabled": False,
            "priority": 99,
        },
    )
    assert update_resp.status_code == 403

    delete_resp = client.delete("/api/sessions/s-mock_openai-1")
    assert delete_resp.status_code == 403


def test_session_actions(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    open_resp = client.post("/api/sessions/s-deepseek-1/open")
    assert open_resp.status_code == 200
    assert "deepseek" in open_resp.json()["chat_url"]

    mark_resp = client.post("/api/sessions/s-deepseek-1/mark-login-ok")
    assert mark_resp.status_code == 200
    assert mark_resp.json()["state"] == "READY"
    assert mark_resp.json()["login_state"] == "logged_in"

    notify_resp = client.post("/api/sessions/s-deepseek-1/notify-ready")
    assert notify_resp.status_code == 200
    assert notify_resp.json()["state"] == "READY"
    assert notify_resp.json()["login_state"] == "logged_in"


def test_session_discovery_and_ready_update(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200
    discovered = discover_resp.json()
    ids = {row["id"] for row in discovered}

    assert "s-mock_openai-1" in ids
    assert "s-deepseek-1" in ids

    deepseek_row = next(row for row in discovered if row["id"] == "s-deepseek-1")
    assert deepseek_row["session_name"].startswith("deepseek-")
    assert deepseek_row["status"] == deepseek_row["state"]
    assert deepseek_row["start_time"] is not None

    deepseek_ready = client.post("/api/sessions/s-deepseek-1/notify-ready")
    assert deepseek_ready.status_code == 200
    assert deepseek_ready.json()["state"] == "READY"
    assert deepseek_ready.json()["login_state"] == "logged_in"


def test_probe_http_session_tracking(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    state_file = Path("tmp/browser_state/deepseek_s-deepseek-1.json")
    if state_file.exists():
        state_file.unlink()

    missing_resp = client.get("/api/sessions/s-deepseek-1/http-session")
    assert missing_resp.status_code == 200
    assert missing_resp.json()["tracked"] is False

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "sessionid",
                        "value": "abc123-session-token",
                        "domain": "chat.deepseek.com",
                        "path": "/",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    tracked_resp = client.get("/api/sessions/s-deepseek-1/http-session")
    assert tracked_resp.status_code == 200
    body = tracked_resp.json()
    assert body["tracked"] is True
    assert body["cookie_name"] == "sessionid"
    assert body["composed_session_id"].startswith("s-deepseek-1#")


def test_open_warns_on_http_session_change_and_rebuild(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    state_file = Path("tmp/browser_state/deepseek_s-deepseek-1.json")
    state_file.parent.mkdir(parents=True, exist_ok=True)

    state_file.write_text(
        json.dumps({"cookies": [{"name": "sessionid", "value": "v1"}]}),
        encoding="utf-8",
    )
    first_open = client.post("/api/sessions/s-deepseek-1/open")
    assert first_open.status_code == 200
    assert first_open.json()["requires_rebuild_confirmation"] is False

    state_file.write_text(
        json.dumps({"cookies": [{"name": "sessionid", "value": "v2"}]}),
        encoding="utf-8",
    )
    second_open = client.post("/api/sessions/s-deepseek-1/open")
    assert second_open.status_code == 200
    assert second_open.json()["requires_rebuild_confirmation"] is True
    assert second_open.json()["warning"] is not None

    rebuild_resp = client.post("/api/sessions/s-deepseek-1/rebuild")
    assert rebuild_resp.status_code == 200
    assert rebuild_resp.json()["old_session_id"] == "s-deepseek-1"
    assert rebuild_resp.json()["rebuilt_session_id"] == "s-deepseek-1"


def test_session_stats_placeholder(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    stats_resp = client.get("/api/sessions/s-deepseek-1/stats")
    assert stats_resp.status_code == 200
    body = stats_resp.json()
    assert body["session_id"] == "s-deepseek-1"
    assert body["implemented"] is False
    assert body["interaction_count"] is None
