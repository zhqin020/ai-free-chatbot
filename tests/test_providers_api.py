from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from src.storage.database import Base
import httpx

# 确保所有表结构在 worker 启动前创建
engine = create_engine("sqlite:///tmp/test_providers_api.db")
Base.metadata.create_all(engine)

from src.config import reset_settings_cache
from src.storage.database import init_db


@pytest.fixture
def client() -> Iterator[TestClient]:

    db_path = Path("data/app.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # 不再删除数据库，只保证表结构存在
    os.environ["DB_URL"] = "sqlite:///data/app.db"
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
    # open_page_in_server_browser 已废弃，worker API自动拉起页面，无需 mock

    # 只保留页面拉起与 session-target 相关逻辑
    open_resp = client.post("/api/providers/deepseek/open-browser")
    assert open_resp.status_code == 200
    assert "deepseek" in open_resp.json()["url"]
    assert "opened_in_server" in open_resp.json()

    target_resp = client.get("/api/providers/deepseek/session-target")
    assert target_resp.status_code == 200
    assert target_resp.json()["sessions_url"] == "/admin/sessions?provider=deepseek"




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


# 端到端会话池校验：open-browser后通过 worker API 查询 session pool entries
import time

WORKER_API_URL = "http://localhost:8000"

def test_provider_open_browser_and_session_pool() -> None:
    provider = "deepseek"
    session_id = f"s-{provider}-1"
    url = "https://www.deepseek.com/"
    # 拉起页面
    open_resp = httpx.post(f"{WORKER_API_URL}/api/providers/{provider}/open-browser")
    assert open_resp.status_code == 200
    # 通过 worker API 查询 session pool entries
    found = False
    for _ in range(10):
        entries_resp = httpx.get(f"{WORKER_API_URL}/api/worker/session-pool-entries?provider={provider}")
        assert entries_resp.status_code == 200
        entries = entries_resp.json()
        for entry in entries:
            if entry["key"] == f"{provider}:{session_id}" and entry["url"] == url:
                found = True
                break
        if found:
            break
        time.sleep(0.5)
    assert found, f"session pool entry not found for {provider}:{session_id}"
