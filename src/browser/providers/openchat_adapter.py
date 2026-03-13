from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from src.browser.providers.base import ProviderAdapter


@dataclass
class OpenChatPageState:
    chat_ready: bool
    cookie_required: bool
    verification_required: bool
    login_required: bool

    def gate_reason(self) -> str:
        if self.cookie_required:
            return "cookie consent required"
        if self.verification_required:
            return "human verification required"
        if self.login_required:
            return "login required"
        return "chat input unavailable"


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
    cookie_gate_selectors = (
        "[data-testid='cookie-accept']",
        "text=Cookie 设置",
        "button:has-text('Accept all')",
        "button:has-text('Accept')",
    )
    verification_selectors = (
        "text=Verify you are human",
        "iframe[title*='challenge' i]",
        "iframe[src*='challenges.cloudflare.com']",
    )

    async def is_logged_in(self, page: Any) -> bool:
        input_selector = await self._pick_visible_selector(page, self.input_selectors)
        if input_selector is None:
            return False

        login_hint = await self._pick_visible_selector(page, self.login_hint_selectors)
        return login_hint is None

    async def inspect_page_state(self, page: Any) -> OpenChatPageState:
        cookie_required = await self._pick_visible_selector(page, self.cookie_gate_selectors) is not None
        verification_required = await self._pick_visible_selector(page, self.verification_selectors) is not None
        login_required = await self._pick_visible_selector(page, self.login_hint_selectors) is not None
        input_selector = await self._pick_visible_selector(page, self.input_selectors)
        # Some providers render sign-in hints even when the active chat box is already usable.
        # If chat input is visible and no hard gate is present, allow processing.
        chat_ready = bool(input_selector is not None and not verification_required and not cookie_required)

        return OpenChatPageState(
            chat_ready=chat_ready,
            cookie_required=cookie_required,
            verification_required=verification_required,
            login_required=login_required,
        )

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
        baseline_latest, baseline_count = await self._response_snapshot(page)
        if not previous:
            previous = baseline_latest
        candidate = ""
        stable_ticks = 0

        while asyncio.get_event_loop().time() < deadline:
            latest, current_count = await self._response_snapshot(page)
            generating = await self._is_generating(page)

            # Consider either text change or message count growth as a new assistant response.
            # This avoids false timeouts when providers return deterministic identical JSON.
            has_new_response = bool(latest and (latest != previous or current_count > baseline_count))
            if has_new_response:
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
        latest, _ = await self._response_snapshot(page)
        return latest

    async def _response_snapshot(self, page: Any) -> tuple[str, int]:
        selector = await self._pick_visible_selector(page, self.response_selectors)
        if selector is None:
            return "", 0

        locator = page.locator(selector)
        try:
            text_items = await locator.all_inner_texts()
        except Exception:
            return "", 0

        if not text_items:
            return "", 0
        return self.normalize_text(text_items[-1]), len(text_items)

    async def _is_generating(self, page: Any) -> bool:
        if not self.generation_indicator_selectors:
            return False
        selector = await self._pick_visible_selector(page, self.generation_indicator_selectors)
        return selector is not None
