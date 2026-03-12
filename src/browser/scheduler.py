from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from src.models.session import Provider, SessionState
from src.models.task import TaskStatus
from src.storage.database import SessionORM
from src.storage.repositories import AttemptRepository, SessionRepository, TaskRepository


@dataclass
class DispatchDecision:
    task_id: str
    session_id: str
    provider: Provider
    attempt_id: int
    attempt_no: int
    dispatched_at: datetime


class WeightedRoundRobinScheduler:
    def __init__(
        self,
        session_repo: SessionRepository | None = None,
        task_repo: TaskRepository | None = None,
        attempt_repo: AttemptRepository | None = None,
        timeout_seconds: int = 120,
        max_retries: int = 3,
    ) -> None:
        self.session_repo = session_repo or SessionRepository()
        self.task_repo = task_repo or TaskRepository()
        self.attempt_repo = attempt_repo or AttemptRepository()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._cursor = 0

    def recover_timeouts(self) -> list[str]:
        return self.task_repo.recover_timeouts(
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
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
        self.session_repo.update_state(session_row.id, SessionState.BUSY)

        return DispatchDecision(
            task_id=task_row.id,
            session_id=session_row.id,
            provider=session_row.provider,
            attempt_id=attempt_row.id,
            attempt_no=attempt_no,
            dispatched_at=datetime.now(UTC),
        )

    def mark_attempt_success(self, task_id: str, session_id: str, attempt_id: int, latency_ms: int) -> None:
        self.attempt_repo.finish_attempt(
            attempt_id=attempt_id,
            status="SUCCESS",
            latency_ms=latency_ms,
            error_message=None,
        )
        self.task_repo.mark_status(task_id=task_id, status=TaskStatus.EXTRACTING)
        self.session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")

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
        self.task_repo.mark_status(task_id=task_id, status=TaskStatus.PENDING)
        self.session_repo.update_state(session_id, SessionState.READY)

    def _pick_next_ready_session(self) -> Optional[SessionORM]:
        all_sessions = self.session_repo.list(enabled_only=True)
        if not all_sessions:
            return None

        ready_sessions = [
            s
            for s in all_sessions
            if s.state == SessionState.READY and s.login_state != "need_login"
        ]
        if not ready_sessions:
            return None

        weighted: list[SessionORM] = []
        for row in ready_sessions:
            weight = max(1, 201 - min(200, row.priority))
            weighted.extend([row] * weight)

        if not weighted:
            return None

        idx = self._cursor % len(weighted)
        selected = weighted[idx]
        self._cursor = (self._cursor + 1) % len(weighted)
        return selected
