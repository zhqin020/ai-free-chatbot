from __future__ import annotations

import pytest

from src.browser.session_pool import BrowserSessionPool


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.closed = False
        self.goto_calls = 0

    def is_closed(self) -> bool:
        return self.closed

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        _ = wait_until
        self.url = url
        self.goto_calls += 1


class FakeController:
    def __init__(self) -> None:
        self.started = 0
        self.closed = 0
        self.healthy = True
        self.page: FakePage | None = None

    async def start(
        self,
        browser_type: str = "chromium",
        headless: bool = True,
        storage_state_path: str | None = None,
        user_data_dir: str | None = None,
    ) -> None:
        _ = browser_type
        _ = headless
        _ = storage_state_path
        _ = user_data_dir
        self.started += 1

    async def open_page(self, url: str):
        self.page = FakePage(url)
        return self.page

    async def is_page_healthy(self, page: FakePage, required_selector: str | None = None) -> bool:
        _ = page
        _ = required_selector
        return self.healthy

    async def close(self) -> None:
        self.closed += 1
        if self.page:
            self.page.closed = True


@pytest.mark.asyncio
async def test_session_pool_reuses_healthy_page() -> None:
    created: list[FakeController] = []

    def factory() -> FakeController:
        c = FakeController()
        created.append(c)
        return c

    pool = BrowserSessionPool(controller_factory=factory)
    p1 = await pool.get_page("s1", "https://a.com")
    p2 = await pool.get_page("s1", "https://a.com")

    assert p1 is p2
    assert len(created) == 1
    await pool.close_all()


@pytest.mark.asyncio
async def test_session_pool_recreates_unhealthy_page() -> None:
    created: list[FakeController] = []

    def factory() -> FakeController:
        c = FakeController()
        created.append(c)
        return c

    pool = BrowserSessionPool(controller_factory=factory)
    first_page = await pool.get_page("s1", "https://a.com")
    created[0].healthy = False

    second_page = await pool.get_page("s1", "https://a.com")
    assert first_page is not second_page
    assert len(created) == 2
    assert created[0].closed == 1
    await pool.close_all()
