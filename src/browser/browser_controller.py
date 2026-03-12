from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


BrowserType = Literal["chromium", "firefox", "webkit"]


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
        self._playwright = await async_playwright().start()
        launch_fn = getattr(self._playwright, browser_type)

        launch_args = {
            "headless": headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }

        if user_data_dir:
            profile_dir = Path(user_data_dir)
            profile_dir.mkdir(parents=True, exist_ok=True)
            self._context = await launch_fn.launch_persistent_context(
                user_data_dir=str(profile_dir),
                **launch_args,
            )
            self._persistent_context = True
            self._browser = None
            return

        self._browser = await launch_fn.launch(**launch_args)
        self._persistent_context = False

        storage_state: str | None = None
        if storage_state_path:
            path = Path(storage_state_path)
            if path.exists():
                storage_state = storage_state_path

        self._context = await self._browser.new_context(storage_state=storage_state)

    async def save_storage_state(self, storage_state_path: str) -> None:
        if self._context is None:
            return
        path = Path(storage_state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(path))

    async def open_page(self, url: str, wait_until: str = "domcontentloaded") -> Page:
        page = await self.context.new_page()
        await page.goto(url, wait_until=wait_until)
        return page

    async def close(self) -> None:
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
