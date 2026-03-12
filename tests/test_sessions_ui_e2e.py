from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import httpx
import pytest


@pytest.fixture
def run_ui_e2e() -> bool:
    # E2E test is opt-in because it requires a browser runtime.
    return os.getenv("RUN_UI_E2E", "0") == "1"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(base_url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=1.5)
            if response.status_code == 200:
                return
            last_error = f"unexpected status={response.status_code}"
        except Exception as exc:  # pragma: no cover - retry loop
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"server health check timeout: {last_error}")


@pytest.fixture
def ui_server(run_ui_e2e: bool) -> Iterator[str]:
    if not run_ui_e2e:
        pytest.skip("set RUN_UI_E2E=1 to run browser E2E flow")

    db_path = Path("tmp/test_sessions_ui_e2e.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["DB_URL"] = "sqlite:///tmp/test_sessions_ui_e2e.db"

    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_health(base_url)
        yield base_url
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - safety cleanup
            server.kill()


def test_sessions_ui_end_to_end_flow(ui_server: str) -> None:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - optional dependency path
        pytest.skip(f"playwright is not available: {exc}")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except PlaywrightTimeoutError as exc:
            pytest.skip(f"playwright browser is not ready: {exc}")
        except Exception as exc:  # pragma: no cover - optional runtime path
            pytest.skip(f"cannot launch browser: {exc}")

        page = browser.new_page()
        page.on("dialog", lambda dialog: dialog.accept())
        page.goto(f"{ui_server}/admin/sessions", wait_until="domcontentloaded")

        def create_session(session_id: str, provider: str, url: str, priority: int) -> None:
            page.fill("#session-id", session_id)
            page.select_option("#provider", provider)
            page.fill("#chat-url", url)
            page.fill("#priority", str(priority))
            page.check("#enabled")
            page.click("#submit-btn")
            page.wait_for_selector(f"button[data-id='{session_id}'][data-action='delete']", timeout=5000)

        create_session("s-e2e-openchat", "openchat", "https://example.com/openchat", 50)
        create_session("s-e2e-gemini", "gemini", "https://example.com/gemini", 70)

        page.select_option("#filter-provider", "openchat")
        page.wait_for_timeout(300)
        rows_count = page.locator("#session-rows tr").count()
        assert rows_count == 1

        page.click("#select-filtered")
        page.click("#batch-disable")
        page.wait_for_timeout(350)

        openchat = httpx.get(f"{ui_server}/api/sessions/s-e2e-openchat", timeout=2.0).json()
        assert openchat["enabled"] is False

        page.click("#clear-filters")
        page.wait_for_timeout(200)

        page.click("button[data-id='s-e2e-openchat'][data-action='delete']")
        page.click("button[data-id='s-e2e-gemini'][data-action='delete']")
        page.wait_for_timeout(300)

        remaining = httpx.get(f"{ui_server}/api/sessions", timeout=2.0).json()
        remaining_ids = {row["id"] for row in remaining}
        assert "s-e2e-openchat" not in remaining_ids
        assert "s-e2e-gemini" not in remaining_ids

        browser.close()
