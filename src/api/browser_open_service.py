from __future__ import annotations

import logging

from src.browser.session_pool import BrowserSessionPool

logger = logging.getLogger(__name__)

# Use one shared browser pool so repeated open actions reuse browser/profile context.
_open_pool = BrowserSessionPool(headless=False)


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
