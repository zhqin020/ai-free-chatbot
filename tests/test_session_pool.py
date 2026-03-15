
from __future__ import annotations
import pytest

from src.browser.session_pool import BrowserSessionPool
import threading
import asyncio
import time

from src.storage.repositories import ProviderConfigRepository
import json
def ensure_test_provider():
    repo = ProviderConfigRepository()
    if not repo.get("test"):
        repo.upsert(
            name="test",
            url="http://127.0.0.1:9999/",  # 测试用URL
            icon="🧪",
        )
        
# 高并发同 session_id/provider get_page 不跨线程复用
@pytest.mark.asyncio
async def test_session_pool_concurrent_get_page_threadsafe():
    ensure_test_provider()
    created = []
    def factory():
        c = FakeController()
        created.append(c)
        return c
    pool = BrowserSessionPool(controller_factory=factory)
    results = []
    def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        page = loop.run_until_complete(pool.get_page("s1", "https://a.com", provider="test"))
        results.append(page)
    threads = [threading.Thread(target=thread_target) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 只会有一个 page/controller 被创建
    assert len(created) == 1
    assert all(p is results[0] for p in results)
    await pool.close_all()

# 异常关闭后自动回收
@pytest.mark.asyncio
async def test_session_pool_auto_recover_on_close_error():
    ensure_test_provider()
    created = []
    ensure_test_provider()
    def factory():
        c = FakeControllerCloseError()
        created.append(c)
        return c
    pool = BrowserSessionPool(controller_factory=factory)
    page1 = await pool.get_page("s2", "https://b.com", provider="test")
    # 关闭时抛异常
    await pool.reset_session("s2", provider="test")
    # 再次获取应能重建
    page2 = await pool.get_page("s2", "https://b.com", provider="test")
    assert page1 is not page2
    assert len(created) == 2
    await pool.close_all()

# 压力测试：并发创建/关闭大量 session
@pytest.mark.asyncio
async def test_session_pool_stress_many_sessions():
    def factory():
        return FakeController()
    pool = BrowserSessionPool(controller_factory=factory)
    session_ids = [f"stress-{i}" for i in range(20)]
    async def create_and_close(sid):
        page = await pool.get_page(sid, f"https://{sid}.com", provider="test")
        await pool.reset_session(sid, provider="test")
    await asyncio.gather(*(create_and_close(sid) for sid in session_ids))
    await pool.close_all()



class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.closed = False
        self.goto_calls = 0

    @property
    def healthy(self) -> bool:
        # 兼容旧用例，默认 healthy，除非外部设置
        return getattr(self, "_healthy", True)

    @healthy.setter
    def healthy(self, value: bool):
        self._healthy = value

    def is_closed(self) -> bool:
        # unhealthy 或 closed 都视为关闭
        return not self.healthy or self.closed

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
        # 每次都 new 一个 FakePage，避免 page 复用
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


class FakeControllerCloseError(FakeController):
    async def close(self) -> None:
        await super().close()
        raise RuntimeError("Target page, context or browser has been closed")


@pytest.mark.asyncio
async def test_session_pool_reuses_healthy_page() -> None:
    created: list[FakeController] = []

    def factory() -> FakeController:
        c = FakeController()
        created.append(c)
        return c

    ensure_test_provider()
    pool = BrowserSessionPool(controller_factory=factory)
    p1 = await pool.get_page("s1", "https://a.com", provider="test")
    p2 = await pool.get_page("s1", "https://a.com", provider="test")

    assert p1 is p2
    assert len(created) == 1
    await pool.close_all()


@pytest.mark.asyncio
async def test_session_pool_recreates_unhealthy_page() -> None:
    import threading
    created: list[FakeController] = []

    def factory() -> FakeController:
        c = FakeController()
        created.append(c)
        return c

    ensure_test_provider()
    pool = BrowserSessionPool(controller_factory=factory)

    # 用同步线程强制保证同一线程下运行
    result = {}
    def sync_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def run():
            first_page = await pool.get_page("s1", "https://a.com", provider="test")
            # 直接设置 entry.page.healthy = False
            entry = pool._entries[pool._make_key("test", "s1")]
            entry.page.healthy = False
            second_page = await pool.get_page("s1", "https://a.com", provider="test")
            result["first_page"] = first_page
            result["second_page"] = second_page
        loop.run_until_complete(run())
        loop.run_until_complete(pool.close_all())

    t = threading.Thread(target=sync_thread)
    t.start()
    t.join()

    first_page = result["first_page"]
    second_page = result["second_page"]
    assert first_page is not second_page
    assert len(created) == 2
    assert created[0].closed == 1


@pytest.mark.asyncio
async def test_session_pool_warns_on_frequent_rebuilds(caplog: pytest.LogCaptureFixture) -> None:
    created: list[FakeController] = []
    ticks = iter([0.0, 1.0, 2.0])

    def factory() -> FakeController:
        c = FakeController()
        created.append(c)
        return c

    ensure_test_provider()
    pool = BrowserSessionPool(
        controller_factory=factory,
        rebuild_warn_threshold=2,
        rebuild_warn_window_seconds=60.0,
        now_seconds=lambda: next(ticks),
    )

    with caplog.at_level("WARNING"):
        key = pool._make_key("test", "s1")
        _ = await pool.get_page("s1", "https://a.com", provider="test")
        entry = pool._entries[key]
        entry.page.healthy = False
        _ = await pool.get_page("s1", "https://a.com", provider="test")
        entry = pool._entries[key]
        entry.page.healthy = False
        _ = await pool.get_page("s1", "https://a.com", provider="test")

    assert any("pool.rebuild.alert" in rec.message for rec in caplog.records)
    await pool.close_all()


@pytest.mark.asyncio
async def test_session_pool_recreate_continues_when_close_raises() -> None:
    created: list[FakeControllerCloseError] = []

    def factory() -> FakeControllerCloseError:
        c = FakeControllerCloseError()
        created.append(c)
        return c

    ensure_test_provider()
    pool = BrowserSessionPool(controller_factory=factory)
    first_page = await pool.get_page("s1", "https://a.com", provider="test")
    # 直接设置 entry.page.healthy = False
    entry = pool._entries[pool._make_key("test", "s1")]
    entry.page.healthy = False

    # Should not raise even if closing old controller fails.
    second_page = await pool.get_page("s1", "https://a.com", provider="test")
    assert first_page is not second_page
    assert len(created) == 2
    await pool.close_all()
