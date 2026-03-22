from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from os import getenv
from time import perf_counter
from typing import Protocol
from uuid import uuid4

## 延迟导入，避免循环依赖
from src.storage.repositories import ProviderConfigRepository
from src.browser.scheduler import DispatchDecision, WeightedRoundRobinScheduler
from src.browser.session_pool import get_global_provider_session_pool, get_or_create_provider_session
from src.models.session import SessionState
from src.models.task import TaskStatus
from datetime import datetime, UTC
from src.parser import JSONValidator, ResponseExtractor, RetryHandler
from src.prompt import PromptGenerator
from src.storage.repositories import LogRepository, SessionRepository, TaskRepository
import threading
from src.browser.providers import ProviderAdapter
import queue
import time
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

from src.logging_mp import setup_logging, startlog


logger = startlog('browser.worker')

# === 全局线程安全命令队列与消息结构 ===
COMMAND_QUEUE: 'queue.Queue[WorkerCommand]' = queue.Queue()
RESULT_QUEUE: 'queue.Queue[WorkerCommandResult]' = queue.Queue()

COMMAND_TIMEOUT_SECONDS = 30  # 命令超时时间，可根据实际需求调整

import os


# --- SessionManager 统一 session 生命周期管理 ---
from src.browser.session_manager import SessionManager
session_manager = SessionManager()

# --- worker 线程主循环/启动逻辑 ---
def start_all_worker_threads(logger=None):
    """
    启动所有 provider 的 worker 线程。主入口由 main.py 调用。
    """
    import threading
    import asyncio
    from src.browser.session_pool import get_global_provider_session_pool, get_or_create_provider_session
    from src.browser.providers.base import DefaultProviderAdapter
    from src.storage.repositories import SessionRepository, TaskRepository
    from sqlalchemy import select
    from src.storage.database import ProviderConfigORM, session_scope
    # 延迟导入，避免循环依赖
    
    from src.browser.worker import PooledProviderTaskProcessor

    with session_scope() as session:
        provider_rows = session.execute(select(ProviderConfigORM)).scalars().all()
        providers = sorted(set(row.name for row in provider_rows if row.name))
    if not providers:
        if logger:
            logger.warning("[worker] 未检测到任何 provider，会跳过 worker 线程启动。请先初始化 provider_configs 表。")
        return

    def worker_thread(provider):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        pool = get_global_provider_session_pool()
        session_repo = SessionRepository()
        task_repo = TaskRepository()
        adapter = DefaultProviderAdapter(provider)
        # 获取 provider url
        with session_scope() as session:
            provider_row = session.execute(select(ProviderConfigORM).where(ProviderConfigORM.name == provider)).scalars().first()
            chat_url = provider_row.url if provider_row and provider_row.url else "about:blank"
        session_id = f"s-{provider}-1"
        owner = str(threading.get_ident())
        # 统一通过 SessionManager 创建/同步 session
        session_manager.get_or_create(session_id, provider, chat_url, owner)
        if logger:
            logger.info(f"[worker] 启动线程: provider={provider} thread_id={owner} pid={os.getpid()} url={chat_url}")
        print(f"[worker-thread-debug] provider={provider} thread_id={owner} pid={os.getpid()} url={chat_url}")
        processor = PooledProviderTaskProcessor(
            provider=provider,
            adapter=adapter,
            session_repo=session_repo,
            task_repo=task_repo,
            session_pool=pool,
        )
        async def run():
            await get_or_create_provider_session(provider, session_id, chat_url)
            while True:
                await processor.run_once()
                await asyncio.sleep(0.5)
        loop.run_until_complete(run())

    threads = []
    for provider in providers:
        t = threading.Thread(target=worker_thread, args=(provider,), name=f"WorkerThread-{provider}", daemon=True)
        t.start()
        threads.append(t)



@dataclass
class WorkerCommand:
    command_id: str
    command_type: str
    params: Dict[str, Any]
    target_thread_id: str
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    timestamp: float = field(default_factory=lambda: time.time())  # 命令创建时间戳

