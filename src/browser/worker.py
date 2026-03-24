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

def start_worker_thread(provider: str, logger=None) -> '__import__("threading").Thread':
    """
    启动单个 provider 的 worker 线程
    """
    import threading
    import asyncio
    from src.browser.session_pool import get_global_provider_session_pool, get_or_create_provider_session
    from src.browser.providers.base import DefaultProviderAdapter
    from src.storage.repositories import SessionRepository, TaskRepository
    from sqlalchemy import select
    from src.storage.database import ProviderConfigORM, session_scope
    
    def worker_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        pool = get_global_provider_session_pool()
        session_repo = SessionRepository()
        task_repo = TaskRepository()
        adapter = DefaultProviderAdapter(provider)
        with session_scope() as session:
            provider_row = session.execute(select(ProviderConfigORM).where(ProviderConfigORM.name == provider)).scalars().first()
            chat_url = provider_row.url if provider_row and provider_row.url else "about:blank"
        session_id = f"s-{provider}-1"
        owner = str(threading.get_ident())
        if logger:
            logger.info(f"[worker] 启动线程: provider={provider} thread_id={owner} pid={os.getpid()} url={chat_url}")
        print(f"[worker-thread-debug] provider={provider} thread_id={owner} pid={os.getpid()} url={chat_url}")
        
        # 延迟导入，避免循环依赖
        from src.browser.worker import PooledProviderTaskProcessor
        processor = PooledProviderTaskProcessor(
            provider=provider,
            adapter=adapter,
            session_repo=session_repo,
            task_repo=task_repo,
            session_pool=pool,
        )
        async def run():
            await session_manager.get_or_create(session_id, provider, chat_url, owner)
            await get_or_create_provider_session(provider, session_id, chat_url)
            try:
                while True:
                    active = await processor.run_once()
                    if not active:
                        await asyncio.sleep(0.5)
            except StopWorkerException:
                if logger:
                    logger.info(f"[worker] provider {provider} 收到中止指令，退出后台循环。")
            finally:
                if logger:
                    logger.info(f"[worker] provider {provider} 进入清理流程 (finally)...")
                try:
                    await pool.close_provider_session(provider)
                    if logger:
                        logger.info(f"[worker] provider {provider} 成功清理 session 资源。")
                except Exception as exc:
                    if logger:
                        logger.error(f"[worker] provider {provider} 清理 session 异常: {exc}", exc_info=True)
        loop.run_until_complete(run())

    t = threading.Thread(target=worker_thread, name=f"WorkerThread-{provider}", daemon=True)
    t.start()
    return t


def start_all_worker_threads(logger=None):
    """
    启动所有 provider 的 worker 线程。主入口由 main.py 调用。
    """
    from sqlalchemy import select
    from src.storage.database import ProviderConfigORM, session_scope

    with session_scope() as session:
        provider_rows = session.execute(select(ProviderConfigORM)).scalars().all()
        providers = sorted(set(row.name for row in provider_rows if row.name and row.enable))
        
    if not providers:
        if logger:
            logger.warning("[worker] 未检测到任何 provider，会跳过 worker 线程启动。请先初始化 provider_configs 表。")
        return

    threads = []
    for provider in providers:
        t = start_worker_thread(provider, logger)
        threads.append(t)
    return threads


class StopWorkerException(Exception):
    pass


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



