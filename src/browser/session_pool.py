from __future__ import annotations
# 统一 pool key 生成函数，确保全链路一致
def make_pool_key(provider: str, session_id: str) -> str:
    return f"{provider}:{session_id}"

from collections import deque
from dataclasses import dataclass
import logging
from pathlib import Path
from time import monotonic
from typing import Callable

from playwright.async_api import Page


from src.browser.browser_controller import BrowserController
from src.storage.database import session_scope
from src.storage.pool_entry_repository import PoolEntryRepository
from src.models.pool_entry import PageStatus
from src.storage.database import Base, get_session_maker
from src.storage.database import SessionORM, ProviderConfigORM



logger = logging.getLogger(__name__)



import threading

@dataclass
class _PoolEntry:
    controller: BrowserController
    page: Page
    url: str
    thread_id: int  # 创建时线程ID


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
        self._entry_locks: dict[str, threading.Lock] = {}
        logger.warning(
            "[debug] BrowserSessionPool.__init__: id(self)=%s, _entries_id=%s, _entries_keys=%s",
            id(self),
            id(self._entries),
            list(self._entries.keys()),
        )

    @staticmethod
    def _make_key(provider: str, session_id: str) -> str:
        # 始终调用全局 make_pool_key，保证一致
        return make_pool_key(provider, session_id)

    def _state_file(self, provider: str, session_id: str) -> Path:
        safe = f"{provider}_{session_id}".replace(":", "_")
        return self.storage_state_dir / f"{safe}.json"

    def _profile_dir(self, provider: str, session_id: str) -> Path:
        safe = f"{provider}_{session_id}".replace(":", "_")
        return self.profile_dir / safe

    @staticmethod
    def _pick_session_cookie(cookies: list[dict]) -> tuple[str, str] | None:
        candidate_names = {
            "sessionid",
            "session",
            "sid",
            "jsessionid",
            "phpsessid",
            "connect.sid",
            "_session",
        }
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get("name") or "").strip()
            value = str(cookie.get("value") or "").strip()
            if not name or not value:
                continue
            lowered = name.lower()
            if lowered in candidate_names or "sess" in lowered:
                return name, value
        return None

    async def probe_runtime_session_cookie(self, session_id: str, provider: str) -> tuple[str, str] | None:
        """Read current session cookie directly from live browser context if available."""
        key = self._make_key(provider, session_id)
        entry = self._entries.get(key)
        if entry is None:
            return None
        try:
            cookies = await entry.controller.context.cookies()
        except Exception as exc:
            logger.warning("pool.probe_runtime_cookie failed key=%s error=%s", key, exc)
            return None
        return self._pick_session_cookie(cookies)

    async def get_page(self, session_id: str, url: str, provider: str) -> Page:
        """
        支持跨进程共享：先查数据库 pool_entries 表，若有可用页面则优先复用，否则新建。
        """
        key = self._make_key(provider, session_id)
        logger.info(
            "[debug] pool.get_page: id(self)=%s, _entries_id=%s, key=%s, all_keys=%s",
            id(self),
            id(self._entries),
            key,
            list(self._entries.keys()),
        )
        logger.debug(
            "pool.get_page key=%s target_url=%s required_selector=%s",
            key,
            url,
            self.required_selector,
        )
        # 0. provider 合法性校验
        with session_scope() as db:
            if not db.query(ProviderConfigORM).filter_by(name=provider).first():
                logger.error(f"[pool] get_page: provider 不存在: {provider}, session_id={session_id}, url={url}")
                raise ValueError(f"Invalid provider: {provider}")
        # 1. 线程安全：为每个 key 加锁，防止并发重复创建
        lock = self._entry_locks.setdefault(key, threading.Lock())
        with lock:
            # 再查一次内存，防止并发重复创建
            entry = self._entries.get(key)
            # 健康检查：如有自定义 unhealthy 标志可扩展此处
            is_healthy = False
            if entry is not None:
                # 允许 page 对象有 is_unhealthy 属性或方法
                if hasattr(entry.page, "is_unhealthy"):
                    is_healthy = not (entry.page.is_closed() or getattr(entry.page, "is_unhealthy")())
                else:
                    is_healthy = not entry.page.is_closed()
            if entry is not None and is_healthy:
                current_thread = threading.get_ident()
                if entry.thread_id != current_thread:
                    logger.error(f"[禁止跨线程] get_page: page 创建于线程 {entry.thread_id}，当前线程 {current_thread}，禁止跨线程传递 Playwright 对象！key={key}")
                    raise RuntimeError(f"[禁止跨线程] get_page: page 创建于线程 {entry.thread_id}，当前线程 {current_thread}，禁止跨线程传递 Playwright 对象！")
                logger.info(
                    "[debug] get_page pre-check: id(self)=%s, key=%s, entry_exists=True, entry_url=%s, page_obj=%s, page_closed=False",
                    id(self), key, entry.url, entry.page
                )
                if entry.url != url:
                    logger.info("pool.get_page navigate existing page key=%s from=%s to=%s", key, entry.url, url)
                    await entry.page.goto(url, wait_until="domcontentloaded")
                    entry.url = url
                # 更新数据库心跳
                with session_scope() as db:
                    repo = PoolEntryRepository(db)
                    repo.upsert(provider, session_id, entry.url, PageStatus.ACTIVE)
                return entry.page
            # 若 entry 存在但不健康，主动移除，准备重建
            if entry is not None and not is_healthy:
                logger.info(f"pool.get_page: unhealthy entry detected for key={key}, will recreate")
                # 先关闭旧 controller
                try:
                    await entry.controller.close()
                except Exception as exc:
                    logger.warning(f"pool.get_page: close old controller failed for key={key}, error={exc}")
                self._entries.pop(key, None)
            # 2. 查数据库，尝试复用其它进程注册的页面（伪分布式，实际无法直接复用对象，仅做状态同步）
            with session_scope() as db:
                repo = PoolEntryRepository(db)
                db_entry = repo.get(provider, session_id)
                if db_entry and db_entry.page_status == PageStatus.ACTIVE:
                    logger.info("[debug] pool.get_page: found db entry, 但无法直接复用对象，仅做状态同步: %s", db_entry)
                    # 理论上可通知其它进程复用，但此处仅做演示
            # 3. 新建页面并注册
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
            self._entries[key] = _PoolEntry(controller=controller, page=page, url=url, thread_id=threading.get_ident())
            # 注册到数据库
            with session_scope() as db:
                repo = PoolEntryRepository(db)
                repo.upsert(provider, session_id, url, PageStatus.ACTIVE)
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