@dataclass
class WorkerCommandResult:
    command_id: str
    status: str  # success, error, timeout
    result: Any = None
    error_message: Optional[str] = None
    timestamp: float = field(default_factory=lambda: time.time())

def put_command(command: WorkerCommand):
    COMMAND_QUEUE.put(command)

def get_command_for_thread(thread_id: str) -> Optional[WorkerCommand]:
    """
    线程安全地获取并移除队列中属于指定线程的命令，超时命令自动丢弃。
    """
    now = time.time()
    temp = []
    found = None
    while not COMMAND_QUEUE.empty():
        cmd = COMMAND_QUEUE.get()
        # 超时命令直接丢弃
        if now - cmd.timestamp > COMMAND_TIMEOUT_SECONDS:
            logger.warning(f"[WorkerCommand] 丢弃超时命令: {cmd.command_id} type={cmd.command_type}")
            continue
        if cmd.target_thread_id == thread_id and found is None:
            found = cmd
        else:
            temp.append(cmd)
    # 其余命令重新放回队列
    for cmd in temp:
        COMMAND_QUEUE.put(cmd)
    return found

def put_command_result(result: WorkerCommandResult):
    RESULT_QUEUE.put(result)

def get_command_result(command_id: str, timeout: float = 10.0) -> Optional[WorkerCommandResult]:
    """
    阻塞等待指定 command_id 的结果，超时返回 None。
    """
    deadline = time.time() + timeout
    temp = []
    found = None
    while time.time() < deadline:
        while not RESULT_QUEUE.empty():
            res = RESULT_QUEUE.get()
            if res.command_id == command_id:
                found = res
                break
            else:
                temp.append(res)
        if found:
            break
        time.sleep(0.05)
    # 其余结果重新放回队列
    for res in temp:
        RESULT_QUEUE.put(res)
    return found