async def _llm_extract_selectors(dom_phase_1: str, dom_phase_2: str, expected_fields: list, current_provider: str, logger=None) -> dict:
    from src.storage.repositories import TaskRepository
    from src.models.task import TaskCreate, TaskStatus
    from src.parser.response_extractor import ResponseExtractor
    from src.browser.session_pool import get_global_provider_session_pool
    import asyncio
    import time

    task_repo = TaskRepository()
    pool = get_global_provider_session_pool()
    
    # 获取当前 READY 状态的 provider entry，优先选择 locked=true 的其他 provider
    available_entries = []
    for e in pool._entries.values():
        if e.provider == current_provider:
            continue
        try:
            if not e.page.is_closed():
                available_entries.append(e)
        except Exception:
            continue
    
    # 优先选取 locked 的 provider
    ready_entry = next((e for e in available_entries if e.lock), None)
    if not ready_entry:
        # 其次选择任意 READY 的
        ready_entry = next(iter(available_entries), None)
        
    if not ready_entry:
        # 严格按照需求 4：如果没有其他的locked provider，可由自己所在的线程识别。
        self_entry = pool._entries.get(current_provider)
        if self_entry:
            try:
                if not self_entry.page.is_closed():
                    ready_entry = self_entry
                    if logger:
                        logger.info(f"[_llm_extract_selectors] No other READY helper found. Using self ({current_provider}) for extraction.")
            except Exception:
                pass

    if not ready_entry:
        if logger:
            logger.warning(f"[_llm_extract_selectors] No READY provider found to help extraction for {current_provider}")
        return {}

    prompt = f"""# Role: AI Chat Scraper Expert
# Task: Identify CSS selectors using two DOM snapshots from different states.

# State Description:
- Phase 1: Captured AFTER typing "hello" into the input. Use this to find the input box and send button.
- Phase 2: Captured AFTER clicking send/pressing enter. Use this to find the reply container (where "hello" response appears).

# Target Elements:
1. 'new_chat_selector': Button/link to start a new chat.
2. 'input_selector': Text field or contenteditable div for typing messages.
3. 'send_button_selector': The submit/send button.
4. 'reply_selector': The container for the AI assistant's responses (e.g. '.ds-markdown', 'model-response .response-container-content').

# Output Requirements:
- Return ONLY valid JSON.
- Use "" if not found.
- For each field, provide the single most specific and reliable CSS selector.
- Ensure selectors are specific for Playwright (CSS or Playwright pseudo-selectors).
- MODERN APPS: The page may use Web Components and Shadow DOM (represented as <shadow-root> in the provided DOM). Selectors should target the deepest identifiable element.

# Output JSON Template:
{{
  "new_chat_selector": "",
  "input_selector": "",
  "send_button_selector": "",
  "reply_selector": ""
}}

# DOM Phase 1:
{dom_phase_1}

# DOM Phase 2:
{dom_phase_2}
"""

    # 创建内部任务
    try:
        payload = TaskCreate(
            prompt=prompt,
            document_text="INTERNAL_DOM_ANALYSIS_DUAL_PHASE",
            owner=str(ready_entry.thread_id),
            session_id=ready_entry.session_id,
            provider=ready_entry.provider
        )
        task_row = task_repo.create(payload)
        task_id = task_row.id
        if logger:
            logger.info(f"[_llm_extract_selectors] Created internal dual-phase task {task_id} assigned to {ready_entry.provider}")
        
        # 轮询状态
        timeout = 60
        start_t = time.time()
        while time.time() - start_t < timeout:
            row = task_repo.get(task_id)
            if row.status == TaskStatus.COMPLETED:
                raw_row = task_repo.get_latest_raw_response(task_id)
                if raw_row and raw_row.response_text:
                    extractor = ResponseExtractor()
                    res = extractor.extract_json_candidate(raw_row.response_text)
                    if logger:
                        logger.info(f"[_llm_extract_selectors] Task {task_id} completed. Extracted: {res}")
                    return res or {}
                break
            elif row.status in (TaskStatus.FAILED, TaskStatus.CRITICAL):
                if logger:
                    logger.error(f"[_llm_extract_selectors] Internal task {task_id} failed with status {row.status}")
                break
            await asyncio.sleep(1)
        
        if logger:
            logger.warning(f"[_llm_extract_selectors] Internal task {task_id} timed out.")
    except Exception as e:
        if logger:
            logger.exception(f"[_llm_extract_selectors] Failed to create or wait for internal task: {e}")
    
    return {}


