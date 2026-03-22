

from __future__ import annotations

import pytest
import types
import inspect
import asyncio
import threading
import time
import json

from src.browser.session_pool import get_global_provider_session_pool
from src.storage.repositories import ProviderConfigRepository

import types
import inspect
import pytest
import asyncio
@pytest.mark.asyncio
async def test_create_and_get_page(monkeypatch):
    """
    验证异步创建 session 并获取 page，page 对象可用。
    使用 monkeypatch 替换 BrowserController，避免真实浏览器依赖。
    """
    from src.browser import session_pool
    class DummyPage:
        def __init__(self, url=None):
            self.url = url
        def is_closed(self):
            return False
    class DummyController:
        async def start(self, *a, **k): pass
        async def open_page(self, url):
            self._url = url
            return DummyPage(url)
        async def save_storage_state(self, path): pass
        @property
        def context(self):
            class Ctx:
                async def cookies(self): return []
            return Ctx()
        async def close(self): pass
    monkeypatch.setattr(session_pool, "BrowserController", DummyController)
    pool = session_pool.get_global_provider_session_pool()
    # 强制替换 controller_factory，确保 DummyController
    pool.controller_factory = DummyController
    provider = "test"
    session_id = "sid"
    url = "http://test/"
    page = await pool.get_page(provider, session_id, url)
    assert hasattr(page, "is_closed") and not page.is_closed(), "page 未正确创建或不可用"

    
def test_singleton_pool_instance():
    pool1 = get_global_provider_session_pool()
    pool2 = get_global_provider_session_pool()
    assert pool1 is pool2, "ProviderSessionPool 单例失效：多次获取不是同一对象"