async def auto_extract_chat_selectors(provider: str, session_id: str, session_pool, logger=None) -> dict:
    """
    自动提取 chat 页面 input/send/response selector，供 API 填充 provider_configs。
    """
    if logger is None:
        logger = logging.getLogger('browser.worker')
    if session_pool is None:
        raise RuntimeError("session_pool must be passed explicitly to auto_extract_chat_selectors!")
    pool = session_pool
    from src.storage.repositories import SessionRepository
    session_repo = SessionRepository()
    row = session_repo.get(session_id)
    if row is None:
        raise RuntimeError(f"session not found: {session_id}")
    page = await pool.get_page(session_id=session_id, url=row.chat_url, provider=provider)
    selectors = {}
    logger.info(f"[auto_extract_chat_selectors] provider={provider} session_id={session_id} page_url={getattr(page, 'url', None)} 开始提取 selector")
    # 输入框区域
    input_candidates = [
        # 精确匹配 deepseek 特有 placeholder
        "textarea[placeholder='Message DeepSeek']",
        "textarea[data-testid='chat-input']",
        "textarea[placeholder*='message' i]",
        "div[contenteditable='true']",
        "textarea",
        "input[type='text']",
        "[contenteditable='true']",
        "textarea[aria-label]",
        "input[aria-label]",
    ]
    input_found = []
    for sel in input_candidates:
        try:
            el = page.locator(sel).first
            if await el.is_visible():
                input_found.append(sel)
        except Exception:
            continue
    if input_found:
        selectors["input_selector"] = input_found[0]
        selectors["input_selector_candidates"] = input_found

    # 发送按钮区域
    send_candidates = [
        "button[data-testid='send-button']",
        "button[aria-label*='send' i]",
        "button:has-text('Send')",
        "button:has-text('发送')",
        "button[type='submit']",
        "div[role='button'].ds-icon-button",
        "div.ds-icon-button[role='button']",
        "div[role='button']",
    ]
    send_found = []
    for sel in send_candidates:
        try:
            el = page.locator(sel).first
            if await el.is_visible():
                send_found.append(sel)
        except Exception:
            continue
    if send_found:
        selectors["send_button_selector"] = send_found[0]
        selectors["send_button_selector_candidates"] = send_found
    logger.info(f"[auto_extract_chat_selectors] send_found: {send_found}")

    # 新建对话按钮区域
    new_chat_candidates = [
        "button:has-text('New chat')",
        "button[data-testid='new-chat']",
        "a:has-text('New chat')",
        "a[data-testid='new-chat']",
    ]
    new_chat_found = []
    for sel in new_chat_candidates:
        try:
            el = page.locator(sel).first
            if await el.is_visible():
                new_chat_found.append(sel)
        except Exception:
            continue
    if new_chat_found:
        selectors["new_chat_selector"] = new_chat_found[0]
        selectors["new_chat_selector_candidates"] = new_chat_found


    # 回复区域（assistant/message/reply）增强：优先检测 .ds-message 结构
    reply_candidates = [
        "[data-testid='assistant-message']",
        "div.message.assistant",
        "article[data-role='assistant']",
        ".message, .response, .chat-message",
        "div[role='log']",
        "div[aria-live]",
        "article",
        ".ds-message .ds-markdown-paragraph",
        ".ds-message:last-of-type .ds-markdown-paragraph",
        "div.ds-message:last-of-type div.ds-markdown > p.ds-markdown-paragraph",
        "p.ds-markdown-paragraph",
        "p[class*='markdown']",
    ]
    reply_found = []
    best_selector = None
    best_text = ""
    # 优先检测唯一结构
    try:
        msg_count = await page.locator('.ds-message').count()
        if msg_count > 0:
            # 检查 .ds-message:last-of-type .ds-markdown-paragraph 是否可见且有内容
            el = page.locator('.ds-message:last-of-type .ds-markdown-paragraph')
            if await el.first.is_visible():
                texts = await el.all_inner_texts()
                text = "\n".join([t for t in texts if t.strip()])
                if text:
                    selectors["reply_selector"] = ".ds-message:last-of-type .ds-markdown-paragraph"
                    reply_found.append(".ds-message:last-of-type .ds-markdown-paragraph")
                    # 兼容其它候选
                    if await page.locator('.ds-message .ds-markdown-paragraph').first.is_visible():
                        reply_found.append('.ds-message .ds-markdown-paragraph')
                    if await page.locator('div.ds-message:last-of-type div.ds-markdown > p.ds-markdown-paragraph').first.is_visible():
                        reply_found.append('div.ds-message:last-of-type div.ds-markdown > p.ds-markdown-paragraph')
                    # 兼容原有
                    if await page.locator('p.ds-markdown-paragraph').first.is_visible():
                        reply_found.append('p.ds-markdown-paragraph')
                    if await page.locator('p[class*="markdown"]').first.is_visible():
                        reply_found.append('p[class*="markdown"]')
                    selectors["reply_selector_candidates"] = reply_found
                    logger.info(f"[auto_extract_chat_selectors] reply_found: {reply_found}")
                    return selectors
    except Exception:
        pass
    # 回退原有逻辑
    for sel in reply_candidates:
        try:
            el = page.locator(sel)
            if await el.first.is_visible():
                texts = await el.all_inner_texts()
                text = "\n".join([t for t in texts if t.strip()])
                if text:
                    reply_found.append(sel)
                if text and len(text) > len(best_text):
                    best_selector = sel
                    best_text = text
        except Exception:
            continue
    if best_selector:
        selectors["reply_selector"] = best_selector
    if reply_found:
        selectors["reply_selector_candidates"] = reply_found
    logger.info(f"[auto_extract_chat_selectors] reply_found: {reply_found}")

    logger.info(f"[auto_extract_chat_selectors] provider={provider} session_id={session_id} 提取结果: {selectors}")
    return selectors