async def auto_extract_chat_selectors(provider: str, session_id: str, session_pool, logger=None) -> dict:
    """
    自动提取 chat 页面 input/send/response selector，供 API 填充 provider_configs。
    尝试发送 'hello' 并提取精简版 DOM，交由 LLM 识别。
    """
    if logger is None:
        import logging
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
    
    # 启发式提取输入框和发送按钮
    input_candidates = [
        "textarea[placeholder='Message DeepSeek']", "textarea[data-testid='chat-input']",
        "textarea[placeholder*='message' i]", "div[contenteditable='true']",
        "textarea", "input[type='text']", "[contenteditable='true']",
        "textarea[aria-label]", "input[aria-label]"
    ]
    input_sel = None
    for sel in input_candidates:
        try:
            if await page.locator(sel).first.is_visible():
                input_sel = sel
                break
        except Exception: pass

    send_candidates = [
        "button[data-testid='send-button']", "button[aria-label*='send' i]",
        "button[aria-label*='发送' i]", "button:has-text('Send')", "button:has-text('发送')", 
        "button[type='submit']", "div[role='button'].ds-icon-button", 
        "div.ds-icon-button[role='button']", "div[role='button']"
    ]
    send_sel = None

    # 获取 DOM 精简样本脚本
    dom_script = """
        () => {
            function isVisible(el) {
                if (el.nodeType !== Node.ELEMENT_NODE) return true;
                if (!el.getBoundingClientRect) return true;
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && style.visibility !== 'hidden' && (el.offsetWidth > 0 || el.tagName.includes('-'));
            }

            function cleanNode(node) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    const tag = node.tagName.toLowerCase();
                    const junkTags = ['script', 'style', 'svg', 'path', 'img', 'noscript', 'meta', 'link', 'iframe', 'canvas', 'video', 'audio'];
                    if (junkTags.includes(tag)) return null;
                    if (!isVisible(node) && !['input', 'textarea', 'button'].includes(tag)) return null;

                    const newNode = document.createElement(tag);
                    const keepAttrs = ['id', 'class', 'placeholder', 'aria-label', 'data-testid', 'href', 'title', 'role', 'name'];
                    for (let i = 0; i < node.attributes.length; i++) {
                        const attr = node.attributes[i];
                        if (keepAttrs.includes(attr.name)) {
                            let val = attr.value;
                            if (val.length > 40) val = val.substring(0, 40) + '...';
                            newNode.setAttribute(attr.name, val);
                        }
                    }
                    
                    // Special handling for input/textarea values
                    if (tag === 'textarea' || tag === 'input') {
                        let val = node.value || "";
                        if (val) {
                            if (val.length > 50) val = val.substring(0, 50) + '...';
                            newNode.setAttribute('value_content', val);
                        }
                    }

                    let hasContent = false;
                    for (let i = 0; i < node.childNodes.length; i++) {
                        const cleaned = cleanNode(node.childNodes[i]);
                        if (cleaned) {
                            newNode.appendChild(cleaned);
                            hasContent = true;
                        }
                    }
                    
                    if (node.shadowRoot) {
                        const shadowContainer = document.createElement('shadow-root');
                        let hasShadowContent = false;
                        for (let i = 0; i < node.shadowRoot.childNodes.length; i++) {
                            const cleaned = cleanNode(node.shadowRoot.childNodes[i]);
                            if (cleaned) {
                                shadowContainer.appendChild(cleaned);
                                hasShadowContent = true;
                                hasContent = true;
                            }
                        }
                        if (hasShadowContent) newNode.appendChild(shadowContainer);
                    }

                    const interactiveTags = ['input', 'textarea', 'button', 'a'];
                    const isContentEditable = node.hasAttribute('contenteditable') && node.getAttribute('contenteditable') !== 'false';
                    const isRoleButton = node.getAttribute('role') === 'button';
                    const ariaLabel = (node.getAttribute('aria-label') || '').toLowerCase();
                    const isPotentialSend = ariaLabel.includes('send') || ariaLabel.includes('发送');
                    
                    if (!hasContent && !interactiveTags.includes(tag) && !isContentEditable && !isRoleButton && !isPotentialSend && !node.innerText.trim()) {
                        return null;
                    }
                    return newNode;
                } else if (node.nodeType === Node.TEXT_NODE) {
                    const text = node.textContent.trim();
                    if (text.length > 0) {
                        return document.createTextNode(text.length > 80 ? text.substring(0, 80) + '...' : text);
                    }
                }
                return null;
            }

            const cleanedBody = cleanNode(document.body);
            return cleanedBody ? cleanedBody.innerHTML : "<body></body>";
        }
    """

    async def capture_minified_dom():
        try:
            res = await page.evaluate(dom_script)
            # 限制单次 DOM 长度，防止 token 溢出 (约 35k chars)
            if res and len(res) > 35000:
                return res[:35000] + "...(truncated)"
            return res
        except Exception as e:
            logger.warning(f"[auto_extract_chat_selectors] DOM capture failed: {e}")
            return ""

    dom_phase_1 = ""
    dom_phase_2 = ""

    if input_sel:
        selectors["input_selector"] = input_sel
        try:
            # 输入 hello
            await page.locator(input_sel).first.click()
            await page.locator(input_sel).first.type("hello", delay=50)
            await page.wait_for_timeout(2000) # 等待 UI 响应（如发送按钮出现）
            
            # 捕获阶段 1：打字后，发送前
            dom_phase_1 = await capture_minified_dom()
            
            if send_sel or (send_candidates and len(send_candidates) > 0):
                # 重新寻找最新的发送按钮
                found_send = None
                for sel in send_candidates:
                    try:
                        if await page.locator(sel).first.is_visible():
                            found_send = sel
                            break
                    except Exception:
                        continue
                
                if found_send:
                    selectors["send_button_selector"] = found_send
                    logger.info(f"[auto_extract_chat_selectors] Clicking send button: {found_send}")
                    try:
                        await page.locator(found_send).first.click()
                        await page.wait_for_timeout(1000)
                    except Exception as e:
                        logger.warning(f"[auto_extract_chat_selectors] Click send button failed: {e}")
                    
                # 检查输入框是否清空，若未清空则兜底回车
                try:
                    curr_val = await page.locator(input_sel).first.evaluate("el => el.value || el.innerText")
                    if curr_val.strip():
                        logger.info("[auto_extract_chat_selectors] Input not cleared, trying Enter/Ctrl+Enter...")
                        await page.locator(input_sel).first.focus()
                        await page.keyboard.press("Control+Enter")
                        await page.wait_for_timeout(500)
                        await page.keyboard.press("Enter")
                except Exception:
                    pass
            else:
                # 只有输入框，直接回车
                logger.info("[auto_extract_chat_selectors] No send button found, trying Enter...")
                try:
                    await page.locator(input_sel).first.focus()
                    await page.keyboard.press("Enter")
                except Exception:
                    pass
            
            logger.info("[auto_extract_chat_selectors] 等待响应加载 (5s)...")
            await page.wait_for_timeout(5000)
            
            # 捕获阶段 2：发送后，应包含回复
            dom_phase_2 = await capture_minified_dom()
            
        except Exception as e:
            logger.warning(f"[auto_extract_chat_selectors] 向页面发送 hello 失败: {e}")
            if not dom_phase_1:
                dom_phase_1 = await capture_minified_dom()
    else:
        # 如果没找到输入框，直接抓取一次当前 DOM
        dom_phase_1 = await capture_minified_dom()

    # 将合并后的 DOM 样本存入结果（仅用于展示在 Admin UI）
    selectors["dom_sample"] = f"--- PHASE 1 (Typed) ---\n{dom_phase_1}\n\n--- PHASE 2 (Replied) ---\n{dom_phase_2}"

    # 调用 LLM 进一步提取
    if dom_phase_1 or dom_phase_2:
        llm_selectors = await _llm_extract_selectors(dom_phase_1, dom_phase_2, ["new_chat_selector", "input_selector", "send_button_selector", "reply_selector"], provider, logger)
        if llm_selectors:
            for k in ["new_chat_selector", "input_selector", "send_button_selector", "reply_selector"]:
                if llm_selectors.get(k):
                    selectors[k] = llm_selectors[k]
                    
    # 如果 LLM 未返回 input/send，保留启发式结果
    if input_sel and not selectors.get("input_selector"):
        selectors["input_selector"] = input_sel
    if send_sel and not selectors.get("send_button_selector"):
        selectors["send_button_selector"] = send_sel
    
    # 最后兜底 reply area 的启发式（如果 LLM 失败）
    if not selectors.get("reply_selector"):
        reply_candidates = [
            ".ds-message:last-of-type .ds-markdown", "div.message.assistant",
            "article[data-role='assistant']", ".message, .response, .chat-message",
            "p.ds-markdown"
        ]
        for sel in reply_candidates:
            try:
                if await page.locator(sel).first.count() > 0:
                    selectors["reply_selector"] = sel
                    break
            except Exception: pass

    logger.info(f"[auto_extract_chat_selectors] Final selectors extracted: {{k: selectors[k] for k in selectors if k != 'dom_sample'}}")
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
        except StopWorkerException:
            raise
        except Exception as exc:
            logger.error(f"Command handling failed in {self.provider}: {exc}")

        # 自动拉取并处理任务（只允许 owner==当前线程的任务被领取和处理）
        import threading
        current_thread_id = str(threading.get_ident())
        while True:
            task = self.task_repo.claim_next_pending(owner=current_thread_id)
            if not task:
                return False
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
                
                # --- Auto-Reset Check ---
                self.session_repo.increment_chat_rounds(task.session_id)
                session_obj = self.session_repo.get(task.session_id)
                from src.storage.repositories import AppParamRepository
                app_param = AppParamRepository().get()
                max_rounds = app_param.max_chat_rounds
                
                if max_rounds > 0 and session_obj and session_obj.chat_rounds >= max_rounds:
                    logger.info(f"[worker] session {task.session_id} 达到最大轮数 {max_rounds}，准备重置对话")
                    try:
                        page = await get_or_create_provider_session(
                            decision.provider, decision.session_id, getattr(decision, 'chat_url', None)
                        )
                        from src.storage.repositories import ProviderConfigRepository
                        import json
                        provider_row = ProviderConfigRepository().get(decision.provider)
                        if provider_row and provider_row.ready_selectors_json:
                            selectors = json.loads(provider_row.ready_selectors_json)
                            if selectors.get("new_chat_selector"):
                                await page.click(selectors["new_chat_selector"], timeout=5000)
                                logger.info(f"[worker] 成功点击 'New chat' 按钮重置对话: {task.session_id}")
                                await asyncio.sleep(2)  # 给页面一点响应和加载时间
                    except Exception as reset_exc:
                        logger.warning(f"[worker] 重置对话失败: {reset_exc}")
                    finally:
                        self.session_repo.reset_chat_rounds(task.session_id)

            else:
                self.task_repo.mark_status(task.id, TaskStatus.FAILED)
                logger.info(f"[worker] 任务处理完成: id={task.id} status={'COMPLETED' if result.ok else 'FAILED'} error={result.error_message}")
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
        elif cmd.command_type == "stop_thread":
            logger.info(f"Stopping worker thread for provider {self.provider}")
            raise StopWorkerException()
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
                # 采用新独立字段体系保存 selectors
                repo = ProviderConfigRepository()
                logger.info(f"[mark_login_ok] update_selectors 调用: provider={self.provider}")
                try:
                    repo.update_selectors(
                        self.provider,
                        new_chat_selector=selectors.get("new_chat_selector"),
                        input_selector=selectors.get("input_selector"),
                        send_button_selector=selectors.get("send_button_selector"),
                        reply_selector=selectors.get("reply_selector"),
                        dom_sample=selectors.get("dom_sample")
                    )
                    logger.info(f"[mark_login_ok] update_selectors 成功: provider={self.provider}")
                except Exception as db_exc:
                    logger.error(f"[mark_login_ok] update_selectors 异常: {db_exc}\\n{traceback.format_exc()}")
                
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
                page = loop.run_until_complete(
                    session_manager.get_or_create(session_id, provider, url, threading.get_ident())
                )
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