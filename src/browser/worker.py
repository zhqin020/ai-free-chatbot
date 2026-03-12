from __future__ import annotations

import asyncio
from dataclasses import dataclass
from os import getenv
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from src.browser.providers import (
    DeepSeekAdapter,
    GeminiAdapter,
    GrokAdapter,
    OpenChatAdapter,
    ProviderAdapter,
)
from src.browser.scheduler import DispatchDecision, WeightedRoundRobinScheduler
from src.browser.session_pool import BrowserSessionPool, ProviderSessionPoolManager
from src.models.session import Provider, SessionState
from src.models.task import TaskStatus
from src.parser import JSONValidator, ResponseExtractor, RetryHandler
from src.prompt import PromptGenerator
from src.storage.repositories import LogRepository, SessionRepository, TaskRepository


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
    def __init__(
        self,
        *,
        provider: Provider,
        adapter: ProviderAdapter,
        session_repo: SessionRepository | None = None,
        task_repo: TaskRepository | None = None,
        session_pool: BrowserSessionPool | None = None,
        timeout_ms: int = 60000,
        headless: bool | None = None,
    ) -> None:
        self.provider = provider
        self.session_repo = session_repo or SessionRepository()
        self.task_repo = task_repo or TaskRepository()
        self.adapter = adapter
        self.timeout_ms = timeout_ms
        if headless is None:
            self.headless = getenv("WORKER_HEADLESS", "1") == "1"
        else:
            self.headless = headless
        self.session_pool = session_pool or BrowserSessionPool(headless=self.headless)

    async def process(self, decision: DispatchDecision) -> ProcessResult:
        if decision.provider != self.provider:
            return ProcessResult(
                ok=False,
                error_message=f"unsupported provider for processor: {decision.provider.value}",
                permanent_failure=True,
            )

        session_row = self.session_repo.get(decision.session_id)
        task_row = self.task_repo.get(decision.task_id)
        if session_row is None or task_row is None:
            return ProcessResult(
                ok=False,
                error_message="task or session not found",
                permanent_failure=True,
            )

        try:
            page = await self.session_pool.get_page(
                session_id=session_row.id,
                url=session_row.chat_url,
                provider=decision.provider.value,
            )

            page_state = await self._inspect_adapter_page_state(page)

            logged_in = await self.adapter.is_logged_in(page)
            if page_state is not None:
                logged_in = page_state.chat_ready

            if not logged_in:
                try:
                    await page.bring_to_front()
                except Exception:
                    pass

                login_message = (
                    "session not logged in; please complete required steps in opened browser, "
                    "then notify worker readiness via /admin/sessions (Mark Login OK) "
                    "or POST /api/sessions/{session_id}/notify-ready"
                )

                if page_state is not None:
                    if page_state.cookie_required:
                        login_message = (
                            "cookie consent required before login. "
                            "Please complete cookie/verification/login in opened browser, "
                            "then notify worker readiness via /admin/sessions (Mark Login OK) "
                            "or POST /api/sessions/{session_id}/notify-ready"
                        )
                    elif page_state.verification_required:
                        login_message = (
                            "human verification required (Cloudflare). "
                            "Please complete verification/login in the opened browser, "
                            "then notify worker readiness via /admin/sessions (Mark Login OK) "
                            "or POST /api/sessions/{session_id}/notify-ready"
                        )
                    elif page_state.login_required:
                        login_message = (
                            "session login required. Please log in via opened browser, "
                            "then notify worker readiness via /admin/sessions (Mark Login OK) "
                            "or POST /api/sessions/{session_id}/notify-ready"
                        )
                    else:
                        login_message = (
                            "chat window is not ready; please complete any required prompts in opened browser, "
                            "then notify worker readiness via /admin/sessions (Mark Login OK) "
                            "or POST /api/sessions/{session_id}/notify-ready"
                        )
                elif await self._looks_like_human_verification(page):
                    login_message = (
                        "human verification required (Cloudflare). "
                        "Please complete verification/login in the opened browser, "
                        "then notify worker readiness via /admin/sessions (Mark Login OK) "
                        "or POST /api/sessions/{session_id}/notify-ready"
                    )

                self.session_repo.update_state(
                    session_row.id,
                    SessionState.WAIT_LOGIN,
                    login_state="need_login",
                )
                return ProcessResult(
                    ok=False,
                    error_message=login_message,
                )

            previous = await self.adapter.latest_response(page)
            message = f"{task_row.prompt_text}\n\n{task_row.document_text}"

            await self.adapter.send_message(page, message)
            response = await self.adapter.wait_for_response(
                page,
                previous_response=previous,
                timeout_ms=self.timeout_ms,
            )
            if not response:
                return ProcessResult(ok=False, error_message="response timeout")
            return ProcessResult(ok=True, raw_response=response)
        except Exception as exc:
            await self.session_pool.reset_session(
                session_row.id,
                provider=decision.provider.value,
            )
            return ProcessResult(ok=False, error_message=str(exc))

    async def close(self) -> None:
        await self.session_pool.close_all()

    async def _looks_like_human_verification(self, page: object) -> bool:
        try:
            selectors = (
                "text=Verify you are human",
                "iframe[title*='challenge' i]",
                "iframe[src*='challenges.cloudflare.com']",
            )
            for selector in selectors:
                locator = page.locator(selector).first  # type: ignore[attr-defined]
                if await locator.is_visible():
                    return True
        except Exception:
            return False
        return False

    async def _inspect_adapter_page_state(self, page: object) -> object | None:
        inspect_fn = getattr(self.adapter, "inspect_page_state", None)
        if not callable(inspect_fn):
            return None
        try:
            return await inspect_fn(page)
        except Exception:
            return None


