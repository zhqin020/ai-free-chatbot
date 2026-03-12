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
    db_path = Path("tmp/test_admin_portal_ui.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_admin_portal_ui.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_admin_hub_page(client: TestClient) -> None:
    response = client.get("/admin")
    assert response.status_code == 200
    assert "统一管理入口" in response.text
    assert "设置" in response.text
    assert "测试" in response.text
    assert "查询" in response.text


def test_admin_settings_and_query_pages(client: TestClient) -> None:
    settings_response = client.get("/admin/settings")
    assert settings_response.status_code == 200
    assert "设置中心" in settings_response.text

    query_response = client.get("/admin/query")
    assert query_response.status_code == 200
    assert "查询中心" in query_response.text


def test_admin_hub_static_assets(client: TestClient) -> None:
    css_response = client.get("/ui/admin-home.css")
    assert css_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]
