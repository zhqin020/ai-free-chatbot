from __future__ import annotations

from typing import Any

import pytest

from src.browser.providers.deepseek_adapter import DeepSeekAdapter
from src.browser.providers.gemini_adapter import GeminiAdapter
from src.browser.providers.grok_adapter import GrokAdapter


class FakeLocator:
    def __init__(self, visible_sequence: list[bool] | None = None, text_sequence: list[list[str]] | None = None) -> None:
        self.visible_sequence = visible_sequence or [False]
        self.text_sequence = text_sequence or [[]]
        self.filled: str | None = None
        self.pressed: str | None = None
        self.clicked = 0

    @property
    def first(self) -> "FakeLocator":
        return self

    async def is_visible(self) -> bool:
        if len(self.visible_sequence) > 1:
            return self.visible_sequence.pop(0)
        return self.visible_sequence[0]

    async def fill(self, message: str) -> None:
        self.filled = message

    async def press(self, key: str) -> None:
        self.pressed = key

    async def click(self) -> None:
        self.clicked += 1

    async def all_inner_texts(self) -> list[str]:
        if len(self.text_sequence) > 1:
            return self.text_sequence.pop(0)
        return self.text_sequence[0]


class FakePage:
    def __init__(self, mapping: dict[str, FakeLocator]) -> None:
        self.mapping = mapping

    def locator(self, selector: str) -> Any:
        return self.mapping.get(selector, FakeLocator([False]))


@pytest.mark.asyncio
async def test_gemini_send_fallback_uses_ctrl_enter() -> None:
    adapter = GeminiAdapter()
    input_locator = FakeLocator([True])
    page = FakePage({
        "textarea[aria-label*='Enter a prompt' i]": input_locator,
    })

    await adapter.send_message(page, "hello")

    assert input_locator.filled == "hello"
    assert input_locator.pressed == "Control+Enter"


@pytest.mark.asyncio
async def test_grok_wait_response_respects_generation_state() -> None:
    adapter = GrokAdapter()
    adapter.poll_interval_seconds = 0.01
    generating = FakeLocator([True, True, False, False, False])
    responses = FakeLocator([True, True, True, True, True], [["old"], ["partial"], ["partial"], ["final"], ["final"]])
    page = FakePage({
        "button:has-text('Stop')": generating,
        "[data-testid='assistant-response']": responses,
    })

    result = await adapter.wait_for_response(page, previous_response="old", timeout_ms=300)
    assert result == "final"


@pytest.mark.asyncio
async def test_deepseek_wait_response_stable_ticks() -> None:
    adapter = DeepSeekAdapter()
    adapter.poll_interval_seconds = 0.01
    generating = FakeLocator([False, False, False])
    responses = FakeLocator([True, True, True], [["draft"], ["draft"], ["final"]])
    page = FakePage({
        "button:has-text('Stop')": generating,
        "[data-testid='assistant-message']": responses,
    })

    result = await adapter.wait_for_response(page, previous_response="old", timeout_ms=300)
    assert result in {"draft", "final"}
