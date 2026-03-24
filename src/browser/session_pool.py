
from __future__ import annotations

import sys
# 统一 provider->session 单例池


from collections import deque
from dataclasses import dataclass
 
from pathlib import Path
from time import monotonic
from typing import Callable

from playwright.async_api import Page


from src.browser.browser_controller import BrowserController
from src.storage.database import session_scope
from src.storage.database import Base, get_session_maker
from src.storage.database import SessionORM, ProviderConfigORM


from src.logging_mp import setup_logging, startlog

logger = startlog(__name__) 



import threading

@dataclass
class _PoolEntry:
    controller: BrowserController
    page: Page
    url: str
    thread_id: int  # 创建时线程ID
    session_id: str
    provider: str
    lock: bool = False # 是否为锁定状态


class ProviderSessionPool:
    def _profile_dir(self, provider: str, session_id: str) -> Path:
        safe = f"{provider}_{session_id}".replace(":", "_")
        return self.profile_dir / safe
    def __init__(
        self,
        headless: bool = False,
        storage_state_dir: str = "tmp/browser_state",
        profile_dir: str = "tmp/browser_profile",
        controller_factory: Callable[[], BrowserController] | None = None,
    ) -> None:
        self.headless = headless
        self.storage_state_dir = Path(storage_state_dir)
        self.profile_dir = Path(profile_dir)
        self.controller_factory = controller_factory or BrowserController
        self._entries = {}  # type: dict[str, _PoolEntry]
        self._entry_locks = {}  # type: dict[str, threading.Lock]
        # [线程唯一绑定建议]：
        # 1. 保证同一 provider 只被一个线程持有，所有任务调度、get_page、session 分配都必须严格 thread_id 唯一。
        # 2. worker 线程启动时，分配 provider->thread_id 映射，禁止多线程争用。
        # 3. get_page/复用/重建等所有入口都要校验 thread_id，发现冲突立即报错并输出详细日志。
        # 4. 如需动态迁移，必须先销毁原线程 page，再由新线程重建。
        self.required_selector = None  # 兼容 get_page 日志输出
        import os, threading
        logger.warning(
            "[debug] ProviderSessionPool.__init__: pid=%s, thread_id=%s, id(self)=%s, _entries_id=%s, _entries_keys=%s",
            os.getpid(),
            threading.get_ident(),
            id(self),
            id(self._entries),
            list(self._entries.keys()),
        )



    def _state_file(self, provider: str, session_id: str) -> Path:
        safe = f"{provider}_{session_id}".replace(":", "_")
        return self.storage_state_dir / f"{safe}.json"

    async def probe_runtime_session_cookie(self, session_id: str, provider: str) -> tuple[str, str] | None:
        """Read current session cookie directly from live browser context if available."""
        key = provider
        entry = self._entries.get(key)
        if entry is None:
            return None
        try:
            cookies = await entry.controller.context.cookies()
        except Exception as exc:
            logger.warning("pool.probe_runtime_cookie failed key=%s error=%s", key, exc)
            return None
        return self._pick_session_cookie(cookies)

    async def get_page(self, provider: str, session_id: str, url: str) -> Page:
        # 单例一致性断言
        import os, threading
        global _GLOBAL_PROVIDER_SESSION_POOL
        assert _GLOBAL_PROVIDER_SESSION_POOL is not None, f"[get_page] _GLOBAL_PROVIDER_SESSION_POOL 未初始化 pid={os.getpid()} thread_id={threading.get_ident()}"
        assert id(_GLOBAL_PROVIDER_SESSION_POOL) == id(self), f"[get_page] 单例失效: id(self)={id(self)} id(_GLOBAL_PROVIDER_SESSION_POOL)={id(_GLOBAL_PROVIDER_SESSION_POOL)} pid={os.getpid()} thread_id={threading.get_ident()}"
        """
        只允许复用 READY 页面，不能重建已存在但 unhealthy 的页面。
        如果页面对象不存在，则拉起浏览器新建。
        """
        key = provider
        import os, threading
        logger.info(
            "[get_page] pid=%s thread_id=%s key=%s url=%s entries=%s required_selector=%s",
            os.getpid(),
            threading.get_ident(),
            key,
            url,
            list(self._entries.keys()),
            self.required_selector,
        )
        lock = self._entry_locks.setdefault(key, threading.Lock())
        with lock:
            entry = self._entries.get(key)
            is_healthy = False
            if entry is not None:
                if hasattr(entry.page, "is_unhealthy"):
                    is_healthy = not (entry.page.is_closed() or getattr(entry.page, "is_unhealthy")())
                else:
                    is_healthy = not entry.page.is_closed()
            if entry is not None:
                current_thread = threading.get_ident()
                if entry.thread_id != current_thread:
                    logger.error(f"[禁止跨线程] get_page: page 创建于线程 {entry.thread_id}，当前线程 {current_thread}，禁止跨线程传递 Playwright 对象！key={key}")
                    import traceback
                    logger.error(f"[禁止跨线程] get_page 调用栈：\n{traceback.format_stack()}")
                    raise RuntimeError(f"[禁止跨线程] get_page: page 创建于线程 {entry.thread_id}，当前线程 {current_thread}，禁止跨线程传递 Playwright 对象！")
                if is_healthy:
                    logger.info(
                        "[复用] get_page: 命中本进程内存 entry，key=%s, url=%s, page_obj=%s, thread_id=%s",
                        key, entry.url, entry.page, entry.thread_id
                    )
                    return entry.page
                else:
                    logger.error(f"[禁止重建] get_page: entry 存在但不健康，禁止自动重建！key={key}，请手动 reset_session 或修复 page 状态")
                    raise RuntimeError(f"[禁止重建] get_page: entry 存在但不健康，禁止自动重建！key={key}，请手动 reset_session 或修复 page 状态")
            # 若 entry 不存在，允许新建（拉起浏览器）
            logger.info(f"[新建] pool.get_page creating new browser entry key={key} url={url}")
            controller = self.controller_factory()
            state_file = self._state_file(provider, session_id)
            user_data_dir = self._profile_dir(provider, session_id)
            await controller.start(
                browser_type="chromium",
                headless=self.headless,
                storage_state_path=str(state_file),
                user_data_dir=str(user_data_dir),
            )
            from src.storage.repositories import ProviderConfigRepository
            repo = ProviderConfigRepository()
            provider_row = repo.get(provider)
            if provider_row and not provider_row.need_login:
                logger.info("pool.get_page clearing cookies because need_login=False key=%s", key)
                await controller.context.clear_cookies()
            page = await controller.open_page(url)
            self._entries[key] = _PoolEntry(
                controller=controller,
                page=page,
                url=url,
                thread_id=threading.get_ident(),
                session_id=session_id,
                provider=provider,
                lock=provider_row.lock if provider_row else False,
            )
            logger.info(f"[trace] AFTER register: pid={os.getpid()} thread_id={threading.get_ident()} pool._entries.keys={list(self._entries.keys())}")
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

    async def reset_session(self, session_id: str, provider: str) -> None:
        key = provider
        logger.warning("pool.reset_session key=%s", key)
        await self._close_entry(key)

    async def close_all(self) -> None:
        for session_id in list(self._entries.keys()):
            await self._close_entry(session_id)

    async def close_provider_session(self, provider: str) -> None:
        await self._close_entry(provider)

    async def _close_entry(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        if entry is None:
            logger.warning("pool.close_entry skip: entry already missing or key mismatch key=%s", key)
            return
        logger.info("pool.close_entry begin key=%s session_id=%s thread_id=%s", key, entry.session_id, entry.thread_id)
        try:
            provider = entry.provider
            session_id = entry.session_id
            state_file = self._state_file(provider, session_id)
            await entry.controller.save_storage_state(str(state_file))
            logger.debug("pool.close_entry saved storage state key=%s file=%s", key, state_file)
        except Exception as exc:
            logger.warning("pool.close_entry save state failed key=%s error=%s", key, exc)
        try:
            logger.debug("pool.close_entry calling controller.close() key=%s", key)
            await entry.controller.close()
            logger.info("pool.close_entry controller closed key=%s", key)
        except Exception as exc:
            logger.error("pool.close_entry controller close failed key=%s error=%s", key, exc, exc_info=True)
        logger.info("pool.close_entry completed ALL for key=%s", key)



# 全局 ProviderSessionPool 单例
import threading
_GLOBAL_PROVIDER_SESSION_POOL_LOCK = threading.Lock()
_GLOBAL_PROVIDER_SESSION_POOL = None

def get_global_provider_session_pool() -> ProviderSessionPool:
    import os, sys, traceback
    global _GLOBAL_PROVIDER_SESSION_POOL
    if _GLOBAL_PROVIDER_SESSION_POOL is None:
        with _GLOBAL_PROVIDER_SESSION_POOL_LOCK:
            if _GLOBAL_PROVIDER_SESSION_POOL is None:
                _GLOBAL_PROVIDER_SESSION_POOL = ProviderSessionPool()
                logger.warning(f"[NEW] ProviderSessionPool created: id={id(_GLOBAL_PROVIDER_SESSION_POOL)} pid={os.getpid()} import_path={__name__}")
    return _GLOBAL_PROVIDER_SESSION_POOL


# 线程安全获取/创建 provider session（page）
async def get_or_create_provider_session(provider: str, session_id: str, url: str) -> Page:
    pool = get_global_provider_session_pool()
    key = provider
    entry = pool._entries.get(key)
    current_thread = threading.get_ident()
    if entry is not None and not entry.page.is_closed():
        if entry.thread_id != current_thread:
            logger.error(f"[禁止跨线程] get_or_create_provider_session: page 创建于线程 {entry.thread_id}，当前线程 {current_thread}，禁止跨线程传递 Playwright 对象！key={key}")
            raise RuntimeError(f"[禁止跨线程] get_or_create_provider_session: page 创建于线程 {entry.thread_id}，当前线程 {current_thread}，禁止跨线程传递 Playwright 对象！")
        return entry.page
    # 否则新建
    controller = pool.controller_factory()
    state_file = pool._state_file(provider, session_id)
    user_data_dir = pool._profile_dir(provider, session_id)
    await controller.start(
        browser_type="chromium",
        headless=pool.headless,
        storage_state_path=str(state_file),
        user_data_dir=str(user_data_dir),
    )
    from src.storage.repositories import ProviderConfigRepository
    repo = ProviderConfigRepository()
    provider_row = repo.get(provider)
    if provider_row and not provider_row.need_login:
        logger.info("pool.get_or_create_provider_session clearing cookies because need_login=False key=%s", key)
        await controller.context.clear_cookies()
    page = await controller.open_page(url)
    pool._entries[key] = _PoolEntry(
        controller=controller,
        page=page,
        url=url,
        thread_id=current_thread,
        session_id=session_id,
        provider=provider,
        lock=provider_row.lock if provider_row else False,
    )
    return page



# ProviderSessionPoolManager 已废弃，统一用 ProviderSessionPool 单例
