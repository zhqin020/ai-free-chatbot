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
from pydantic import BaseModel

router = APIRouter(prefix="/api/worker", tags=["worker"])

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TMP_DIR = _REPO_ROOT / "tmp"
_LOG_DIR = _REPO_ROOT / "logs"
_STATE_FILE = _TMP_DIR / "worker_manager_state.json"
_WORKER_LOG_FILE = _LOG_DIR / "worker-managed.log"
_STATE_LOCK = threading.Lock()


class WorkerStatusResponse(BaseModel):
    running: bool
    pid: int | None = None
    managed_by_api: bool = False
    started_at: datetime | None = None
    uptime_seconds: int | None = None
    command: str | None = None
    message: str | None = None


class WorkerActionResponse(BaseModel):
    action: str
    status: WorkerStatusResponse


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    # Zombie process should be treated as not running for management decisions.
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        try:
            stat_text = stat_path.read_text(encoding="utf-8", errors="ignore")
            parts = stat_text.split()
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


def _read_state() -> dict[str, object] | None:
    if not _STATE_FILE.exists():
        return None
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_state(*, pid: int, started_at: datetime, command: str) -> None:
    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": pid,
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


def _find_worker_pids() -> list[int]:
    found: list[int] = []
    proc_root = Path("/proc")
    if not proc_root.exists():
        return found

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
        if "scripts.run_worker" in text:
            found.append(pid)

    found.sort()
    return found


def _collect_worker_status() -> WorkerStatusResponse:
    state = _read_state()
    if state is not None:
        pid = int(state.get("pid", 0))
        if _is_pid_alive(pid):
            started_at = _parse_started_at(state.get("started_at"))
            uptime = None
            if started_at is not None:
                uptime = max(0, int((_now_utc() - started_at).total_seconds()))
            return WorkerStatusResponse(
                running=True,
                pid=pid,
                managed_by_api=bool(state.get("managed_by_api", True)),
                started_at=started_at,
                uptime_seconds=uptime,
                command=str(state.get("command", "python -m scripts.run_worker")),
                message="worker is running",
            )
        _clear_state()

    pids = _find_worker_pids()
    if pids:
        return WorkerStatusResponse(
            running=True,
            pid=pids[0],
            managed_by_api=False,
            started_at=None,
            uptime_seconds=None,
            command="python -m scripts.run_worker",
            message="worker is running (not managed by api)",
        )

    return WorkerStatusResponse(running=False, message="worker is not running")


def _start_managed_worker() -> WorkerStatusResponse:
    current = _collect_worker_status()
    if current.running:
        return WorkerStatusResponse(
            **current.model_dump(),
            message="worker already running",
        )

    cmd = [sys.executable, "-m", "scripts.run_worker"]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _WORKER_LOG_FILE.open("ab") as log_fp:
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
        started_at=started_at,
        command=" ".join(cmd),
    )
    time.sleep(0.15)

    return _collect_worker_status()


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


def _stop_active_worker(force: bool) -> WorkerStatusResponse:
    current = _collect_worker_status()
    if not current.running or current.pid is None:
        return WorkerStatusResponse(running=False, message="worker is not running")

    # If worker is managed by API, stop tracked pid only; otherwise stop all discovered worker pids.
    if current.managed_by_api:
        target_pids = [current.pid]
    else:
        target_pids = _find_worker_pids()
        if not target_pids:
            target_pids = [current.pid]

    for pid in target_pids:
        _terminate_pid(pid, force=force)

    if not _is_pid_alive(current.pid):
        _clear_state()
    return _collect_worker_status()


@router.get("/status", response_model=WorkerStatusResponse)
def get_worker_status() -> WorkerStatusResponse:
    with _STATE_LOCK:
        return _collect_worker_status()


@router.post("/start", response_model=WorkerActionResponse)
def start_worker() -> WorkerActionResponse:
    with _STATE_LOCK:
        status = _start_managed_worker()
    return WorkerActionResponse(action="start", status=status)


@router.post("/stop", response_model=WorkerActionResponse)
def stop_worker(
    force: bool = Query(default=True, description="Force SIGKILL when SIGTERM timeout"),
) -> WorkerActionResponse:
    with _STATE_LOCK:
        status = _stop_active_worker(force=force)
    return WorkerActionResponse(action="stop", status=status)