@dataclass
class ProcessResult:
    ok: bool
    raw_response: str | None = None
    error_message: str | None = None
    permanent_failure: bool = False


class TaskProcessor(Protocol):
    async def process(self, decision: DispatchDecision) -> ProcessResult:
        raise NotImplementedError


class MockTaskProcessor:
    async def process(self, decision: DispatchDecision) -> ProcessResult:
        _ = decision
        await asyncio.sleep(0.01)
        return ProcessResult(ok=True)


class PooledProviderTaskProcessor:
    async def process(self, decision: DispatchDecision) -> ProcessResult:
        """
        Provider 任务处理主流程：
        1. 获取/激活 session/page
        2. 调用 self.adapter 执行任务
        3. 处理响应，返回 ProcessResult
        """
        try:
            # 1. 获取/激活页面
            page = await get_or_create_provider_session(
                decision.provider,
                decision.session_id,
                getattr(decision, 'chat_url', None)
            )
            # 2. 调用 provider adapter 执行任务（如发送 prompt）
            # 假设 adapter.run 返回对象含 ok/raw_response/error_message 字段
            result = await self.adapter.run(page, decision)
            # 3. 标准化返回
            return ProcessResult(
                ok=getattr(result, 'ok', True),
                raw_response=getattr(result, 'raw_response', None),
                error_message=getattr(result, 'error_message', None)
            )
        except Exception as exc:
            logger.exception("provider process error: %s", exc)
            return ProcessResult(ok=False, error_message=str(exc))
    def __init__(
        self,
        *,
        provider: str,
        adapter: ProviderAdapter,
        session_repo: SessionRepository | None = None,
        task_repo: TaskRepository | None = None,
        session_pool: object | None = None,
        timeout_ms: int = 60000,
        headless: bool | None = None,
        idle_sleep_seconds: float = 1.0,
    ) -> None:
        self.provider = provider
        self.session_repo = session_repo or SessionRepository()
        self.task_repo = task_repo or TaskRepository()
        self.adapter = adapter
        self.timeout_ms = timeout_ms
        self.session_pool = session_pool
        self.idle_sleep_seconds = idle_sleep_seconds
        # 修复：初始化调度器
        from src.browser.scheduler import WeightedRoundRobinScheduler
        self.scheduler = WeightedRoundRobinScheduler()
        self.log_repo = LogRepository()
        self.processor = self  # Self-reference for task processing

    async def run_once(self) -> bool:
        """
        Command queue + task polling loop for this provider thread.
        """
        try:
            import threading
            current_thread_id = str(threading.get_ident())
            cmd = get_command_for_thread(current_thread_id)
            if cmd:
                await self._handle_command(cmd)
                return True
        except Exception as exc:
            logger.error(f"Command handling failed in {self.provider}: {exc}")

        # 自动拉取并处理任务（只允许 owner==当前线程的任务被领取和处理）
        import threading
        current_thread_id = str(threading.get_ident())
        while True:
            task = self.task_repo.claim_next_pending(owner=current_thread_id)
            if not task:
                break
            logger.info(f"[worker] 领取任务: id={task.id} provider={task.provider} session_id={task.session_id} owner={task.owner} 当前线程={current_thread_id}")
            decision = DispatchDecision(
                provider=task.provider,
                session_id=task.session_id,
                prompt=task.prompt_text,
                document_text=task.document_text,
                task_id=task.id,
                attempt_id=0,
                attempt_no=0,
                dispatched_at=datetime.now(UTC),
            )
            result = await self.process(decision)
            # 结果入库与状态更新
            if result.ok:
                if result.raw_response:
                    self.task_repo.save_raw_response(task.id, task.provider, result.raw_response)
                self.task_repo.mark_status(task.id, TaskStatus.COMPLETED)
                logger.info(f"[worker] get  reply: id={task.id} reply={result.raw_response}")
            else:
                self.task_repo.mark_status(task.id, TaskStatus.FAILED)
                logger.info(f"[worker] 任务处理完成: id={task.id} status={'COMPLETED' if result.ok else 'FAILED'} error={result.error_message}")
            break

        await asyncio.sleep(self.idle_sleep_seconds)
        return True
    
    async def _handle_command(self, cmd):
        if cmd.command_type == "verify_session":
            page = await get_or_create_provider_session(
                self.provider,
                cmd.params["session_id"],
                cmd.params["url"]
            )
            if hasattr(page, "is_closed") and page.is_closed():
                put_command_result(WorkerCommandResult(
                    command_id=cmd.command_id,
                    status="error",
                    error_message="Page closed"
                ))
            else:
                put_command_result(WorkerCommandResult(
                    command_id=cmd.command_id,
                    status="success",
                    result={"ready": True}
                ))
        elif cmd.command_type == "mark_login_ok":
            # 检测页面 ready 并提取 selectors
            import traceback
            logger.info(f"[mark_login_ok] worker收到命令: provider={self.provider} session_id={cmd.params['session_id']} thread_id={getattr(self, 'thread_id', None)}")
            try:
                selectors = await auto_extract_chat_selectors(
                    self.provider,
                    cmd.params["session_id"],
                    self.session_pool,
                    logger=logger
                )
                logger.info(f"[mark_login_ok] selectors 提取结果: {selectors}")
                # 增量合并 ready_selectors_json，未采集到的 selector 字段保留原值
                repo = ProviderConfigRepository()
                old_row = repo.get(self.provider)
                import json
                old_selectors = {}
                if old_row and old_row.ready_selectors_json:
                    try:
                        old_selectors = json.loads(old_row.ready_selectors_json)
                    except Exception:
                        old_selectors = {}
                merged = dict(old_selectors)
                for k, v in selectors.items():
                    if v:
                        merged[k] = v
                logger.info(f"[mark_login_ok] update_ready_selectors 调用: provider={self.provider} merged_selectors={merged}")
                try:
                    repo.update_ready_selectors(self.provider, merged)
                    logger.info(f"[mark_login_ok] update_ready_selectors 成功: provider={self.provider}")
                except Exception as db_exc:
                    logger.error(f"[mark_login_ok] update_ready_selectors 异常: {db_exc}\n{traceback.format_exc()}")
                    # 继续返回 success，人工兜底
                # 只要用户点击“标记就绪”，都返回 success，ready 字段仅供参考
                ready = bool(selectors.get("input_selector") and selectors.get("send_button_selector") and selectors.get("reply_selector"))
                missing = []
                for k in ("input_selector", "send_button_selector", "reply_selector"):
                    if not selectors.get(k):
                        missing.append(k)
                put_command_result(WorkerCommandResult(
                    command_id=cmd.command_id,
                    status="success",
                    result={
                        "ready": ready,
                        "selectors": selectors,
                        "missing": missing,
                        "msg": "login confirmed (manual override, see missing)" if missing else "login confirmed"
                    },
                    error_message=None
                ))
            except Exception as exc:
                logger.error(f"[mark_login_ok] selector extract failed: {exc}\n{traceback.format_exc()}")
                put_command_result(WorkerCommandResult(
                    command_id=cmd.command_id,
                    status="success",
                    result={"ready": False, "msg": str(exc), "selectors": {}, "missing": ["exception"]},
                    error_message=None
                ))
    
    async def _inspect_adapter_page_state(self, page: object) -> Optional[object]:
        inspect_fn = getattr(self.adapter, "inspect_page_state", None)
        if callable(inspect_fn):
            try:
                return await inspect_fn(page)
            except Exception:
                logger.debug("Adapter inspect failed")
        return None


 
