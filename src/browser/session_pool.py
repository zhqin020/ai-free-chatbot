from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
from pathlib import Path
from time import monotonic
from typing import Callable

from playwright.async_api import Page

from src.browser.browser_controller import BrowserController
from src.models.session import Provider


logger = logging.getLogger(__name__)


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
        storage_state_dir: str = "tmp/browser_state",
        profile_dir: str = "tmp/browser_profile",
        controller_factory: Callable[[], BrowserController] | None = None,
        rebuild_warn_threshold: int = 3,
        rebuild_warn_window_seconds: float = 90.0,
        now_seconds: Callable[[], float] | None = None,
    ) -> None:
        self.headless = headless
        self.required_selector = required_selector
        self.storage_state_dir = Path(storage_state_dir)
        self.profile_dir = Path(profile_dir)
        self.controller_factory = controller_factory or BrowserController
        self.rebuild_warn_threshold = max(1, rebuild_warn_threshold)
        self.rebuild_warn_window_seconds = max(1.0, rebuild_warn_window_seconds)
        self.now_seconds = now_seconds or monotonic
        self._entries: dict[str, _PoolEntry] = {}
        self._rebuild_events: dict[str, deque[float]] = {}

    @staticmethod
    def _make_key(provider: str, session_id: str) -> str:
        return f"{provider}:{session_id}"

    def _state_file(self, provider: str, session_id: str) -> Path:
        safe = f"{provider}_{session_id}".replace(":", "_")
        return self.storage_state_dir / f"{safe}.json"

    def _profile_dir(self, provider: str, session_id: str) -> Path:
        safe = f"{provider}_{session_id}".replace(":", "_")
        return self.profile_dir / safe

    async def get_page(self, session_id: str, url: str, provider: str = "openchat") -> Page:
        key = self._make_key(provider, session_id)
        logger.debug(
            "pool.get_page key=%s target_url=%s required_selector=%s",
            key,
            url,
            self.required_selector,
        )
        entry = self._entries.get(key)
        if entry is not None:
            healthy = await entry.controller.is_page_healthy(
                entry.page,
                required_selector=self.required_selector,
            )
            if healthy:
                logger.debug("pool.get_page reuse key=%s current_url=%s", key, entry.url)
                if entry.url != url:
                    logger.info("pool.get_page navigate existing page key=%s from=%s to=%s", key, entry.url, url)
                    await entry.page.goto(url, wait_until="domcontentloaded")
                    entry.url = url
                return entry.page
            logger.warning("pool.get_page unhealthy existing entry; will close and recreate key=%s", key)
            await self._close_entry(key)

        self._record_rebuild(key)
        logger.info("pool.get_page creating new browser entry key=%s url=%s", key, url)
        controller = self.controller_factory()
        state_file = self._state_file(provider, session_id)
        user_data_dir = self._profile_dir(provider, session_id)
        logger.debug(
            "pool.get_page new entry state_file=%s user_data_dir=%s",
            state_file,
            user_data_dir,
        )
        await controller.start(
            browser_type="chromium",
            headless=self.headless,
            storage_state_path=str(state_file),
            user_data_dir=str(user_data_dir),
        )
        page = await controller.open_page(url)
        self._entries[key] = _PoolEntry(controller=controller, page=page, url=url)
        logger.info("pool.get_page created key=%s opened_url=%s", key, page.url)
        return page

    def _record_rebuild(self, key: str) -> None:
        now = self.now_seconds()
        events = self._rebuild_events.setdefault(key, deque())
        while events and (now - events[0]) > self.rebuild_warn_window_seconds:
            events.popleft()
        events.append(now)

        count = len(events)
        if count > self.rebuild_warn_threshold:
            logger.warning(
                "pool.rebuild.alert key=%s rebuild_count=%s window_seconds=%s threshold=%s",
                key,
                count,
                self.rebuild_warn_window_seconds,
                self.rebuild_warn_threshold,
            )

    async def reset_session(self, session_id: str, provider: str = "openchat") -> None:
        key = self._make_key(provider, session_id)
        logger.warning("pool.reset_session key=%s", key)
        await self._close_entry(key)

    async def close_all(self) -> None:
        for session_id in list(self._entries.keys()):
            await self._close_entry(session_id)

    async def _close_entry(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        if entry is None:
            logger.debug("pool.close_entry skip missing key=%s", key)
            return
        logger.info("pool.close_entry begin key=%s", key)
        try:
            provider, session_id = key.split(":", 1)
            state_file = self._state_file(provider, session_id)
            await entry.controller.save_storage_state(str(state_file))
            logger.debug("pool.close_entry saved storage state key=%s file=%s", key, state_file)
        except Exception as exc:
            logger.warning("pool.close_entry save state failed key=%s error=%s", key, exc)
        try:
            await entry.controller.close()
        except Exception as exc:
            logger.warning("pool.close_entry controller close failed key=%s error=%s", key, exc)
        logger.info("pool.close_entry completed key=%s", key)


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
