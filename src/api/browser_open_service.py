from __future__ import annotations

import logging

from src.browser.providers import DefaultProviderAdapter
from src.browser.session_pool import BrowserSessionPool

logger = logging.getLogger(__name__)

# Use one shared browser pool so repeated open actions reuse browser/profile context.
_open_pool = BrowserSessionPool(headless=False)


def _resolve_adapter(provider: str):
    # 统一返回通用 ProviderAdapter，后续可用配置驱动
    return DefaultProviderAdapter()


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
    # 1. 获取 provider ready_selectors_json
    from src.storage.repositories import ProviderConfigRepository
    import json
    repo = ProviderConfigRepository()
    provider_row = repo.get(provider)
    selectors = None
    if provider_row and provider_row.ready_selectors_json:
        try:
            selectors = json.loads(provider_row.ready_selectors_json)
        except Exception:
            selectors = None

    try:
        page = await _open_pool.get_page(session_id=key, url=url, provider=provider)
    except Exception as exc:
        logger.warning(
            "server browser inspect page state failed key=%s provider=%s url=%s error=%s",
            key,
            provider,
            url,
            exc,
        )
        return None

    # 2. 判断 input_selector 是否可见，自动重试等待页面加载
    import asyncio
    chat_ready = False
    max_attempts = 5
    delay = 1.0  # 秒
    if selectors and selectors.get("input_selector"):
        for attempt in range(max_attempts):
            try:
                locator = page.locator(selectors["input_selector"]).first  # type: ignore[attr-defined]
                if await locator.is_visible():
                    chat_ready = True
                    break
            except Exception:
                pass
            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)

    return {
        "chat_ready": chat_ready,
        "cookie_required": False,
        "verification_required": False,
        "login_required": False,
    }
