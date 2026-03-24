


# 修复：future import 必须在文件最顶部，去除重复定义，整理结构
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional

from src.logging_mp import setup_logging, startlog


logger = startlog(__name__)

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
        2. 发送消息（拼接 prompt+document_text）。
        3. 等待回复。
        4. 返回标准 ProcessResult。
        """
        from src.browser.worker import ProcessResult
        try:
            # 0. 重新加载最新配置，避免长时间运行导致的配置过期
            self._load_selectors_from_provider()

            # 1. 检查登录状态
            if not await self.is_logged_in(page):
                return ProcessResult(ok=False, error_message="Not logged in", permanent_failure=True)

            # 2. 发送消息（拼接 prompt+document_text）
            await self.send_message(page, decision.prompt, getattr(decision, "document_text", ""))

            # 3. 等待回复
            reply = await self.wait_for_response(page, previous_response=None, timeout_ms=60000)
            if not reply:
                return ProcessResult(ok=False, error_message="No reply received", permanent_failure=False)

            # 4. 返回成功
            return ProcessResult(ok=True, error_message=None, raw_response=reply)
        except Exception as exc:
            return ProcessResult(ok=False, error_message=f"chat failed: {exc}", permanent_failure=False)


    
    def _load_selectors_from_provider(self):
        repo = ProviderConfigRepository()
        row = repo.get(self.provider_name)
        
        # 默认 input_selector（空值兜底）
        default_input_selectors = (
            "textarea, input[type='text'], [contenteditable='true']",
        )
        
        if not row:
            self.input_selectors = default_input_selectors
            self.send_button_selectors = ()
            self.response_selectors = ()
            return

        # 1. 优先从独立字段加载
        input_sel = row.input_selector
        send_sel = row.send_button_selector
        reply_sel = row.reply_selector
        
        # 2. 如果独立字段为空，尝试从 legacy JSON 字段兜底
        if not (input_sel or send_sel or reply_sel) and row.ready_selectors_json:
            try:
                data = json.loads(row.ready_selectors_json)
                input_sel = data.get("input_selector")
                send_sel = data.get("send_button_selector")
                reply_sel = data.get("response_selector") or data.get("reply_selector")
            except Exception:
                pass

        # 3. 设置实例属性
        self.input_selectors = (input_sel,) if input_sel else default_input_selectors
        self.send_button_selectors = (send_sel,) if send_sel else ()
        self.response_selectors = (reply_sel,) if reply_sel else ()
        
        # 记录日志方便调试
        logger.debug(f"[_load_selectors_from_provider] {self.provider_name} loaded: "
                     f"input={self.input_selectors}, send={self.send_button_selectors}, "
                     f"response={self.response_selectors}")

    async def is_logged_in(self, page: Any) -> bool:
        # 默认实现：假定已登录，或需自定义
        return True

    async def send_message(self, page: Any, message: str, document_text: str = "") -> None:
        """
        通用 send_message 实现：
        1. 选取 input_selector，填充 message+document_text。
        2. 若 send_button_selector 存在且可见，则点击按钮。
        3. 否则在输入框回车（Enter/Control+Enter）。
        """
        
        
        # 拼接输入内容
        full_text = message
        if document_text:
            full_text = f"{message}\n{document_text}" if message else document_text
        logger.info(f"[send_message] provider={self.provider_name} full_text={full_text!r}")
        input_selector = await self._pick_visible_selector(page, self.input_selectors)
        logger.info(f"[send_message] input_selector={input_selector}")
        if not input_selector:
            logger.error(f"[send_message] No visible input_selector found for provider={self.provider_name}")
            raise RuntimeError(f"No visible input_selector found for provider={self.provider_name}")
        input_box = page.locator(input_selector).first
        await input_box.focus()
        await input_box.fill(full_text)
        logger.info(f"[send_message] filled input_box with text and focused")

        # 优先点击发送按钮
        send_selector = await self._pick_visible_selector(page, self.send_button_selectors)
        logger.info(f"[send_message] send_button_selector={send_selector}")

        if send_selector:
            send_btn = page.locator(send_selector).first
            try:
                await send_btn.scroll_into_view_if_needed()
                await send_btn.click()
                logger.info(f"[send_message] clicked send button: {send_selector}")
                import asyncio
                await asyncio.sleep(0.5)
                # 检查输入框是否已清空，未清空则兜底回车
                try:
                    value = await input_box.input_value()
                except Exception:
                    value = await input_box.inner_text()
                    
                if value.strip() != "":
                    logger.warning(f"[send_message] input_box not cleared after click, fallback to Enter")
                    try:
                        await input_box.press("Enter")
                        logger.info(f"[send_message] pressed Enter as fallback")
                        await asyncio.sleep(0.5)
                    except Exception as exc2:
                        logger.error(f"[send_message] Enter fallback failed: {exc2}")
                return
            except Exception as exc:
                logger.error(f"[send_message] click send button failed: {exc}")

        # 否则尝试回车发送
        # 有些平台用 Control+Enter，有些用 Enter
        try:
            await input_box.press("Control+Enter")
            logger.info(f"[send_message] pressed Control+Enter")
        except Exception as exc:
            logger.warning(f"[send_message] Control+Enter failed: {exc}")
            try:
                await input_box.press("Enter")
                logger.info(f"[send_message] pressed Enter")
            except Exception as exc2:
                logger.error(f"[send_message] Enter failed: {exc2}")

        # === 新增：自动等待 response_selector/reply_selector 匹配元素出现，确保页面渲染 ===
        import asyncio
        selectors = list(self.response_selectors) if getattr(self, "response_selectors", None) else []
        # fallback 兼容 reply_selector
        fallback_selectors = [
            'p.ds-markdown-paragraph',
            '.ds-markdown-paragraph',
            'p[class*="markdown"]',
        ]
        selectors += [s for s in fallback_selectors if s not in selectors]
        found = False
        for sel in selectors:
            try:
                logger.info(f"[send_message] wait_for_selector('{sel}') for reply area...")
                await page.wait_for_selector(sel, timeout=3000)
                found = True
                logger.info(f"[send_message] reply area appeared: {sel}")
                break
            except Exception as exc:
                logger.info(f"[send_message] wait_for_selector('{sel}') timeout or error: {exc}")
        if not found:
            logger.warning(f"[send_message] No reply area appeared after send, selectors tried: {selectors}")
        await asyncio.sleep(0.2)

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
        3. 日志输出 selector 匹配数量，多个元素取最后一个。
        """
        import asyncio, time
        default_response_selectors = (
            '[data-testid="assistant-message"]',
            '[data-message] div',
            '.message, .chat-message',
        )
        selectors = self.response_selectors or default_response_selectors
        logger.info(f"[wait_for_response] using selectors={selectors}")
        
        fallback_selectors = (
            '.ds-message:last-of-type .ds-markdown-paragraph',
            'p.ds-markdown-paragraph',
            '.ds-markdown-paragraph',
            'p[class*="markdown"]',
        )
        tried_selectors = list(selectors)
        for sel in fallback_selectors:
            if sel not in tried_selectors:
                tried_selectors.append(sel)
        
        start = time.monotonic()
        last_text = None
        first_wait = True
        last_change_time = time.monotonic()
        
        while (time.monotonic() - start) * 1000 < timeout_ms:
            # Dynamically check for any visible selector in tried_selectors
            selector = await self._pick_visible_selector(page, tuple(tried_selectors))
            if not selector:
                if first_wait:
                    first_sel = tried_selectors[0]
                    try:
                        logger.info(f"[wait_for_response] first wait_for_selector('{first_sel}') for async render...")
                        await page.wait_for_selector(first_sel, timeout=3000)
                    except Exception as exc:
                        logger.info(f"[wait_for_response] wait_for_selector timeout or error: {exc}")
                    first_wait = False
                await asyncio.sleep(0.5)
                continue

            locator = page.locator(selector)
            try:
                count = await locator.count()
                logger.debug(f"[wait_for_response] selector '{selector}' matched {count} elements")
                if count > 0:
                    # 取所有匹配元素的最后一个（最新回复）
                    last_locator = locator.nth(count - 1)
                    is_vis = await last_locator.is_visible()
                    logger.debug(f"[wait_for_response] last_locator is_visible={is_vis}")
                    if is_vis:
                        texts = await last_locator.all_inner_texts()
                        text = self.normalize_text("\n".join(texts) if isinstance(texts, list) else str(texts))
                        if not text:
                            # fallback to textContent
                            try:
                                raw_text = await last_locator.evaluate("el => el.textContent")
                                text = self.normalize_text(raw_text or "")
                                logger.debug(f"[wait_for_response] all_inner_texts empty, textContent yielded {len(text)} chars")
                            except Exception as eval_exc:
                                logger.warning(f"[wait_for_response] evaluate textContent failed: {eval_exc}")
                        
                        logger.debug(f"[wait_for_response] extracted text length={len(text)}")
                        
                        if text and text != previous_response:
                            if text != last_text:
                                last_text = text
                                last_change_time = time.monotonic()
                            else:
                                if time.monotonic() - last_change_time > 1.0:
                                    logger.info(f"[wait_for_response] text stable for 1s, returning {len(text)} chars...")
                                    return text
            except Exception as exc:
                logger.warning(f"[wait_for_response] Exception: {exc}")
            await asyncio.sleep(0.2)

        # 超时处理
        if not last_text:
            try:
                content = await page.content()
                import datetime, os
                ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                fname = f"/tmp/ai_free_chatbot_page_content_{self.provider_name}_{ts}.html"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.error(f"[wait_for_response] Dumped page.content() to {fname}")
            except Exception as exc:
                logger.error(f"[wait_for_response] Failed to dump page.content(): {exc}")
            logger.error(f"[wait_for_response] No visible response_selector found for provider={self.provider_name}, selectors tried: {tried_selectors}")
            
        logger.warning(f"[wait_for_response] timeout, return last_text: {last_text}")
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