class OpenChatTaskProcessor(PooledProviderTaskProcessor):
    def __init__(
        self,
        session_repo: SessionRepository | None = None,
        task_repo: TaskRepository | None = None,
        adapter: OpenChatAdapter | None = None,
        session_pool: BrowserSessionPool | None = None,
        timeout_ms: int = 60000,
        headless: bool | None = None,
    ) -> None:
        super().__init__(
            provider=Provider.OPENCHAT,
            adapter=adapter or OpenChatAdapter(),
            session_repo=session_repo,
            task_repo=task_repo,
            session_pool=session_pool,
            timeout_ms=timeout_ms,
            headless=headless,
        )


class MultiProviderTaskProcessor:
    def __init__(
        self,
        processors: dict[Provider, TaskProcessor] | None = None,
        pool_manager: ProviderSessionPoolManager | None = None,
        session_repo: SessionRepository | None = None,
        task_repo: TaskRepository | None = None,
        timeout_ms: int = 60000,
        headless: bool | None = None,
    ) -> None:
        if headless is None:
            is_headless = getenv("WORKER_HEADLESS", "1") == "1"
        else:
            is_headless = headless

        self.pool_manager = pool_manager or ProviderSessionPoolManager(headless=is_headless)
        self.session_repo = session_repo or SessionRepository()
        self.task_repo = task_repo or TaskRepository()

        if processors is not None:
            self.processors = processors
            return

        self.processors = {
            Provider.OPENCHAT: PooledProviderTaskProcessor(
                provider=Provider.OPENCHAT,
                adapter=OpenChatAdapter(),
                session_repo=self.session_repo,
                task_repo=self.task_repo,
                session_pool=self.pool_manager.get_pool(Provider.OPENCHAT),
                timeout_ms=timeout_ms,
                headless=is_headless,
            ),
            Provider.GEMINI: PooledProviderTaskProcessor(
                provider=Provider.GEMINI,
                adapter=GeminiAdapter(),
                session_repo=self.session_repo,
                task_repo=self.task_repo,
                session_pool=self.pool_manager.get_pool(Provider.GEMINI),
                timeout_ms=timeout_ms,
                headless=is_headless,
            ),
            Provider.GROK: PooledProviderTaskProcessor(
                provider=Provider.GROK,
                adapter=GrokAdapter(),
                session_repo=self.session_repo,
                task_repo=self.task_repo,
                session_pool=self.pool_manager.get_pool(Provider.GROK),
                timeout_ms=timeout_ms,
                headless=is_headless,
            ),
            Provider.DEEPSEEK: PooledProviderTaskProcessor(
                provider=Provider.DEEPSEEK,
                adapter=DeepSeekAdapter(),
                session_repo=self.session_repo,
                task_repo=self.task_repo,
                session_pool=self.pool_manager.get_pool(Provider.DEEPSEEK),
                timeout_ms=timeout_ms,
                headless=is_headless,
            ),
        }

    async def process(self, decision: DispatchDecision) -> ProcessResult:
        processor = self.processors.get(decision.provider)
        if processor is None:
            return ProcessResult(
                ok=False,
                error_message=f"unsupported provider: {decision.provider.value}",
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


class SchedulerWorker:
    def __init__(
        self,
        scheduler: WeightedRoundRobinScheduler | None = None,
        task_repo: TaskRepository | None = None,
        processor: TaskProcessor | None = None,
        response_extractor: ResponseExtractor | None = None,
        json_validator: JSONValidator | None = None,
        retry_handler: RetryHandler | None = None,
        prompt_generator: PromptGenerator | None = None,
        log_repo: LogRepository | None = None,
        idle_sleep_seconds: float = 1.0,
    ) -> None:
        self.scheduler = scheduler or WeightedRoundRobinScheduler()
        self.task_repo = task_repo or TaskRepository()
        self.processor = processor or MultiProviderTaskProcessor(task_repo=self.task_repo)
        self.response_extractor = response_extractor or ResponseExtractor()
        self.json_validator = json_validator or JSONValidator()
        self.retry_handler = retry_handler or RetryHandler(max_parse_retry=1)
        self.prompt_generator = prompt_generator or PromptGenerator()
        self.log_repo = log_repo or LogRepository()
        self.idle_sleep_seconds = idle_sleep_seconds

    async def run_once(self) -> bool:
        decision = self.scheduler.dispatch_next()
        if decision is None:
            await asyncio.sleep(self.idle_sleep_seconds)
            return False

        trace_id = uuid4().hex

        self.log_repo.add_log(
            trace_id=trace_id,
            level="INFO",
            provider=decision.provider,
            task_id=decision.task_id,
            session_id=decision.session_id,
            event="task_dispatched",
            message=f"attempt={decision.attempt_no}",
        )

        started = perf_counter()
        result = await self.processor.process(decision)
        elapsed_ms = int((perf_counter() - started) * 1000)

        if result.ok:
            self.scheduler.mark_attempt_success(
                task_id=decision.task_id,
                session_id=decision.session_id,
                attempt_id=decision.attempt_id,
                latency_ms=elapsed_ms,
            )
            if result.raw_response:
                self.task_repo.save_raw_response(
                    task_id=decision.task_id,
                    provider=decision.provider,
                    response_text=result.raw_response,
                )
                self.task_repo.mark_status(task_id=decision.task_id, status=TaskStatus.EXTRACTING)
                self.log_repo.add_log(
                    trace_id=trace_id,
                    level="INFO",
                    provider=decision.provider,
                    task_id=decision.task_id,
                    session_id=decision.session_id,
                    event="task_extracting",
                    message="raw response stored",
                )
                extraction_ok = self._handle_extraction(
                    task_id=decision.task_id,
                    raw_response=result.raw_response,
                    attempt_no=decision.attempt_no,
                    trace_id=trace_id,
                )
                if extraction_ok:
                    self.task_repo.mark_status(task_id=decision.task_id, status=TaskStatus.COMPLETED)
                    self.log_repo.add_log(
                        trace_id=trace_id,
                        level="INFO",
                        provider=decision.provider,
                        task_id=decision.task_id,
                        session_id=decision.session_id,
                        event="task_completed",
                        message=f"latency_ms={elapsed_ms}",
                    )
                return True

            self.task_repo.mark_status(task_id=decision.task_id, status=TaskStatus.COMPLETED)
            self.log_repo.add_log(
                trace_id=trace_id,
                level="INFO",
                provider=decision.provider,
                task_id=decision.task_id,
                session_id=decision.session_id,
                event="task_completed",
                message=f"latency_ms={elapsed_ms}, no_raw_response",
            )
        else:
            self.scheduler.mark_attempt_failed(
                task_id=decision.task_id,
                session_id=decision.session_id,
                attempt_id=decision.attempt_id,
                error_message=result.error_message or "processor failed",
                latency_ms=elapsed_ms,
            )
            if result.error_message and (
                "session not logged in" in result.error_message.lower()
                or "login required" in result.error_message.lower()
                or "human verification" in result.error_message.lower()
            ):
                self.log_repo.add_log(
                    trace_id=trace_id,
                    level="WARNING",
                    provider=decision.provider,
                    task_id=decision.task_id,
                    session_id=decision.session_id,
                    event="session_login_required",
                    message=result.error_message,
                )
            if result.permanent_failure:
                self.task_repo.mark_status(task_id=decision.task_id, status=TaskStatus.FAILED)
            self.log_repo.add_log(
                trace_id=trace_id,
                level="ERROR",
                provider=decision.provider,
                task_id=decision.task_id,
                session_id=decision.session_id,
                event="task_failed",
                message=result.error_message or "processor failed",
            )
        return True

    def _handle_extraction(self, task_id: str, raw_response: str, attempt_no: int, trace_id: str) -> bool:
        try:
            payload = self.response_extractor.extract_json_candidate(raw_response)
        except Exception as exc:
            return self._on_extraction_failed(task_id, attempt_no, f"extract_error: {exc}", trace_id)

        validated = self.json_validator.validate(payload)
        if not validated.ok or validated.value is None:
            return self._on_extraction_failed(
                task_id,
                attempt_no,
                f"validate_error: {validated.error_message}",
                trace_id,
            )

        fields = self.json_validator.to_storage_fields(validated.value)
        self.task_repo.save_extracted_result(
            task_id,
            valid_schema=True,
            extraction_error=None,
            case_status=fields["case_status"],
            judgment_result=fields["judgment_result"],
            filing_date=fields["filing_date"],
            judge_assignment_date=fields["judge_assignment_date"],
            trial_date=fields["trial_date"],
            judgment_date=fields["judgment_date"],
        )
        self.log_repo.add_log(
            trace_id=trace_id,
            level="INFO",
            task_id=task_id,
            event="extract_success",
            message="schema validated",
        )
        return True

    def _on_extraction_failed(self, task_id: str, attempt_no: int, error_message: str, trace_id: str) -> bool:
        self.task_repo.save_extracted_result(
            task_id,
            valid_schema=False,
            extraction_error=error_message,
        )
        self.log_repo.add_log(
            trace_id=trace_id,
            level="WARNING",
            task_id=task_id,
            event="extract_failed",
            message=error_message,
        )

        if self.retry_handler.should_retry_parse(attempt_no):
            task = self.task_repo.get(task_id)
            if task is not None:
                retry_prompt = self.prompt_generator.build_retry_prompt(
                    previous_prompt=task.prompt_text,
                    error_message=error_message,
                )
                self.task_repo.update_prompt(task_id, retry_prompt)
            self.task_repo.mark_status(task_id=task_id, status=TaskStatus.PENDING)
            self.log_repo.add_log(
                trace_id=trace_id,
                level="WARNING",
                task_id=task_id,
                event="extract_retry_scheduled",
                message=f"attempt_no={attempt_no}",
            )
            return False

        self.task_repo.mark_status(task_id=task_id, status=TaskStatus.FAILED)
        self.log_repo.add_log(
            trace_id=trace_id,
            level="ERROR",
            task_id=task_id,
            event="task_failed_after_extract",
            message=error_message,
        )
        return False

    async def run_forever(self, stop_after: int | None = None) -> None:
        count = 0
        try:
            recovered_sessions = self.scheduler.session_repo.recover_stuck_busy_sessions()
            if recovered_sessions > 0:
                self.log_repo.add_log(
                    level="WARNING",
                    event="session_recovered",
                    message=f"recovered_stuck_busy_sessions={recovered_sessions}",
                )
            while True:
                _ = await self.run_once()
                count += 1
                if stop_after is not None and count >= stop_after:
                    return
        finally:
            close_fn = getattr(self.processor, "close", None)
            if callable(close_fn):
                maybe_awaitable = close_fn()
                if asyncio.iscoroutine(maybe_awaitable):
                    await maybe_awaitable
