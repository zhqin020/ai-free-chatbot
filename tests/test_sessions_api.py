from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from src.config import reset_settings_cache
from src.models.task import TaskCreate
from src.storage.database import init_db
from src.models.session import Provider, SessionConfig
from src.storage.repositories import SessionRepository
from src.storage.repositories import TaskRepository


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


@pytest.fixture(autouse=True)
def patch_server_open(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    from src.api.routers import sessions as sessions_router

    runtime_cookies: dict[tuple[str, str], tuple[str, str]] = {}
    runtime_cookies_on_open: dict[tuple[str, str], tuple[str, str]] = {}
    stats = {"open_calls": 0}

    async def _fake_open_page_in_server_browser(*, key: str, url: str, provider: str) -> tuple[bool, str]:
        _ = url
        stats["open_calls"] = int(stats["open_calls"]) + 1
        cookie = runtime_cookies_on_open.get((key, provider))
        if cookie is not None:
            runtime_cookies[(key, provider)] = cookie
            runtime_cookies_on_open.pop((key, provider), None)
        _ = key
        _ = url
        _ = provider
        return True, "opened in server browser"

    async def _fake_ensure_runtime_cookie_in_server_browser(
        *,
        key: str,
        url: str,
        provider: str,
    ) -> tuple[str, str] | None:
        cookie = runtime_cookies.get((key, provider))
        if cookie is not None:
            return cookie
        await _fake_open_page_in_server_browser(key=key, url=url, provider=provider)
        return runtime_cookies.get((key, provider))

    monkeypatch.setattr(sessions_router, "open_page_in_server_browser", _fake_open_page_in_server_browser)
    monkeypatch.setattr(
        sessions_router,
        "ensure_runtime_cookie_in_server_browser",
        _fake_ensure_runtime_cookie_in_server_browser,
    )
    return {
        "cookies": runtime_cookies,
        "cookies_on_open": runtime_cookies_on_open,
        "stats": stats,
    }


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


def test_open_session_auto_marks_ready(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    # Simulate sticky unhealthy state before manual open.
    set_unhealthy_resp = client.post("/api/sessions/s-mock_openai-1/mark-login-ok")
    assert set_unhealthy_resp.status_code == 200

    from src.storage.repositories import SessionRepository
    from src.models.session import SessionState

    repo = SessionRepository()
    ok = repo.update_state("s-mock_openai-1", SessionState.UNHEALTHY, login_state="runtime_error")
    assert ok is True

    open_resp = client.post("/api/sessions/s-mock_openai-1/open")
    assert open_resp.status_code == 200

    session_resp = client.get("/api/sessions/s-mock_openai-1")
    assert session_resp.status_code == 200
    assert session_resp.json()["state"] == "READY"
    assert session_resp.json()["login_state"] == "logged_in"


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


def test_probe_http_session_tracking(client: TestClient, patch_server_open: dict[str, object]) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    missing_resp = client.get("/api/sessions/s-deepseek-1/http-session")
    assert missing_resp.status_code == 200
    assert missing_resp.json()["tracked"] is False
    assert missing_resp.json()["source"] == "browser_context"

    cookies = patch_server_open["cookies"]
    assert isinstance(cookies, dict)
    cookies[("s-deepseek-1", "deepseek")] = ("sessionid", "abc123-session-token")

    tracked_resp = client.get("/api/sessions/s-deepseek-1/http-session")
    assert tracked_resp.status_code == 200
    body = tracked_resp.json()
    assert body["tracked"] is True
    assert body["cookie_name"] == "sessionid"
    assert body["composed_session_id"].startswith("s-deepseek-1#")


def test_open_warns_on_http_session_change_and_rebuild(client: TestClient, patch_server_open: dict[str, object]) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    cookies = patch_server_open["cookies"]
    assert isinstance(cookies, dict)
    cookies[("s-deepseek-1", "deepseek")] = ("sessionid", "v1")
    first_open = client.post("/api/sessions/s-deepseek-1/open")
    assert first_open.status_code == 200
    assert first_open.json()["requires_rebuild_confirmation"] is False

    cookies[("s-deepseek-1", "deepseek")] = ("sessionid", "v2")
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


def test_verify_stale_session_marks_invalid_without_deletion(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    # Insert a stale session record with no tracked current HTTP session.
    repo = SessionRepository()
    repo.upsert(
        SessionConfig(
            id="1111",
            provider=Provider.OPENCHAT,
            chat_url="https://chatgpt.com/",
            enabled=True,
            priority=100,
        )
    )

    verify_resp = client.post("/api/sessions/1111/verify")
    assert verify_resp.status_code == 200
    body = verify_resp.json()
    assert body["valid"] is False
    assert body["deleted"] is False
    assert "unable to verify" in body["reason"]

    existing_resp = client.get("/api/sessions/1111")
    assert existing_resp.status_code == 200


def test_verify_valid_session_keeps_record(client: TestClient, patch_server_open: dict[str, object]) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    cookies = patch_server_open["cookies"]
    assert isinstance(cookies, dict)
    cookies[("s-deepseek-1", "deepseek")] = ("sessionid", "stable-session-token")

    verify_resp = client.post("/api/sessions/s-deepseek-1/verify")
    assert verify_resp.status_code == 200
    body = verify_resp.json()
    assert body["valid"] is True
    assert body["deleted"] is False

    verify_again = client.post("/api/sessions/s-deepseek-1/verify")
    assert verify_again.status_code == 200
    body_again = verify_again.json()
    assert body_again["valid"] is True
    assert body_again["deleted"] is False
    assert body_again["stored_http_session_id"] == body_again["current_http_session_id"]

    existing_resp = client.get("/api/sessions/s-deepseek-1")
    assert existing_resp.status_code == 200


def test_verify_session_deletes_when_http_session_changes(client: TestClient, patch_server_open: dict[str, object]) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    cookies = patch_server_open["cookies"]
    assert isinstance(cookies, dict)
    cookies[("s-deepseek-1", "deepseek")] = ("sessionid", "session-v1")

    first_verify = client.post("/api/sessions/s-deepseek-1/verify")
    assert first_verify.status_code == 200
    assert first_verify.json()["valid"] is True

    cookies[("s-deepseek-1", "deepseek")] = ("sessionid", "session-v2")

    verify_resp = client.post("/api/sessions/s-deepseek-1/verify")
    assert verify_resp.status_code == 200
    body = verify_resp.json()
    assert body["valid"] is False
    assert body["deleted"] is False
    assert "HTTP session changed" in body["reason"]

    existing_resp = client.get("/api/sessions/s-deepseek-1")
    assert existing_resp.status_code == 200


def test_verify_session_change_moves_state_to_wait_login(client: TestClient, patch_server_open: dict[str, object]) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    cookies = patch_server_open["cookies"]
    assert isinstance(cookies, dict)
    cookies[("s-deepseek-1", "deepseek")] = ("sessionid", "state-a")
    init_resp = client.post("/api/sessions/s-deepseek-1/verify")
    assert init_resp.status_code == 200
    assert init_resp.json()["valid"] is True

    cookies[("s-deepseek-1", "deepseek")] = ("sessionid", "state-b")
    changed_resp = client.post("/api/sessions/s-deepseek-1/verify")
    assert changed_resp.status_code == 200
    assert changed_resp.json()["valid"] is False

    row_resp = client.get("/api/sessions/s-deepseek-1")
    assert row_resp.status_code == 200
    row = row_resp.json()
    assert row["state"] == "WAIT_LOGIN"
    assert row["login_state"] == "invalid_session"


def test_verify_with_attempt_history_does_not_delete_session(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    # Create one historical task bound to this provider path.
    task_repo = TaskRepository()
    _ = task_repo.create(
        TaskCreate(
            prompt="提取",
            document_text="正文",
            provider_hint=Provider.OPENCHAT,
        )
    )

    verify_resp = client.post("/api/sessions/s-mock_openai-1/verify")
    assert verify_resp.status_code == 200
    body = verify_resp.json()
    assert body["valid"] is False
    assert body["deleted"] is False
    assert "unable to verify" in body["reason"]

    kept_resp = client.get("/api/sessions/s-mock_openai-1")
    assert kept_resp.status_code == 200


def test_discover_reenables_archived_mapped_sessions(client: TestClient) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    repo = SessionRepository()
    disabled = repo.disable("s-deepseek-1", login_state="invalid_session")
    assert disabled is True

    before = client.get("/api/sessions?enabled_only=true")
    assert before.status_code == 200
    before_ids = {row["id"] for row in before.json()}
    assert "s-deepseek-1" not in before_ids

    rediscover = client.post("/api/sessions/discover")
    assert rediscover.status_code == 200

    after = client.get("/api/sessions?enabled_only=true")
    assert after.status_code == 200
    after_ids = {row["id"] for row in after.json()}
    assert "s-deepseek-1" in after_ids


def test_verify_auto_opens_page_then_reads_runtime_cookie(client: TestClient, patch_server_open: dict[str, object]) -> None:
    discover_resp = client.post("/api/sessions/discover")
    assert discover_resp.status_code == 200

    cookies_on_open = patch_server_open["cookies_on_open"]
    stats = patch_server_open["stats"]
    assert isinstance(cookies_on_open, dict)
    assert isinstance(stats, dict)
    cookies_on_open[("s-deepseek-1", "deepseek")] = ("sessionid", "opened-and-read")

    verify_resp = client.post("/api/sessions/s-deepseek-1/verify")
    assert verify_resp.status_code == 200
    body = verify_resp.json()
    assert body["valid"] is True
    assert body["tracked"] is True
    assert body["cookie_name"] == "sessionid"
    assert int(stats["open_calls"]) >= 1
