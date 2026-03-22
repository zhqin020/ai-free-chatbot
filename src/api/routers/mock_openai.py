from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field



router = APIRouter(prefix="/api/mock-openai", tags=["mock-openai"])

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TMP_DIR = _REPO_ROOT / "tmp"
_LOG_DIR = _REPO_ROOT / "logs"
_STATE_FILE = _TMP_DIR / "mock_openai_manager_state.json"
_LOG_FILE = _LOG_DIR / "mock-openai-managed.log"
_STATE_LOCK = threading.Lock()


class MockOpenAIStartRequest(BaseModel):
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8010, ge=1, le=65535)
    reload: bool = False


class MockOpenAIStatusResponse(BaseModel):
    running: bool
    pid: int | None = None
    managed_by_api: bool = False
    host: str = "127.0.0.1"
    port: int = 8010
    url: str | None = None
    started_at: datetime | None = None
    uptime_seconds: int | None = None
    command: str | None = None
    message: str | None = None


class MockOpenAIActionResponse(BaseModel):
    action: str
    status: MockOpenAIStatusResponse


class MockOpenAIOpenResponse(BaseModel):
    url: str
    opened_in_server: bool = False
    open_message: str | None = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False

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


def _is_tcp_port_open(host: str, port: int) -> bool:
    import socket

    connect_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    try:
        with socket.create_connection((connect_host, port), timeout=0.6):
            return True
    except OSError:
        return False


def _read_state() -> dict[str, object] | None:
    if not _STATE_FILE.exists():
        return None
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_state(*, pid: int, host: str, port: int, reload_enabled: bool, started_at: datetime, command: str) -> None:
    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": pid,
        "host": host,
        "port": port,
        "reload": reload_enabled,
        "started_at": started_at.isoformat(),
        "command": command,
        "managed_by_api": True,
    }
    _STATE_FILE.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _clear_state() -> None:
    if _STATE_FILE.exists():
        _STATE_FILE.unlink()


def _parse_started_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _iter_mock_openai_pids() -> list[int]:
    pids: list[int] = []
    proc_root = Path("/proc")
    if not proc_root.exists():
        return pids

    for pid_dir in proc_root.iterdir():
        if not pid_dir.name.isdigit():
            continue
        pid = int(pid_dir.name)
        cmdline_path = pid_dir / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except Exception:
            continue

        if not raw:
            continue
        text = raw.decode("utf-8", errors="ignore").replace("\x00", " ")
        if "scripts.run_mock_openchat" in text:
            pids.append(pid)

    pids.sort()
    return pids


def _collect_status(host: str, port: int) -> MockOpenAIStatusResponse:
    state = _read_state()
    if state is not None:
        pid = int(state.get("pid", 0))
        state_host = str(state.get("host", host))
        state_port = int(state.get("port", port))
        if _is_pid_alive(pid):
            started_at = _parse_started_at(state.get("started_at"))
            uptime = None
            if started_at is not None:
                uptime = max(0, int((_now_utc() - started_at).total_seconds()))
            return MockOpenAIStatusResponse(
                running=True,
                pid=pid,
                managed_by_api=bool(state.get("managed_by_api", True)),
                host=state_host,
                port=state_port,
                url=f"http://{state_host}:{state_port}/",
                started_at=started_at,
                uptime_seconds=uptime,
                command=str(state.get("command", "python -m scripts.run_mock_openchat")),
                message="mock_openai is running",
            )
        _clear_state()

    if _is_tcp_port_open(host, port):
        pids = _iter_mock_openai_pids()
        return MockOpenAIStatusResponse(
            running=True,
            pid=pids[0] if pids else None,
            managed_by_api=False,
            host=host,
            port=port,
            url=f"http://{host}:{port}/",
            command="python -m scripts.run_mock_openchat",
            message="mock_openai port is active (not managed by api)",
        )

    return MockOpenAIStatusResponse(
        running=False,
        managed_by_api=False,
        host=host,
        port=port,
        url=f"http://{host}:{port}/",
        message="mock_openai is not running",
    )


def _start_mock_openai(*, host: str, port: int, reload_enabled: bool) -> MockOpenAIStatusResponse:
    current = _collect_status(host=host, port=port)
    if current.running:
        return MockOpenAIStatusResponse(
            **current.model_dump(),
            message="mock_openai already running",
        )

    cmd = [
        sys.executable,
        "-m",
        "scripts.run_mock_openchat",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload_enabled:
        cmd.append("--reload")

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _LOG_FILE.open("ab") as log_fp:
        proc = subprocess.Popen(
            cmd,
            cwd=_REPO_ROOT,
            env=env,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    started_at = _now_utc()
    _write_state(
        pid=proc.pid,
        host=host,
        port=port,
        reload_enabled=reload_enabled,
        started_at=started_at,
        command=" ".join(cmd),
    )
    time.sleep(0.2)

    return _collect_status(host=host, port=port)


def _terminate_pid(pid: int, force: bool) -> None:
    if not _is_pid_alive(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if not _is_pid_alive(pid):
            return
        time.sleep(0.2)

    if force and _is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return


def _stop_mock_openai(*, host: str, port: int, force: bool) -> MockOpenAIStatusResponse:
    current = _collect_status(host=host, port=port)
    if not current.running:
        return current

    if current.pid is not None:
        _terminate_pid(current.pid, force=force)
    else:
        pids = _iter_mock_openai_pids()
        for pid in pids:
            _terminate_pid(pid, force=force)

    post = _collect_status(host=host, port=port)
    if not post.running:
        _clear_state()
    return post


@router.get("/status", response_model=MockOpenAIStatusResponse)
def get_mock_openai_status(
    host: str = Query(default="127.0.0.1"),
    port: int = Query(default=8010, ge=1, le=65535),
) -> MockOpenAIStatusResponse:
    with _STATE_LOCK:
        return _collect_status(host=host, port=port)


@router.post("/start", response_model=MockOpenAIActionResponse)
def start_mock_openai(payload: MockOpenAIStartRequest) -> MockOpenAIActionResponse:
    with _STATE_LOCK:
        status = _start_mock_openai(
            host=payload.host,
            port=payload.port,
            reload_enabled=payload.reload,
        )
    return MockOpenAIActionResponse(action="start", status=status)


@router.post("/stop", response_model=MockOpenAIActionResponse)
def stop_mock_openai(
    host: str = Query(default="127.0.0.1"),
    port: int = Query(default=8010, ge=1, le=65535),
    force: bool = Query(default=True, description="Force SIGKILL when SIGTERM timeout"),
) -> MockOpenAIActionResponse:
    with _STATE_LOCK:
        status = _stop_mock_openai(host=host, port=port, force=force)
    return MockOpenAIActionResponse(action="stop", status=status)


@router.post("/open-browser", response_model=MockOpenAIOpenResponse)
async def open_mock_openai_browser(
    host: str = Query(default="127.0.0.1"),
    port: int = Query(default=8010, ge=1, le=65535),
) -> MockOpenAIOpenResponse:
    url = f"http://{host}:{port}/"
    # 浏览器操作已禁用，统一由 worker 进程管理
    return MockOpenAIOpenResponse(
        url=url,
        opened_in_server=False,
        open_message="浏览器操作已禁用，请通过 worker API 进行页面管理。",
    )
