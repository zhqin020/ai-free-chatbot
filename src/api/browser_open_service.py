from __future__ import annotations

import logging

from src.browser.providers import DeepSeekAdapter, GeminiAdapter, GrokAdapter, OpenChatAdapter
from src.browser.session_pool import BrowserSessionPool

logger = logging.getLogger(__name__)

# Use one shared browser pool so repeated open actions reuse browser/profile context.
_open_pool = BrowserSessionPool(headless=False)


def _resolve_adapter(provider: str):
    if provider == "openchat":
        return OpenChatAdapter()
    if provider == "gemini":
        return GeminiAdapter()
    if provider == "grok":
        return GrokAdapter()
    if provider == "deepseek":
        return DeepSeekAdapter()
    return None


async def open_page_in_server_browser(*, key: str, url: str, provider: str) -> tuple[bool, str]:
    try:
        page = await _open_pool.get_page(session_id=key, url=url, provider=provider)
        try:
            await page.bring_to_front()
        except Exception:
            pass
        return True, f"opened in server browser: {url}"
    except Exception as exc:
        logger.warning(
            "server browser open failed key=%s provider=%s url=%s error=%s",
            key,
            provider,
            url,
            exc,
        )
        return False, f"server browser open failed: {exc}"


async def probe_runtime_cookie_in_server_browser(*, key: str, provider: str) -> tuple[str, str] | None:
    return await _open_pool.probe_runtime_session_cookie(session_id=key, provider=provider)


async def ensure_runtime_cookie_in_server_browser(
    *,
    key: str,
    url: str,
    provider: str,
) -> tuple[str, str] | None:
    cookie = await probe_runtime_cookie_in_server_browser(key=key, provider=provider)
    if cookie is not None:
        return cookie

    try:
        page = await _open_pool.get_page(session_id=key, url=url, provider=provider)
        try:
            await page.bring_to_front()
        except Exception:
            pass
    except Exception as exc:
        logger.warning(
            "server browser ensure runtime cookie failed key=%s provider=%s url=%s error=%s",
            key,
            provider,
            url,
            exc,
        )
        return None

    return await probe_runtime_cookie_in_server_browser(key=key, provider=provider)


async def inspect_runtime_page_state_in_server_browser(
    *,
    key: str,
    url: str,
    provider: str,
) -> dict[str, bool] | None:
    adapter = _resolve_adapter(provider)
    if adapter is None:
        return None

    inspect_fn = getattr(adapter, "inspect_page_state", None)
    if not callable(inspect_fn):
        return None

    try:
        page = await _open_pool.get_page(session_id=key, url=url, provider=provider)
        state = await inspect_fn(page)
    except Exception as exc:
        logger.warning(
            "server browser inspect page state failed key=%s provider=%s url=%s error=%s",
            key,
            provider,
            url,
            exc,
        )
        return None

    return {
        "chat_ready": bool(getattr(state, "chat_ready", False)),
        "cookie_required": bool(getattr(state, "cookie_required", False)),
        "verification_required": bool(getattr(state, "verification_required", False)),
        "login_required": bool(getattr(state, "login_required", False)),
    }
