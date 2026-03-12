from __future__ import annotations

from typing import Any

import pytest

from src.browser.providers.openchat_adapter import OpenChatAdapter


class FakeLocator:
    def __init__(self, visible: bool = False, text_items: list[str] | None = None) -> None:
        self._visible = visible
        self._text_items = text_items or []
        self.filled: str | None = None
        self.clicked = False
        self.pressed: str | None = None

    @property
    def first(self) -> "FakeLocator":
        return self

    async def is_visible(self) -> bool:
        return self._visible

    async def fill(self, message: str) -> None:
        self.filled = message

    async def click(self) -> None:
        self.clicked = True

    async def press(self, key: str) -> None:
        self.pressed = key

    async def all_inner_texts(self) -> list[str]:
        return self._text_items


class FakePage:
    def __init__(self, mapping: dict[str, FakeLocator]) -> None:
        self.mapping = mapping

    def locator(self, selector: str) -> Any:
        return self.mapping.get(selector, FakeLocator(visible=False))


@pytest.mark.asyncio
async def test_is_logged_in_true_when_input_visible_and_no_signin() -> None:
    adapter = OpenChatAdapter()
    page = FakePage(
        {
            "textarea[data-testid='chat-input']": FakeLocator(visible=True),
        }
    )

    result = await adapter.is_logged_in(page)
    assert result is True


@pytest.mark.asyncio
async def test_send_message_uses_send_button_when_visible() -> None:
    adapter = OpenChatAdapter()
    input_loc = FakeLocator(visible=True)
    send_loc = FakeLocator(visible=True)
    page = FakePage(
        {
            "textarea[data-testid='chat-input']": input_loc,
            "button[data-testid='send-button']": send_loc,
        }
    )

    await adapter.send_message(page, "hello")

    assert input_loc.filled == "hello"
    assert send_loc.clicked is True


@pytest.mark.asyncio
async def test_wait_for_response_returns_latest_non_previous() -> None:
    adapter = OpenChatAdapter()
    response_loc = FakeLocator(visible=True, text_items=["old", "new answer"])
    page = FakePage(
        {
            "[data-testid='assistant-message']": response_loc,
        }
    )

    result = await adapter.wait_for_response(page, previous_response="old", timeout_ms=100)
    assert result == "new answer"
