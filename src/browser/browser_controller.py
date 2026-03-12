from __future__ import annotations

from typing import Literal, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


BrowserType = Literal["chromium", "firefox", "webkit"]


class BrowserController:
    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

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
    ) -> None:
        self._playwright = await async_playwright().start()
        launch_fn = getattr(self._playwright, browser_type)
        self._browser = await launch_fn.launch(headless=headless)
        self._context = await self._browser.new_context(storage_state=storage_state_path)

    async def open_page(self, url: str, wait_until: str = "domcontentloaded") -> Page:
        page = await self.context.new_page()
        await page.goto(url, wait_until=wait_until)
        return page

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def is_page_healthy(self, page: Page, required_selector: str | None = None) -> bool:
        if page.is_closed():
            return False
        if required_selector is None:
            return True
        locator = page.locator(required_selector).first
        try:
            await locator.wait_for(state="visible", timeout=1500)
            return True
        except Exception:
            return False
