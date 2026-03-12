from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from playwright.async_api import Page

from src.browser.browser_controller import BrowserController
from src.models.session import Provider


@dataclass
class _PoolEntry:
    controller: BrowserController
    page: Page
    url: str


class BrowserSessionPool:
    def __init__(
        self,
        *,
        headless: bool = True,
        required_selector: str | None = None,
        controller_factory: Callable[[], BrowserController] | None = None,
    ) -> None:
        self.headless = headless
        self.required_selector = required_selector
        self.controller_factory = controller_factory or BrowserController
        self._entries: dict[str, _PoolEntry] = {}

    @staticmethod
    def _make_key(provider: str, session_id: str) -> str:
        return f"{provider}:{session_id}"

    async def get_page(self, session_id: str, url: str, provider: str = "openchat") -> Page:
        key = self._make_key(provider, session_id)
        entry = self._entries.get(key)
        if entry is not None:
            healthy = await entry.controller.is_page_healthy(
                entry.page,
                required_selector=self.required_selector,
            )
            if healthy:
                if entry.url != url:
                    await entry.page.goto(url, wait_until="domcontentloaded")
                    entry.url = url
                return entry.page
            await self._close_entry(key)

        controller = self.controller_factory()
        await controller.start(browser_type="chromium", headless=self.headless)
        page = await controller.open_page(url)
        self._entries[key] = _PoolEntry(controller=controller, page=page, url=url)
        return page

    async def reset_session(self, session_id: str, provider: str = "openchat") -> None:
        key = self._make_key(provider, session_id)
        await self._close_entry(key)

    async def close_all(self) -> None:
        for session_id in list(self._entries.keys()):
            await self._close_entry(session_id)

    async def _close_entry(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        if entry is None:
            return
        await entry.controller.close()


class ProviderSessionPoolManager:
    def __init__(
        self,
        *,
        headless: bool = True,
        required_selectors: dict[Provider, str] | None = None,
        controller_factory: Callable[[], BrowserController] | None = None,
    ) -> None:
        self.headless = headless
        self.required_selectors = required_selectors or {}
        self.controller_factory = controller_factory
        self._pools: dict[Provider, BrowserSessionPool] = {}

    def get_pool(self, provider: Provider) -> BrowserSessionPool:
        pool = self._pools.get(provider)
        if pool is not None:
            return pool
        pool = BrowserSessionPool(
            headless=self.headless,
            required_selector=self.required_selectors.get(provider),
            controller_factory=self.controller_factory,
        )
        self._pools[provider] = pool
        return pool

    async def close_all(self) -> None:
        for pool in self._pools.values():
            await pool.close_all()
