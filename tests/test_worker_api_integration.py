from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from src.config import reset_settings_cache
from src.storage.database import init_db


@pytest.fixture
def client() -> Iterator[TestClient]:
    db_path = Path("tmp/test_worker_api_integration.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_worker_api_integration.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def _is_pid_alive(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        try:
            parts = stat_path.read_text(encoding="utf-8", errors="ignore").split()
            if len(parts) >= 3 and parts[2] == "Z":
                return False
        except Exception:
            pass

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_worker_lifecycle_real_process(client: TestClient) -> None:
    from src.api.routers import worker as worker_router

    state_file = worker_router._STATE_FILE
    original_state: bytes | None = None
    if state_file.exists():
        original_state = state_file.read_bytes()

    started_pid: int | None = None

    try:
        initial = client.get("/api/worker/status")
        assert initial.status_code == 200
        initial_body = initial.json()
        if initial_body.get("running"):
            pytest.skip("worker already running; skip destructive lifecycle integration test")

        start_resp = client.post("/api/worker/start")
        assert start_resp.status_code == 200
        start_body = start_resp.json()

        assert start_body["action"] == "start"
        assert start_body["status"]["running"] is True
        assert start_body["status"]["managed_by_api"] is True
        assert isinstance(start_body["status"]["pid"], int)
        started_pid = int(start_body["status"]["pid"])
        assert started_pid > 0

        assert state_file.exists()
        state_payload = json.loads(state_file.read_text(encoding="utf-8"))
        assert int(state_payload["pid"]) == started_pid

        status_resp = client.get("/api/worker/status")
        assert status_resp.status_code == 200
        status_body = status_resp.json()
        assert status_body["running"] is True
        assert int(status_body["pid"]) == started_pid
        assert status_body["managed_by_api"] is True

        stop_resp = client.post("/api/worker/stop?force=true")
        assert stop_resp.status_code == 200
        stop_body = stop_resp.json()
        assert stop_body["action"] == "stop"
        assert stop_body["status"]["running"] is False

        time.sleep(0.2)
        assert state_file.exists() is False
        assert _is_pid_alive(started_pid) is False
    finally:
        if started_pid is not None and _is_pid_alive(started_pid):
            try:
                os.kill(started_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        if original_state is not None:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_bytes(original_state)
        elif state_file.exists():
            state_file.unlink()
