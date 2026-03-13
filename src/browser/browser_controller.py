from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


BrowserType = Literal["chromium", "firefox", "webkit"]
logger = logging.getLogger(__name__)


class BrowserController:
    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._persistent_context = False

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser context is not initialized")
        return self._context

    async def start(
        self,
        browser_type: BrowserType = "chromium",
        headless: bool = False,
        storage_state_path: str | None = None,
        user_data_dir: str | None = None,
    ) -> None:
        logger.debug(
            "browser.start begin type=%s headless=%s storage_state_path=%s user_data_dir=%s",
            browser_type,
            headless,
            storage_state_path,
            user_data_dir,
        )
        self._playwright = await async_playwright().start()
        launch_fn = getattr(self._playwright, browser_type)

        effective_headless = headless
        if not headless:
            has_display = bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))
            if not has_display:
                effective_headless = True
                logger.warning(
                    "browser.start forced_headless=true because no DISPLAY/WAYLAND_DISPLAY was found"
                )

        launch_args = {
            "headless": effective_headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }

        storage_state: str | None = None
        if storage_state_path:
            path = Path(storage_state_path)
            if path.exists():
                storage_state = storage_state_path
                logger.debug("browser.start loading storage state from %s", path)
            else:
                logger.debug("browser.start storage state missing: %s", path)

        if user_data_dir:
            profile_dir = Path(user_data_dir)
            profile_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("browser.start using persistent context profile_dir=%s", profile_dir)
            try:
                self._context = await launch_fn.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    **launch_args,
                )
                self._persistent_context = True
                self._browser = None
                logger.debug("browser.start completed persistent=%s", self._persistent_context)
                return
            except Exception as exc:
                error_text = str(exc)
                if (
                    "Opening in existing browser session" in error_text
                    or "Target page, context or browser has been closed" in error_text
                ):
                    logger.warning(
                        "browser.start persistent launch failed due to profile lock; "
                        "fallback to non-persistent context profile_dir=%s error=%s",
                        profile_dir,
                        error_text,
                    )
                else:
                    raise

        self._browser = await launch_fn.launch(**launch_args)
        self._persistent_context = False

        self._context = await self._browser.new_context(storage_state=storage_state)
        logger.debug("browser.start completed persistent=%s", self._persistent_context)

    async def save_storage_state(self, storage_state_path: str) -> None:
        if self._context is None:
            return
        path = Path(storage_state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(path))

    async def open_page(self, url: str, wait_until: str = "domcontentloaded") -> Page:
        logger.debug("browser.open_page url=%s wait_until=%s", url, wait_until)
        page = await self.context.new_page()
        await page.goto(url, wait_until=wait_until)
        logger.debug("browser.open_page completed url=%s", getattr(page, "url", url))
        return page

    async def close(self) -> None:
        logger.debug("browser.close begin persistent=%s", self._persistent_context)
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None and not self._persistent_context:
            await self._browser.close()
            self._browser = None
        self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        logger.debug("browser.close completed")

    async def is_page_healthy(self, page: Page, required_selector: str | None = None) -> bool:
        if page.is_closed():
            logger.warning("browser.health unhealthy reason=page_closed")
            return False
        if required_selector is None:
            logger.debug("browser.health healthy reason=no_required_selector url=%s", page.url)
            return True
        locator = page.locator(required_selector).first
        try:
            await locator.wait_for(state="visible", timeout=1500)
            logger.debug(
                "browser.health healthy selector_visible selector=%s url=%s",
                required_selector,
                page.url,
            )
            return True
        except Exception as exc:
            logger.warning(
                "browser.health unhealthy selector_not_visible selector=%s url=%s error=%s",
                required_selector,
                page.url,
                exc,
            )
            return False
