from __future__ import annotations

from src.browser.providers.openchat_adapter import OpenChatAdapter


class GrokAdapter(OpenChatAdapter):
    provider_name = "grok"
    input_selectors = (
        "textarea[placeholder*='Ask anything' i]",
        "textarea[data-testid='composer-input']",
        "div[contenteditable='true']",
    )
    send_button_selectors = (
        "button[data-testid='send-button']",
        "button[aria-label*='Send' i]",
    )
    response_selectors = (
        "[data-testid='assistant-response']",
        "div.message-assistant",
        "article[data-role='assistant']",
    )
    login_hint_selectors = (
        "button:has-text('Log in')",
        "a:has-text('Log in')",
    )
    generation_indicator_selectors = (
        "button:has-text('Stop')",
        "button[aria-label*='Stop generating' i]",
        "span:has-text('Thinking')",
    )
    stable_ticks_required = 2
    poll_interval_seconds = 0.5