class MultiProviderTaskProcessor:
    def __init__(
        self,
        processors: dict[str, TaskProcessor] | None = None,
        pool_manager: object | None = None,
        session_repo: SessionRepository | None = None,
        task_repo: TaskRepository | None = None,
        timeout_ms: int = 60000,
        headless: bool | None = None,
        session_pool: object | None = None,
    ) -> None:
        if headless is None:
            is_headless = getenv("WORKER_HEADLESS", "1") == "1"
        else:
            is_headless = headless

        self.session_pool = session_pool or get_global_provider_session_pool()
        self.pool_manager = None  # 兼容保留
        self.session_repo = session_repo or SessionRepository()
        self.task_repo = task_repo or TaskRepository()

        from src.browser.providers.base import DefaultProviderAdapter
        def provider_adapter_factory(provider_name: str) -> ProviderAdapter:
            # 统一返回 DefaultProviderAdapter，传递 provider_name，便于 selector fallback 和日志
            return DefaultProviderAdapter(provider_name)

        if processors is not None:
            self.processors = processors
            return

        # 动态注册所有 provider
        provider_repo = ProviderConfigRepository()
        provider_configs = provider_repo.list()
        self.processors = {}
        for provider in provider_configs:
            name = provider.name
            adapter = provider_adapter_factory(name)
            # 优先传递全局 session_pool
            self.processors[name] = PooledProviderTaskProcessor(
                provider=name,
                adapter=adapter,
                session_repo=self.session_repo,
                task_repo=self.task_repo,
                session_pool=session_pool or self.pool_manager.get_pool(name),
                timeout_ms=timeout_ms,
                headless=is_headless,
            )

    async def process(self, decision: DispatchDecision) -> ProcessResult:
        processor = self.processors.get(decision.provider)
        if processor is None:
            return ProcessResult(
                ok=False,
                error_message=f"unsupported provider: {decision.provider}",
                permanent_failure=True,
            )
        return await processor.process(decision)

    async def close(self) -> None:
        for processor in self.processors.values():
            close_fn = getattr(processor, "close", None)
            if callable(close_fn):
                maybe_awaitable = close_fn()
                if asyncio.iscoroutine(maybe_awaitable):
                    await maybe_awaitable




