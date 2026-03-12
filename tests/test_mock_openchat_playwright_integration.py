from __future__ import annotations

import json
import os
import re
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
    # Keep browser-driven integration test opt-in.
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
def mock_openchat_server(run_ui_e2e: bool) -> Iterator[str]:
    if not run_ui_e2e:
        pytest.skip("set RUN_UI_E2E=1 to run browser integration flow")

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.mock_openchat.site:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[1],
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


def test_mock_openchat_browser_flow_end_to_end(mock_openchat_server: str) -> None:
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
        page.goto(f"{mock_openchat_server}/", wait_until="domcontentloaded")

        # Step 1: cookie gate should block everything else.
        cookie_btn = page.locator("[data-testid='cookie-accept']")
        cookie_title = page.locator("#cookieOverlay h2")
        verify_overlay = page.locator("#verifyOverlay")
        login_overlay = page.locator("#loginOverlay")
        state_badge = page.locator("#stateBadge")

        assert cookie_title.is_visible()
        assert verify_overlay.is_hidden()
        assert login_overlay.is_hidden()
        assert state_badge.inner_text() == "待处理 Cookie"
        cookie_btn.click()

        # Step 2: human verification gate appears after cookie acceptance.
        verify_btn = page.locator("[data-testid='verify-human']")
        verify_btn.wait_for(state="visible", timeout=5000)
        assert login_overlay.is_hidden()
        assert state_badge.inner_text() == "待做人机验证"
        verify_btn.click()

        # Step 3: login gate appears after verification.
        page.locator("#loginOverlay").wait_for(state="visible", timeout=5000)
        assert state_badge.inner_text() == "待登录"

        page.fill("#username", "tester")
        page.fill("#password", "secret")
        page.click("#signinBtn")

        # Step 4: chat input is enabled and welcome assistant message exists.
        input_box = page.locator("textarea[data-testid='chat-input']")
        send_btn = page.locator("button[data-testid='send-button']")
        login_overlay.wait_for(state="hidden", timeout=5000)
        assert input_box.is_enabled()
        assert send_btn.is_enabled()
        assert state_badge.inner_text() == "已进入对话"

        messages = page.locator("[data-testid='assistant-message']")
        assert messages.count() == 1
        assert "欢迎进入 Mock OpenChat" in messages.first.inner_text()

        # Step 5: type and send real message (keyboard Enter), then parse JSON response.
        previous_count = messages.count()

        input_box.fill("case AB-42 please extract")
        input_box.press("Enter")

        page.wait_for_function(
            "(p) => document.querySelectorAll(p.selector).length > p.count",
            arg={"selector": "[data-testid='assistant-message']", "count": previous_count},
            timeout=5000,
        )
        response_text = messages.nth(previous_count).inner_text()
        payload = json.loads(response_text)

        assert payload["case_id"].startswith("AB-42")
        assert payload["case_status"] in {"结案", "正在进行"}
        assert payload["judgment_result"] in {"leave", "grant", "dismiss"}
        assert payload["hearing"] in {"yes", "no"}

        timeline = payload["timeline"]
        assert "filing_date" in timeline
        assert "Applicant_file_completed" in timeline
        assert "reply_memo" in timeline
        assert "Sent_to_Court" in timeline
        assert "judgment_date" in timeline

        for key in (
            "filing_date",
            "Applicant_file_completed",
            "reply_memo",
            "Sent_to_Court",
            "judgment_date",
        ):
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", timeline[key])

        browser.close()
