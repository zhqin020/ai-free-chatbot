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
    db_path = Path("tmp/test_sessions_ui.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_sessions_ui.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_admin_sessions_page(client: TestClient) -> None:
    response = client.get("/admin/sessions")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Session Management Console" in response.text
    assert "Batch Enable" in response.text
    assert "Recent Error Summary" in response.text


def test_admin_sessions_static_assets(client: TestClient) -> None:
    css_response = client.get("/ui/admin-sessions.css")
    assert css_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]

    js_response = client.get("/ui/admin-sessions.js")
    assert js_response.status_code == 200
    assert "javascript" in js_response.headers["content-type"]