# 线程池管理，每线程独占会话

# 每个 provider 只分配一个线程，所有该 provider 的任务都分配到同一线程，避免同 provider 多窗口
class ThreadedWorkerManager:
    def __init__(self, providers: list[str]):
        self.providers = set(providers)
        self.executor = ThreadPoolExecutor(max_workers=len(providers))
        self.thread_local = threading.local()
        # provider -> threading.Lock，保证同一 provider 的任务串行
        self.provider_locks: dict[str, threading.Lock] = {p: threading.Lock() for p in providers}
        # provider -> future，便于管理线程生命周期
        self.provider_futures: dict[str, object] = {}

    def add_provider(self, provider: str):
        if provider in self.providers:
            return
        self.providers.add(provider)
        self.provider_locks[provider] = threading.Lock()
        # 可根据实际业务创建新线程或扩展线程池
        # 注意：ThreadPoolExecutor 无法动态扩容 max_workers，需重启或用更灵活的池

    def remove_provider(self, provider: str):
        if provider not in self.providers:
            return
        self.providers.remove(provider)
        self.provider_locks.pop(provider, None)
        # 停止相关线程（如有 future，可取消）
        fut = self.provider_futures.pop(provider, None)
        if fut is not None:
            try:
                fut.cancel()
            except Exception:
                pass

    def restart_provider(self, provider: str):
        self.remove_provider(provider)
        self.add_provider(provider)
        # 可补充重启逻辑，如重新提交任务等

    def submit_task(self, session_id, url, provider, task_fn, *args, **kwargs):
        lock = self.provider_locks[provider]
        def thread_task(*args, **kwargs):
            with lock:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                from src.browser.session_manager import session_manager
                page = session_manager.get_or_create(session_id, provider, url, threading.get_ident())
                self.thread_local.page = page
                return task_fn(page, *args, **kwargs)
        fut = self.executor.submit(thread_task, *args, **kwargs)
        self.provider_futures[provider] = fut
        return fut

