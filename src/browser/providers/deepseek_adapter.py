from __future__ import annotations

from src.browser.providers.openchat_adapter import OpenChatAdapter


class DeepSeekAdapter(OpenChatAdapter):
    provider_name = "deepseek"
    input_selectors = (
        "textarea[placeholder*='Send a message' i]",
        "textarea[data-testid='chat-input']",
        "div[contenteditable='true']",
    )
    send_button_selectors = (
        "button[aria-label*='Send' i]",
        "button[data-testid='send-button']",
    )
    response_selectors = (
        "[data-testid='assistant-message']",
        "div.markdown-body",
        "article[data-role='assistant']",
    )
    login_hint_selectors = (
        "button:has-text('Sign in')",
        "a:has-text('Sign in')",
    )
    generation_indicator_selectors = (
        "button:has-text('Stop')",
        "button[aria-label*='Stop generating' i]",
        "span:has-text('Generating')",
    )
    stable_ticks_required = 2
    poll_interval_seconds = 0.5
