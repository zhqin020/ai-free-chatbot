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

    db_path = Path("tmp/test_settings_ui_e2e.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["DB_URL"] = "sqlite:///tmp/test_settings_ui_e2e.db"

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


def test_settings_open_browser_opens_local_tab(ui_server: str) -> None:
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
        page.goto(f"{ui_server}/admin/settings", wait_until="domcontentloaded")

        open_btn = "button[data-action='open'][data-name='deepseek']"
        page.wait_for_selector(open_btn, timeout=5000)

        with page.expect_popup(timeout=5000) as popup_info:
            page.click(open_btn)

        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded", timeout=5000)
        assert popup.url.startswith("https://chat.deepseek.com")

        popup.close()
        browser.close()