# 全局线程安全 session pool 单例
import threading
_session_pool_singleton = None
_session_pool_lock = threading.Lock()

def get_global_session_pool() -> BrowserSessionPool:
    global _session_pool_singleton
    if _session_pool_singleton is None:
        with _session_pool_lock:
            if _session_pool_singleton is None:
                _session_pool_singleton = BrowserSessionPool()
    return _session_pool_singleton

# 线程安全获取/创建 session（page）
async def get_or_create_session(session_id: str, url: str, provider: str) -> Page:
    pool = get_global_session_pool()
    key = pool._make_key(provider, session_id)
    entry = pool._entries.get(key)
    current_thread = threading.get_ident()
    if entry is not None and not entry.page.is_closed():
        if entry.thread_id != current_thread:
            logger.error(f"[禁止跨线程] get_or_create_session: page 创建于线程 {entry.thread_id}，当前线程 {current_thread}，禁止跨线程传递 Playwright 对象！key={key}")
            raise RuntimeError(f"[禁止跨线程] get_or_create_session: page 创建于线程 {entry.thread_id}，当前线程 {current_thread}，禁止跨线程传递 Playwright 对象！")
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
    page = await controller.open_page(url)
    pool._entries[key] = _PoolEntry(controller=controller, page=page, url=url, thread_id=current_thread)
    return page


class ProviderSessionPoolManager:
    def __init__(
        self,
        *,
        headless: bool = True,
        required_selectors: dict[str, str] | None = None,
        controller_factory: Callable[[], BrowserController] | None = None,
    ) -> None:
        self.headless = headless
        self.required_selectors = required_selectors or {}
        self.controller_factory = controller_factory
        self._pools: dict[str, BrowserSessionPool] = {}

    def get_pool(self, provider: str) -> BrowserSessionPool:
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
