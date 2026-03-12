from __future__ import annotations

import asyncio
from typing import Any, Optional

from src.browser.providers.base import ProviderAdapter


class OpenChatAdapter(ProviderAdapter):
    provider_name = "openchat"
    input_selectors = (
        "textarea[data-testid='chat-input']",
        "textarea[placeholder*='message' i]",
        "div[contenteditable='true']",
    )
    send_button_selectors = (
        "button[data-testid='send-button']",
        "button[aria-label*='send' i]",
        "button:has-text('Send')",
    )
    response_selectors = (
        "[data-testid='assistant-message']",
        "div.message.assistant",
        "article[data-role='assistant']",
    )
    login_hint_selectors = (
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
        "a:has-text('Sign in')",
    )
    generation_indicator_selectors: tuple[str, ...] = ()
    poll_interval_seconds: float = 1.0
    stable_ticks_required: int = 1
    fallback_send_key: str = "Enter"

    async def is_logged_in(self, page: Any) -> bool:
        input_selector = await self._pick_visible_selector(page, self.input_selectors)
        if input_selector is None:
            return False

        login_hint = await self._pick_visible_selector(page, self.login_hint_selectors)
        return login_hint is None

    async def send_message(self, page: Any, message: str) -> None:
        input_selector = await self._pick_visible_selector(page, self.input_selectors)
        if input_selector is None:
            raise RuntimeError("OpenChat input selector not found")

        input_locator = page.locator(input_selector).first
        await input_locator.fill(message)

        await self._send_via_button_or_key(page, input_locator)

    async def _send_via_button_or_key(self, page: Any, input_locator: Any) -> None:

        send_selector = await self._pick_visible_selector(page, self.send_button_selectors)
        if send_selector:
            await page.locator(send_selector).first.click()
            return

        await input_locator.press(self.fallback_send_key)

    async def wait_for_response(
        self,
        page: Any,
        previous_response: str | None = None,
        timeout_ms: int = 60000,
    ) -> Optional[str]:
        deadline = asyncio.get_event_loop().time() + timeout_ms / 1000.0
        previous = self.normalize_text(previous_response)
        candidate = ""
        stable_ticks = 0

        while asyncio.get_event_loop().time() < deadline:
            latest = await self._latest_response(page)
            generating = await self._is_generating(page)

            if latest and latest != previous:
                if latest == candidate and not generating:
                    stable_ticks += 1
                else:
                    candidate = latest
                    stable_ticks = 1 if not generating else 0

                if stable_ticks >= self.stable_ticks_required:
                    return latest
            await asyncio.sleep(self.poll_interval_seconds)
        return None

    async def latest_response(self, page: Any) -> str:
        return await self._latest_response(page)

    async def _latest_response(self, page: Any) -> str:
        selector = await self._pick_visible_selector(page, self.response_selectors)
        if selector is None:
            return ""

        locator = page.locator(selector)
        try:
            text_items = await locator.all_inner_texts()
        except Exception:
            return ""

        if not text_items:
            return ""
        return self.normalize_text(text_items[-1])

    async def _is_generating(self, page: Any) -> bool:
        if not self.generation_indicator_selectors:
            return False
        selector = await self._pick_visible_selector(page, self.generation_indicator_selectors)
        return selector is not None
