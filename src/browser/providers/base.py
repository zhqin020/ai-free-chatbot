


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


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.browser.worker import ProcessResult
import json
from ...storage.repositories import ProviderConfigRepository

class DefaultProviderAdapter(ProviderAdapter):
    """
    通用 provider 适配器，自动读取 provider ready_selectors_json 字段。
    """
    def __init__(self, provider_name: str = "unknown"):
        super().__init__()
        self.provider_name = provider_name
        self._load_selectors_from_provider()


    
    async def run(self, page, decision):
        """
        通用 chat 流程：
        1. 检查登录状态。
        2. 发送消息。
        3. 等待回复。
        4. 返回标准 ProcessResult。
        """
        from src.browser.worker import ProcessResult
        try:
            # 1. 检查登录状态
            if not await self.is_logged_in(page):
                return ProcessResult(ok=False, error_message="Not logged in", permanent_failure=True)

            # 2. 发送消息
            await self.send_message(page, decision.prompt)

            # 3. 等待回复
            reply = await self.wait_for_response(page, previous_response=None, timeout_ms=60000)
            if not reply:
                return ProcessResult(ok=False, error_message="No reply received", permanent_failure=False)

            # 4. 返回成功
            return ProcessResult(ok=True, error_message=None, reply=reply)
        except Exception as exc:
            return ProcessResult(ok=False, error_message=f"chat failed: {exc}", permanent_failure=False)


    
    def _load_selectors_from_provider(self):
        repo = ProviderConfigRepository()
        row = repo.get(self.provider_name)
        # 默认 input_selector（可根据实际平台补充更多）
        default_input_selectors = (
            "textarea, input[type='text'], [contenteditable='true']",
        )
        if row and row.ready_selectors_json:
            try:
                data = json.loads(row.ready_selectors_json)
                # 合并 input_selector 和 input_selector_candidates，去重且保持顺序
                selectors = []
                if data.get("input_selector"):
                    selectors.append(data["input_selector"])
                if data.get("input_selector_candidates"):
                    for s in data["input_selector_candidates"]:
                        if s not in selectors:
                            selectors.append(s)
                if selectors:
                    self.input_selectors = tuple(selectors)
                else:
                    self.input_selectors = default_input_selectors
                self.send_button_selectors = (data.get("send_button_selector"),) if data.get("send_button_selector") else ()
                self.response_selectors = (data.get("response_selector"),) if data.get("response_selector") else ()
            except Exception:
                self.input_selectors = default_input_selectors
                self.send_button_selectors = ()
                self.response_selectors = ()
        else:
            self.input_selectors = default_input_selectors
            self.send_button_selectors = ()
            self.response_selectors = ()

    async def is_logged_in(self, page: Any) -> bool:
        # 默认实现：假定已登录，或需自定义
        return True

    async def send_message(self, page: Any, message: str) -> None:
        """
        通用 send_message 实现：
        1. 选取 input_selector，填充 message。
        2. 若 send_button_selector 存在且可见，则点击按钮。
        3. 否则在输入框回车（Enter/Control+Enter）。
        """
        input_selector = await self._pick_visible_selector(page, self.input_selectors)
        if not input_selector:
            raise RuntimeError(f"No visible input_selector found for provider={self.provider_name}")
        input_box = page.locator(input_selector).first
        await input_box.fill(message)

        # 优先点击发送按钮
        send_selector = await self._pick_visible_selector(page, self.send_button_selectors)
        if send_selector:
            send_btn = page.locator(send_selector).first
            await send_btn.click()
            return

        # 否则尝试回车发送
        # 有些平台用 Control+Enter，有些用 Enter
        try:
            await input_box.press("Control+Enter")
        except Exception:
            await input_box.press("Enter")

    async def wait_for_response(
        self,
        page: Any,
        previous_response: str | None = None,
        timeout_ms: int = 60000,
    ) -> Optional[str]:
        """
        通用 wait_for_response 实现：
        1. 选取 response_selector，轮询抓取响应文本。
        2. 支持超时、去重，若 response_selector 缺失则 fallback 到常见区域。
        """
        import asyncio, time
        # 默认 response_selector fallback
        default_response_selectors = (
            '[data-testid="assistant-message"]',
            '[data-message] div',
            '.message, .chat-message',
        )
        selectors = self.response_selectors or default_response_selectors
        selector = await self._pick_visible_selector(page, selectors)
        if not selector:
            raise RuntimeError(f"No visible response_selector found for provider={self.provider_name}")
        locator = page.locator(selector).first
        start = time.monotonic()
        last_text = None
        while (time.monotonic() - start) * 1000 < timeout_ms:
            try:
                if await locator.is_visible():
                    texts = await locator.all_inner_texts()
                    text = self.normalize_text("\n".join(texts) if isinstance(texts, list) else str(texts))
                    if text and text != previous_response:
                        # 若内容有变化且非空，直接返回
                        return text
                    last_text = text
            except Exception:
                pass
            await asyncio.sleep(0.5)
        # 超时返回最后一次抓到的内容
        return last_text


class ProviderAdapter_(ABC):
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
