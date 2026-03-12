from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.browser.scheduler import DispatchDecision
from src.browser.worker import PooledProviderTaskProcessor
from src.config import reset_settings_cache
from src.models.session import Provider, SessionConfig, SessionState
from src.models.task import TaskCreate
from src.storage.database import init_db
from src.storage.repositories import SessionRepository, TaskRepository


class FakeLocator:
    def __init__(self, visible: bool) -> None:
        self._visible = visible

    @property
    def first(self) -> "FakeLocator":
        return self

    async def is_visible(self) -> bool:
        return self._visible


class FakePage:
    def __init__(self, *, verify_visible: bool = False) -> None:
        self.verify_visible = verify_visible
        self.brought_to_front = False

    async def bring_to_front(self) -> None:
        self.brought_to_front = True

    def locator(self, selector: str) -> Any:
        if selector == "text=Verify you are human":
            return FakeLocator(self.verify_visible)
        return FakeLocator(False)


class FakeSessionPool:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.get_page_calls: list[tuple[str, str, str]] = []
        self.reset_calls: list[tuple[str, str]] = []

    async def get_page(self, session_id: str, url: str, provider: str = "openchat") -> FakePage:
        self.get_page_calls.append((session_id, url, provider))
        return self.page

    async def reset_session(self, session_id: str, provider: str = "openchat") -> None:
        self.reset_calls.append((session_id, provider))


class FakeAdapter:
    def __init__(
        self,
        *,
        logged_in: bool,
        response: str = "",
        page_state: "FakePageState | None" = None,
    ) -> None:
        self.logged_in = logged_in
        self.response = response
        self.page_state = page_state
        self.last_previous_response: str | None = None
        self.sent_messages: list[str] = []

    async def is_logged_in(self, page: FakePage) -> bool:
        _ = page
        return self.logged_in

    async def latest_response(self, page: FakePage) -> str:
        _ = page
        return "previous"

    async def send_message(self, page: FakePage, message: str) -> None:
        _ = page
        self.sent_messages.append(message)

    async def wait_for_response(
        self,
        page: FakePage,
        previous_response: str | None = None,
        timeout_ms: int = 60000,
    ) -> str:
        _ = page
        _ = timeout_ms
        self.last_previous_response = previous_response
        return self.response

    async def inspect_page_state(self, page: FakePage) -> "FakePageState | None":
        _ = page
        return self.page_state


@dataclass
class FakePageState:
    chat_ready: bool
    cookie_required: bool
    verification_required: bool
    login_required: bool


def _setup_db(path: str) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    os.environ["DB_URL"] = f"sqlite:///{path}"
    reset_settings_cache()
    init_db()


def _prepare_task_and_session(db_name: str) -> tuple[str, str]:
    _setup_db(db_name)

    session = SessionRepository().upsert(
        SessionConfig(
            id="s-openchat-it",
            provider=Provider.OPENCHAT,
            chat_url="https://example.com/openchat",
            enabled=True,
            priority=10,
        )
    )
    task = TaskRepository().create(
        TaskCreate(
            prompt="请提取结构化字段",
            document_text="这里是文书正文",
            provider_hint=Provider.OPENCHAT,
        )
    )
    return session.id, task.id


@pytest.mark.asyncio
async def test_processor_marks_wait_login_when_human_verification_detected() -> None:
    session_id, task_id = _prepare_task_and_session("tmp/test_browser_dialog_wait_login.db")

    page = FakePage(verify_visible=True)
    pool = FakeSessionPool(page)
    adapter = FakeAdapter(logged_in=False)

    processor = PooledProviderTaskProcessor(
        provider=Provider.OPENCHAT,
        adapter=adapter,
        session_pool=pool,
    )

    result = await processor.process(
        DispatchDecision(
            task_id=task_id,
            session_id=session_id,
            provider=Provider.OPENCHAT,
            attempt_id=1,
            attempt_no=1,
            dispatched_at=datetime.now(UTC),
        )
    )

    assert result.ok is False
    assert "human verification required" in (result.error_message or "")
    assert "notify-ready" in (result.error_message or "")
    assert page.brought_to_front is True

    session_row = SessionRepository().get(session_id)
    assert session_row is not None
    assert session_row.state == SessionState.WAIT_LOGIN
    assert session_row.login_state == "need_login"


