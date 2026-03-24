from __future__ import annotations

 
import os
import asyncio
from pathlib import Path
from time import monotonic
from typing import Literal, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from src.logging_mp import setup_logging, startlog

logger = startlog(__name__) 

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
        logger.debug(
            "browser.start begin type=%s headless=%s storage_state_path=%s user_data_dir=%s",
            browser_type,
            headless,
            storage_state_path,
            user_data_dir,
        )
        self._playwright = await async_playwright().start()
        launch_fn = getattr(self._playwright, browser_type)

        effective_headless = headless
        if not headless:
            has_display = bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))
            if not has_display:
                effective_headless = True
                logger.warning(
                    "browser.start forced_headless=true because no DISPLAY/WAYLAND_DISPLAY was found"
                )

        launch_args = {
            "headless": effective_headless,
            "channel": "chrome",
            "ignore_default_args": ["--enable-automation"], # 去掉最明显的自动化标记
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--lang=zh-CN",
                "--disable-site-isolation-trials", # 解决某些 iframe 跨域导致的检测问题
                f"--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            ],
        }

        storage_state: str | None = None
        if storage_state_path:
            path = Path(storage_state_path)
            if path.exists():
                storage_state = storage_state_path
                logger.debug("browser.start loading storage state from %s", path)
            else:
                logger.debug("browser.start storage state missing: %s", path)

        if user_data_dir:
            profile_dir = Path(user_data_dir)
            profile_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("browser.start using persistent context profile_dir=%s", profile_dir)
            persistent_attempts = 0
            while persistent_attempts < 2:
                try:
                    self._context = await launch_fn.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        **launch_args,
                    )
                    self._persistent_context = True
                    self._browser = None
                    await self._apply_stealth_to_context(self._context)
                    logger.debug("browser.start completed persistent=%s (with stealth)", self._persistent_context)
                    return
                except Exception as exc:
                    error_text = str(exc)
                    if (
                        "Opening in existing browser session" in error_text
                        or "Target page, context or browser has been closed" in error_text
                    ):
                        logger.warning(
                            "browser.start persistent launch failed due to profile lock; profile_dir=%s error=%s attempt=%d",
                            profile_dir,
                            error_text,
                            persistent_attempts+1
                        )
                        # 清理 profile 目录下的锁文件后重试一次
                        lock_file = profile_dir / "SingletonLock"
                        if lock_file.exists():
                            try:
                                lock_file.unlink()
                                logger.info("browser.start removed profile lock file: %s", lock_file)
                            except Exception as e:
                                logger.warning("browser.start failed to remove lock file: %s error: %s", lock_file, e)
                        # 也可清理其它常见锁文件
                        for extra_lock in profile_dir.glob("*.lock"):
                            try:
                                extra_lock.unlink()
                                logger.info("browser.start removed extra lock file: %s", extra_lock)
                            except Exception as e:
                                logger.warning("browser.start failed to remove extra lock file: %s error: %s", extra_lock, e)
                        persistent_attempts += 1
                        continue
                    else:
                        raise
                break

        self._browser = await launch_fn.launch(**launch_args)
        self._persistent_context = False

        self._context = await self._browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1920, "height": 1080}
        )
        await self._apply_stealth_to_context(self._context)
        logger.debug("browser.start completed persistent=%s (with stealth)", self._persistent_context)
    async def _apply_stealth_to_context(self, context: BrowserContext) -> None:
        """注入 JS 脚本以屏蔽 webdriver 等自动化痕迹"""
        stealth_js = """
        () => {
            // 屏蔽自动化标记
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // 伪造 Chrome 特性
            window.chrome = { runtime: {} };
            // 伪造语言
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            // 伪造平台以匹配 User-Agent
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            // 伪造硬件并发数
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            // 修复 Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        }
        """
        await context.add_init_script(stealth_js)


    async def save_storage_state(self, storage_state_path: str) -> None:
        if self._context is None:
            return
        path = Path(storage_state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(path))

    async def open_page(self, url: str, wait_until: str = "domcontentloaded") -> Page:
        logger.debug("browser.open_page url=%s wait_until=%s", url, wait_until)
        page = await self.context.new_page()
        await page.goto(url, wait_until=wait_until)
        logger.debug("browser.open_page completed url=%s", getattr(page, "url", url))
        return page

    async def close(self) -> None:
        logger.debug("browser.close begin persistent=%s", self._persistent_context)
        if self._context is not None:
            try:
                await self._context.close()
            except Exception as exc:
                logger.warning("browser.close context close failed: %s", exc)
            self._context = None
        if self._browser is not None and not self._persistent_context:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.warning("browser.close browser close failed: %s", exc)
            self._browser = None
        self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning("browser.close playwright stop failed: %s", exc)
            self._playwright = None
        logger.debug("browser.close completed")

    async def handle_cloudflare_challenge(self, page: Page, timeout_ms: int = 5000) -> bool:
        """
        尝试自动通过 Cloudflare Turnstile/Challenge 验证。
        扫描 iframe 并寻找 checkbox。
        """
        start_time = monotonic()
        while (monotonic() - start_time) * 1000 < timeout_ms:
            # 1. 寻找 Cloudflare 常见的 selector
            selectors = [
                 "iframe[src*='cloudflare']",
                 "#turnstile-wrapper iframe",
                 "div#cf-turnstile-wrapper iframe",
            ]
            
            for sel in selectors:
                try:
                    iframe_el = page.locator(sel).first
                    if await iframe_el.is_visible():
                        logger.info(f"[Cloudflare] 发现验证 iframe: {sel}，尝试点击中心...")
                        # 尝试点击 iframe 中间位置（checkbox 通常在中间）
                        box = await iframe_el.bounding_box()
                        if box:
                            await page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                            await asyncio.sleep(2)
                            # 如果 iframe 消失了，说明可能成功了
                            if not await iframe_el.is_visible():
                                logger.info("[Cloudflare] Iframe 已消失，验证可能已通过")
                                return True
                except Exception as e:
                    logger.debug(f"[Cloudflare] 尝试点击失败: {e}")
            
            # 2. 直接找 iframe 内部的 checkbox (如果同源或已注入脚本)
            for frame in page.frames:
                try:
                    # Cloudflare 样式： <input type="checkbox">
                    checkbox = frame.locator("input[type='checkbox']").first
                    if await checkbox.is_visible():
                        logger.info("[Cloudflare] 在 Iframe 中发现 checkbox，点击...")
                        await checkbox.click()
                        await asyncio.sleep(2)
                        return True
                except: pass
            
            await asyncio.sleep(1)
        return False

    async def is_page_healthy(self, page: Page, required_selector: str | None = None) -> bool:
        if page.is_closed():
            logger.warning("browser.health unhealthy reason=page_closed")
            return False
        if required_selector is None:
            logger.debug("browser.health healthy reason=no_required_selector url=%s", page.url)
            return True
        locator = page.locator(required_selector).first
        try:
            await locator.wait_for(state="visible", timeout=1500)
            logger.debug(
                "browser.health healthy selector_visible selector=%s url=%s",
                required_selector,
                page.url,
            )
            return True
        except Exception as exc:
            logger.warning(
                "browser.health unhealthy selector_not_visible selector=%s url=%s error=%s",
                required_selector,
                page.url,
                exc,
            )
            return False
