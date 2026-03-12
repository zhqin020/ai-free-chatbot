from __future__ import annotations

from src.browser.providers.openchat_adapter import OpenChatAdapter


class GeminiAdapter(OpenChatAdapter):
    provider_name = "gemini"
    input_selectors = (
        "textarea[aria-label*='Enter a prompt' i]",
        "textarea[placeholder*='Enter a prompt' i]",
        "div[contenteditable='true']",
    )
    send_button_selectors = (
        "button[aria-label*='Send message' i]",
        "button:has-text('Send')",
    )
    response_selectors = (
        "message-content",
        "div.response-content",
        "article[data-response-index]",
    )
    login_hint_selectors = (
        "a:has-text('Sign in')",
        "button:has-text('Sign in')",
    )
    generation_indicator_selectors = (
        "button[aria-label*='Stop generating' i]",
        "button:has-text('Stop')",
        "span:has-text('Generating')",
    )
    stable_ticks_required = 2
    poll_interval_seconds = 0.6
    fallback_send_key = "Control+Enter"