@pytest.mark.asyncio
async def test_processor_enters_dialog_and_returns_response_when_logged_in() -> None:
    session_id, task_id = _prepare_task_and_session("tmp/test_browser_dialog_logged_in.db")

    page = FakePage(verify_visible=False)
    pool = FakeSessionPool(page)
    adapter = FakeAdapter(logged_in=True, response="{\"ok\": true}")

    processor = PooledProviderTaskProcessor(
        provider=Provider.OPENCHAT,
        adapter=adapter,
        session_pool=pool,
    )

    result = await processor.process(
        DispatchDecision(
            task_id=task_id,
            session_id=session_id,
            provider=Provider.OPENCHAT,
            attempt_id=1,
            attempt_no=1,
            dispatched_at=datetime.now(UTC),
        )
    )

    assert result.ok is True
    assert result.raw_response == "{\"ok\": true}"

    assert pool.get_page_calls == [
        ("s-openchat-it", "https://example.com/openchat", "openchat")
    ]
    assert adapter.last_previous_response == "previous"
    assert len(adapter.sent_messages) == 1
    assert "请提取结构化字段" in adapter.sent_messages[0]
    assert "这里是文书正文" in adapter.sent_messages[0]
    assert pool.reset_calls == []


@pytest.mark.asyncio
async def test_processor_marks_wait_login_when_cookie_consent_required() -> None:
    session_id, task_id = _prepare_task_and_session("tmp/test_browser_dialog_cookie_required.db")

    page = FakePage(verify_visible=False)
    pool = FakeSessionPool(page)
    adapter = FakeAdapter(
        logged_in=False,
        page_state=FakePageState(
            chat_ready=False,
            cookie_required=True,
            verification_required=False,
            login_required=False,
        ),
    )

    processor = PooledProviderTaskProcessor(
        provider=Provider.OPENCHAT,
        adapter=adapter,
        session_pool=pool,
    )

    result = await processor.process(
        DispatchDecision(
            task_id=task_id,
            session_id=session_id,
            provider=Provider.OPENCHAT,
            attempt_id=1,
            attempt_no=1,
            dispatched_at=datetime.now(UTC),
        )
    )

    assert result.ok is False
    assert "cookie consent required" in (result.error_message or "")
    assert "notify-ready" in (result.error_message or "")
    assert page.brought_to_front is True

    session_row = SessionRepository().get(session_id)
    assert session_row is not None
    assert session_row.state == SessionState.WAIT_LOGIN
    assert session_row.login_state == "need_login"


@pytest.mark.asyncio
async def test_processor_uses_page_state_chat_ready_even_if_logged_in_check_false() -> None:
    session_id, task_id = _prepare_task_and_session("tmp/test_browser_dialog_chat_ready_override.db")

    page = FakePage(verify_visible=False)
    pool = FakeSessionPool(page)
    adapter = FakeAdapter(
        logged_in=False,
        response="{\"ok\": true}",
        page_state=FakePageState(
            chat_ready=True,
            cookie_required=False,
            verification_required=False,
            login_required=False,
        ),
    )

    processor = PooledProviderTaskProcessor(
        provider=Provider.OPENCHAT,
        adapter=adapter,
        session_pool=pool,
    )

    result = await processor.process(
        DispatchDecision(
            task_id=task_id,
            session_id=session_id,
            provider=Provider.OPENCHAT,
            attempt_id=1,
            attempt_no=1,
            dispatched_at=datetime.now(UTC),
        )
    )

    assert result.ok is True
    assert result.raw_response == "{\"ok\": true}"
    assert len(adapter.sent_messages) == 1
