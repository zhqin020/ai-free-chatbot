from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from src.models.session import SessionState
from src.models.task import TaskStatus
from src.storage.database import SessionORM
from src.storage.repositories import (
    AttemptRepository,
    SessionRepository,
    TaskDispatchConfigRepository,
    TaskRepository,
)


@dataclass
class DispatchDecision:
    task_id: str
    session_id: str
    provider: str
    attempt_id: int
    attempt_no: int
    dispatched_at: datetime
    prompt: str
    document_text: str


class WeightedRoundRobinScheduler:
    def __init__(
        self,
        session_repo: SessionRepository | None = None,
        task_repo: TaskRepository | None = None,
        attempt_repo: AttemptRepository | None = None,
        dispatch_config_repo: TaskDispatchConfigRepository | None = None,
        timeout_seconds: int = 30,
        session_pool: object = None,
    ) -> None:
        self.session_repo = session_repo or SessionRepository()
        self.task_repo = task_repo or TaskRepository()
        self.attempt_repo = attempt_repo or AttemptRepository()
        self.dispatch_config_repo = dispatch_config_repo or TaskDispatchConfigRepository()
        self.timeout_seconds = timeout_seconds
        self._cursor = 0
        self.session_pool = session_pool

    def recover_timeouts(self) -> list[str]:
        return self.task_repo.recover_timeouts(
            timeout_seconds=self.timeout_seconds,
        )

    def dispatch_next(self) -> Optional[DispatchDecision]:
        recovered = self.recover_timeouts()
        if recovered:
            pass
        session_row = self._pick_next_ready_session()
        if session_row is None:
            return None

        task_row = self.task_repo.claim_next_pending(provider_hint=session_row.provider)
        if task_row is None:
            return None

        attempt_no = self.attempt_repo.next_attempt_no(task_id=task_row.id)
        attempt_row = self.attempt_repo.start_attempt(
            task_id=task_row.id,
            session_id=session_row.id,
            attempt_no=attempt_no,
        )
        # 分配后立即更新 last_seen_at（如需）
        # 状态流转全部走 session_pool 内存
        return DispatchDecision(
            task_id=task_row.id,
            session_id=session_row.id,
            provider=session_row.provider,
            attempt_id=attempt_row.id,
            attempt_no=attempt_no,
            dispatched_at=datetime.now(UTC),
            prompt=task_row.prompt_text,
            document_text=task_row.document_text,
        )

    def mark_attempt_success(self, task_id: str, session_id: str, attempt_id: int, latency_ms: int) -> None:
        self.attempt_repo.finish_attempt(
            attempt_id=attempt_id,
            status="SUCCESS",
            latency_ms=latency_ms,
            error_message=None,
        )
        self.task_repo.mark_status(task_id=task_id, status=TaskStatus.EXTRACTING)
        # 状态流转全部走 session_pool 内存

    def mark_attempt_failed(
        self,
        task_id: str,
        session_id: str,
        attempt_id: int,
        error_message: str,
        latency_ms: Optional[int] = None,
    ) -> None:
        self.attempt_repo.finish_attempt(
            attempt_id=attempt_id,
            status="FAILED",
            latency_ms=latency_ms,
            error_message=error_message,
        )
        lowered = error_message.lower()
        if (
            "session not logged in" in lowered
            or "login required" in lowered
            or "human verification" in lowered
            or "chat window is not ready" in lowered
        ):
            self.task_repo.mark_status(task_id=task_id, status=TaskStatus.PENDING)
            # 状态流转全部走 session_pool 内存
        elif (
            "missing x server" in lowered
            or "$display" in lowered
            or "looks like you launched a headed browser" in lowered
            or "maximum number of clients reached" in lowered
            or "ozone_platform_x11" in lowered
            or "err_connection_refused" in lowered
            or "connection refused" in lowered
            or "net::err_connection_refused" in lowered
            or "err_name_not_resolved" in lowered
            or "name not resolved" in lowered
            or "err_internet_disconnected" in lowered
            or "timed out" in lowered
        ):
            self.task_repo.mark_status(task_id=task_id, status=TaskStatus.PENDING)
            # 状态流转全部走 session_pool 内存
        else:
            self.task_repo.mark_status(task_id=task_id, status=TaskStatus.FAILED)
            # 状态流转全部走 session_pool 内存

    def _pick_next_ready_session(self) -> Optional[SessionORM]:
        all_sessions = self.session_repo.list()
        if not all_sessions:
            return None

        # 只选内存 pool 中状态为 READY 的 session
        ready_sessions = []
        pool = self.session_pool
        if pool is None:
            raise RuntimeError("session_pool must be injected into WeightedRoundRobinScheduler")
        for s in all_sessions:
            key = s.provider  # provider 作为唯一 key，无需 make_key
            entry = pool._entries.get(key)
            if entry is not None:
                if hasattr(entry.page, "is_unhealthy"):
                    is_healthy = not (entry.page.is_closed() or getattr(entry.page, "is_unhealthy")())
                else:
                    is_healthy = not entry.page.is_closed()
                if is_healthy:
                    ready_sessions.append(s)
        if not ready_sessions:
            return None

        mode = self.dispatch_config_repo.get_mode()
        if mode == "priority":
            pool_list: list[SessionORM] = []
            for row in ready_sessions:
                weight = max(1, 201 - min(200, row.priority))
                pool_list.extend([row] * weight)
            if not pool_list:
                return None
            idx = self._cursor % len(pool_list)
            selected = pool_list[idx]
            self._cursor = (self._cursor + 1) % len(pool_list)
            return selected
        else:
            def session_sort_key(s):
                t = s.last_seen_at or s.created_at
                return (t, s.id)
            sorted_sessions = sorted(ready_sessions, key=session_sort_key)
            return sorted_sessions[0]