# 示例：任务函数
def example_task(page, *args, **kwargs):
    # 只操作本线程的 page
    # ...业务逻辑...
    return True

# 新增：发现真实浏览器会话（页面对象）
async def discover_real_sessions() -> list:
    """
    只发现真实浏览器页面对象，返回所有活跃 session 信息。
    """
    from src.browser.session_pool import get_global_provider_session_pool
    pool = get_global_provider_session_pool()
    sessions = []
    for key, entry in getattr(pool, '_entries', {}).items():
        page = getattr(entry, 'page', None)
        if page is not None:
            sessions.append({
                'session_key': key,
                'page': page,
                'url': getattr(entry, 'url', None),
                'provider': key.split(':')[0] if ':' in key else None,
            })
    return sessions

# 新增：发现并拉起所有 provider 的 chat 页面（仅在无页面时才拉起）
async def discover_and_launch_sessions() -> list:
    """
    遍历所有 provider 的 session：
    - 已有页面时，检测页面是否处于READY（可chat）状态，并返回该状态。
    - 只有在找不到页面的情况下才调用 get_page(headless=False) 拉起 chat 页面。
    返回所有 session 信息（含页面对象和 ready 状态）。
    """
    from src.browser.session_pool import get_global_provider_session_pool
    from src.storage.repositories import SessionRepository
    pool = get_global_provider_session_pool()
    session_repo = SessionRepository()
    sessions = []
    entries = getattr(pool, '_entries', {})
    # READY 检查逻辑：检测页面是否可用（如 chat input 存在且可用）
    async def is_page_ready(page) -> bool:
        try:
            # 以常见 chat input selector 检查页面可用性
            selectors = [
                "textarea[data-testid='chat-input']",
                "textarea[placeholder*='message' i]",
                "div[contenteditable='true']",
                "textarea",
                "input[type='text']",
                "[contenteditable='true']",
                "textarea[aria-label]",
                "input[aria-label]",
            ]
            for sel in selectors:
                el = page.locator(sel).first
                if await el.is_visible() and await el.is_enabled():
                    return True
        except Exception:
            pass
        return False

    
    
    for row in session_repo.list():
        key = f"{row.provider}:{row.id}"
        entry = entries.get(key)
        page = getattr(entry, 'page', None) if entry else None
        logger.info(f"[discover_and_launch_sessions] session_id={row.id} provider={row.provider} chat_url={row.chat_url} entry_exists={bool(entry)} page_exists={page is not None}")
        if page is not None:
            # 已有页面，检测是否READY
            ready = await is_page_ready(page)
            logger.info(f"[discover_and_launch_sessions] session_id={row.id} provider={row.provider} page already exists, ready={ready}")
            sessions.append({
                'session_id': row.id,
                'provider': row.provider,
                'url': row.chat_url,
                'page': page,
                'launched': False,
                'ready': ready,
            })
        else:
            # 没有页面，拉起
            try:
                logger.info(f"[discover_and_launch_sessions] launching new page: session_id={row.id} provider={row.provider} url={row.chat_url}")
                page = await pool.get_page(
                    session_id=row.id,
                    url=row.chat_url,
                    provider=row.provider
                )
                ready = await is_page_ready(page)
                logger.info(f"[discover_and_launch_sessions] launched new page: session_id={row.id} provider={row.provider} ready={ready} page={page}")
                sessions.append({
                    'session_id': row.id,
                    'provider': row.provider,
                    'url': row.chat_url,
                    'page': page,
                    'launched': True,
                    'ready': ready,
                })
            except Exception as exc:
                logger.error(f"[discover_and_launch_sessions] failed to launch page: session_id={row.id} provider={row.provider} error={exc}")
                sessions.append({
                    'session_id': row.id,
                    'provider': row.provider,
                    'url': row.chat_url,
                    'page': None,
                    'launched': False,
                    'ready': False,
                    'error': str(exc),
                })
    return sessions


if __name__ == "__main__":
    logger.info(f'logger_test')