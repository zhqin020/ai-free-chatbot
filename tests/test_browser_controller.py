from __future__ import annotations

from pathlib import Path

import pytest

from src.browser.browser_controller import BrowserController


class FakePage:
    def __init__(self) -> None:
        self.last_url: str | None = None

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        _ = wait_until
        self.last_url = url


class FakeContext:
    def __init__(self) -> None:
        self.page = FakePage()
        self.closed = False
        self.storage_state_path: str | None = None

    async def new_page(self) -> FakePage:
        return self.page

    async def storage_state(self, path: str) -> None:
        self.storage_state_path = path

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self._context = context
        self.closed = False
        self.last_storage_state: str | None = None

    async def new_context(self, storage_state: str | None = None) -> FakeContext:
        self.last_storage_state = storage_state
        return self._context

    async def close(self) -> None:
        self.closed = True


class FakeBrowserType:
    def __init__(self) -> None:
        self.context = FakeContext()
        self.browser = FakeBrowser(self.context)
        self.launch_called = False
        self.launch_persistent_called = False
        self.last_launch_kwargs: dict | None = None
        self.last_persistent_kwargs: dict | None = None
        self.persistent_error: Exception | None = None

    async def launch(self, **kwargs):
        self.launch_called = True
        self.last_launch_kwargs = kwargs
        return self.browser

    async def launch_persistent_context(self, **kwargs):
        self.launch_persistent_called = True
        self.last_persistent_kwargs = kwargs
        if self.persistent_error is not None:
            raise self.persistent_error
        return self.context


class FakePlaywrightManager:
    def __init__(self, browser_type: FakeBrowserType) -> None:
        self.chromium = browser_type
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FakeAsyncPlaywright:
    def __init__(self, manager: FakePlaywrightManager) -> None:
        self._manager = manager

    async def start(self) -> FakePlaywrightManager:
        return self._manager


@pytest.mark.asyncio
async def test_start_launches_browser_context_with_existing_storage_state(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")

    browser_type = FakeBrowserType()
    manager = FakePlaywrightManager(browser_type)
    monkeypatch.setattr(
        "src.browser.browser_controller.async_playwright",
        lambda: FakeAsyncPlaywright(manager),
    )

    controller = BrowserController()
    await controller.start(storage_state_path=str(state_path), headless=True)

    assert browser_type.launch_called is True
    assert browser_type.browser.last_storage_state == str(state_path)

    page = await controller.open_page("https://example.com/chat")
    assert page.last_url == "https://example.com/chat"

    await controller.close()
    assert browser_type.context.closed is True
    assert browser_type.browser.closed is True
    assert manager.stopped is True


@pytest.mark.asyncio
async def test_start_uses_persistent_profile_when_user_data_dir_provided(monkeypatch, tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"

    browser_type = FakeBrowserType()
    manager = FakePlaywrightManager(browser_type)
    monkeypatch.setattr(
        "src.browser.browser_controller.async_playwright",
        lambda: FakeAsyncPlaywright(manager),
    )

    controller = BrowserController()
    await controller.start(user_data_dir=str(profile_dir), headless=False)

    assert browser_type.launch_persistent_called is True
    assert browser_type.launch_called is False
    assert browser_type.last_persistent_kwargs is not None
    assert browser_type.last_persistent_kwargs["user_data_dir"] == str(profile_dir)

    await controller.close()
    assert browser_type.context.closed is True
    assert browser_type.browser.closed is False
    assert manager.stopped is True


@pytest.mark.asyncio
async def test_start_falls_back_when_persistent_profile_locked(monkeypatch, tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")

    browser_type = FakeBrowserType()
    browser_type.persistent_error = RuntimeError(
        "BrowserType.launch_persistent_context: Target page, context or browser has been closed\n"
        "[pid=1][out] Opening in existing browser session."
    )
    manager = FakePlaywrightManager(browser_type)
    monkeypatch.setattr(
        "src.browser.browser_controller.async_playwright",
        lambda: FakeAsyncPlaywright(manager),
    )

    controller = BrowserController()
    await controller.start(
        user_data_dir=str(profile_dir),
        storage_state_path=str(state_path),
        headless=False,
    )

    assert browser_type.launch_persistent_called is True
    assert browser_type.launch_called is True
    assert browser_type.browser.last_storage_state == str(state_path)

    await controller.close()
    assert browser_type.context.closed is True
    assert browser_type.browser.closed is True
    assert manager.stopped is True


@pytest.mark.asyncio
async def test_save_storage_state_creates_parent_directory(monkeypatch, tmp_path: Path) -> None:
    browser_type = FakeBrowserType()
    manager = FakePlaywrightManager(browser_type)
    monkeypatch.setattr(
        "src.browser.browser_controller.async_playwright",
        lambda: FakeAsyncPlaywright(manager),
    )

    controller = BrowserController()
    await controller.start()

    out_path = tmp_path / "nested" / "state.json"
    await controller.save_storage_state(str(out_path))

    assert out_path.parent.exists() is True
    assert browser_type.context.storage_state_path == str(out_path)

    await controller.close()
