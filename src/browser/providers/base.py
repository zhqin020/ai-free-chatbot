


# 修复：future import 必须在文件最顶部，去除重复定义，整理结构
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional


class ProviderAdapter(ABC):
    provider_name: str = "unknown"
    input_selectors: tuple[str, ...] = ()
    send_button_selectors: tuple[str, ...] = ()
    response_selectors: tuple[str, ...] = ()

    async def inspect_page_state(self, page: Any) -> dict:
        """
        通用 chat 页面状态检测：输入框可见即 chat_ready。
        子类可扩展/覆盖。
        返回 dict: {chat_ready, cookie_required, verification_required, login_required}
        """
        input_selector = await self._pick_visible_selector(page, self.input_selectors)
        chat_ready = input_selector is not None
        # 默认不检测 cookie/验证/登录弹窗，子类可扩展
        return {
            "chat_ready": chat_ready,
            "cookie_required": False,
            "verification_required": False,
            "login_required": False,
        }

    @abstractmethod
    async def is_logged_in(self, page: Any) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def send_message(self, page: Any, message: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def wait_for_response(
        self,
        page: Any,
        previous_response: str | None = None,
        timeout_ms: int = 60000,
    ) -> Optional[str]:
        raise NotImplementedError

    async def _pick_visible_selector(self, page: Any, selectors: tuple[str, ...]) -> Optional[str]:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.is_visible():
                    return selector
            except Exception:
                continue
        return None

    @staticmethod
    def normalize_text(value: str | None) -> str:
        if not value:
            return ""
        return "\n".join(line.rstrip() for line in value.strip().splitlines()).strip()



import json
from src.storage.repositories import ProviderConfigRepository

class DefaultProviderAdapter(ProviderAdapter):
    """
    通用 provider 适配器，自动读取 provider ready_selectors_json 字段。
    """
    def __init__(self, provider_name: str = "unknown"):
        super().__init__()
        self.provider_name = provider_name
        self._load_selectors_from_provider()

    def _load_selectors_from_provider(self):
        repo = ProviderConfigRepository()
        row = repo.get(self.provider_name)
        if row and row.ready_selectors_json:
            try:
                data = json.loads(row.ready_selectors_json)
                self.input_selectors = (data.get("input_selector"),) if data.get("input_selector") else ()
                self.send_button_selectors = (data.get("send_button_selector"),) if data.get("send_button_selector") else ()
                self.response_selectors = (data.get("response_selector"),) if data.get("response_selector") else ()
            except Exception:
                self.input_selectors = ()
                self.send_button_selectors = ()
                self.response_selectors = ()
        else:
            self.input_selectors = ()
            self.send_button_selectors = ()
            self.response_selectors = ()

    async def is_logged_in(self, page: Any) -> bool:
        # 默认实现：假定已登录，或需自定义
        return True

    async def send_message(self, page: Any, message: str) -> None:
        # 必须由具体 provider 配置实现
        raise NotImplementedError("send_message 必须由具体 provider 配置实现")

    async def wait_for_response(
        self,
        page: Any,
        previous_response: str | None = None,
        timeout_ms: int = 60000,
    ) -> Optional[str]:
        # 必须由具体 provider 配置实现
        raise NotImplementedError("wait_for_response 必须由具体 provider 配置实现")


class ProviderAdapter(ABC):
    provider_name: str = "unknown"
    input_selectors: tuple[str, ...] = ()
    send_button_selectors: tuple[str, ...] = ()
    response_selectors: tuple[str, ...] = ()

    async def inspect_page_state(self, page: Any) -> dict:
        """
        通用 chat 页面状态检测：输入框可见即 chat_ready。
        子类可扩展/覆盖。
        返回 dict: {chat_ready, cookie_required, verification_required, login_required}
        """
        input_selector = await self._pick_visible_selector(page, self.input_selectors)
        chat_ready = input_selector is not None
        # 默认不检测 cookie/验证/登录弹窗，子类可扩展
        return {
            "chat_ready": chat_ready,
            "cookie_required": False,
            "verification_required": False,
            "login_required": False,
        }

    @abstractmethod
    async def is_logged_in(self, page: Any) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def send_message(self, page: Any, message: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def wait_for_response(
        self,
        page: Any,
        previous_response: str | None = None,
        timeout_ms: int = 60000,
    ) -> Optional[str]:
        raise NotImplementedError

    async def _pick_visible_selector(self, page: Any, selectors: tuple[str, ...]) -> Optional[str]:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.is_visible():
                    return selector
            except Exception:
                continue
        return None

    @staticmethod
    def normalize_text(value: str | None) -> str:
        if not value:
            return ""
        return "\n".join(line.rstrip() for line in value.strip().splitlines()).strip()
