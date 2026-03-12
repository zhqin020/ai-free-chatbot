from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from src.browser.runtime_health import check_provider_runtime
from src.config import get_settings
from src.models.session import Provider, SessionState
from src.storage.database import init_db
from src.storage.repositories import SessionRepository


def _build_api_cmd(host: str, port: int, reload_enabled: bool) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.api.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload_enabled:
        cmd.append("--reload")
    return cmd


def _build_worker_cmd(max_loops: int | None) -> list[str]:
    cmd = [sys.executable, "-m", "scripts.run_worker"]
    if max_loops is not None:
        cmd.extend(["--max-loops", str(max_loops)])
    return cmd


def _terminate(proc: subprocess.Popen[bytes], name: str) -> None:
    if proc.poll() is not None:
        return

    print(f"[stack] stopping {name} (pid={proc.pid})")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        print(f"[stack] force-killing {name} (pid={proc.pid})")
        proc.kill()
        proc.wait(timeout=5)


def _ensure_port_available(host: str, port: int) -> None:
    bind_host = "0.0.0.0" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, port))
        except OSError as exc:
            raise RuntimeError(f"api port {host}:{port} is unavailable: {exc}") from exc


def _check_ready_session(provider: Provider) -> bool:
    session_repo = SessionRepository()
    sessions = session_repo.list(enabled_only=True)
    for row in sessions:
        if row.provider != provider:
            continue
        if row.state == SessionState.READY and row.login_state == "logged_in":
            return True
    return False


def _run_preflight(host: str, port: int, required_provider: Provider | None) -> None:
    settings = get_settings()
    print("[stack-check] preflight start")
    print(
        "[stack-check] env "
        f"APP_ENV={settings.app_env} LOG_LEVEL={settings.log_level} DB_URL={settings.db_url}"
    )

    _ensure_port_available(host, port)
    print(f"[stack-check] api port check passed: {host}:{port}")

    init_db()
    print("[stack-check] database init/check passed")

    runtime_ok, runtime_message = check_provider_runtime(required_provider)
    if not runtime_ok:
        raise RuntimeError(runtime_message or "runtime_unavailable: browser runtime check failed")
    print("[stack-check] browser runtime check passed")

    if required_provider is not None:
        if not _check_ready_session(required_provider):
            raise RuntimeError(
                "no enabled READY+logged_in session found for provider "
                f"{required_provider.value}; configure it in /admin/sessions first"
            )
        print(f"[stack-check] provider session ready: {required_provider.value}")

    print("[stack-check] preflight completed")


def _wait_api_health(host: str, port: int, timeout_seconds: int, poll_interval_seconds: float) -> None:
    connect_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    health_url = f"http://{connect_host}:{port}/healthz"
    deadline = time.monotonic() + timeout_seconds

    print(f"[stack-check] waiting api healthz: {health_url}")
    while time.monotonic() < deadline:
        try:
            with urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    print("[stack-check] api health check passed")
                    return
        except URLError:
            pass
        except Exception:
            pass
        time.sleep(poll_interval_seconds)

    raise RuntimeError(
        f"api health check timeout after {timeout_seconds}s: {health_url}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run API + worker as one coordinated backend stack")
    parser.add_argument("--host", default="0.0.0.0", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    parser.add_argument("--no-reload", action="store_true", help="Disable uvicorn --reload")
    parser.add_argument("--worker-max-loops", type=int, default=None, help="Worker debug max loops")
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip preflight checks (port/db/session)",
    )
    parser.add_argument(
        "--require-provider-ready",
        choices=[p.value for p in Provider],
        default=None,
        help="Require at least one enabled READY+logged_in session for the provider before startup",
    )
    parser.add_argument(
        "--health-timeout-seconds",
        type=int,
        default=30,
        help="Timeout for API /healthz readiness check before starting worker",
    )
    parser.add_argument(
        "--health-poll-interval-seconds",
        type=float,
        default=0.5,
        help="Polling interval for API /healthz readiness check",
    )
    args = parser.parse_args()

    reload_enabled = not args.no_reload
    env = os.environ.copy()
    if "WORKER_HEADLESS" not in env:
        app_env = get_settings().app_env.lower()
        env["WORKER_HEADLESS"] = "0" if app_env == "dev" else "1"
    print(f"[stack-check] WORKER_HEADLESS={env.get('WORKER_HEADLESS')}")

    api_cmd = _build_api_cmd(host=args.host, port=args.port, reload_enabled=reload_enabled)
    worker_cmd = _build_worker_cmd(max_loops=args.worker_max_loops)

    required_provider = Provider(args.require_provider_ready) if args.require_provider_ready else None
    if not args.skip_checks:
        _run_preflight(host=args.host, port=args.port, required_provider=required_provider)
    else:
        print("[stack-check] skipped by --skip-checks")

    print("[stack] starting coordinated backend stack")
    print(f"[stack] api command: {' '.join(api_cmd)}")
    print(f"[stack] worker command: {' '.join(worker_cmd)}")

    api_proc = subprocess.Popen(api_cmd, env=env)
    worker_proc: subprocess.Popen[bytes] | None = None

    try:
        _wait_api_health(
            host=args.host,
            port=args.port,
            timeout_seconds=args.health_timeout_seconds,
            poll_interval_seconds=args.health_poll_interval_seconds,
        )
    except Exception:
        _terminate(api_proc, "api")
        raise

    worker_proc = subprocess.Popen(worker_cmd, env=env)

    stopping = False

    def _handle_signal(signum: int, _frame: object) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print(f"[stack] received signal {signum}, shutting down")
        if worker_proc is not None:
            _terminate(worker_proc, "worker")
        _terminate(api_proc, "api")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    exit_code = 0
    try:
        while True:
            api_code = api_proc.poll()
            worker_code = worker_proc.poll()

            if api_code is not None:
                print(f"[stack] api exited with code {api_code}")
                if worker_proc is not None:
                    _terminate(worker_proc, "worker")
                exit_code = api_code
                break

            if worker_proc is not None and worker_code is not None:
                print(f"[stack] worker exited with code {worker_code}")
                _terminate(api_proc, "api")
                exit_code = worker_code
                break

            time.sleep(0.5)
    finally:
        if worker_proc is not None:
            _terminate(worker_proc, "worker")
        _terminate(api_proc, "api")

    if exit_code != 0:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
