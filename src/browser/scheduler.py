from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from src.models.session import Provider, SessionState
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
        dispatch_config_repo: TaskDispatchConfigRepository | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.session_repo = session_repo or SessionRepository()
        self.task_repo = task_repo or TaskRepository()
        self.attempt_repo = attempt_repo or AttemptRepository()
        self.dispatch_config_repo = dispatch_config_repo or TaskDispatchConfigRepository()
        self.timeout_seconds = timeout_seconds
        self._cursor = 0

    def recover_timeouts(self) -> list[str]:
        return self.task_repo.recover_timeouts(
            timeout_seconds=self.timeout_seconds,
        )

    def dispatch_next(self) -> Optional[DispatchDecision]:
        recovered = self.recover_timeouts()
        if recovered:
            pass

        # Keep BUSY sessions from being stuck forever after process interruption.
        self.session_repo.recover_stuck_busy_sessions(timeout_seconds=self.timeout_seconds)

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
        lowered = error_message.lower()
        if (
            "session not logged in" in lowered
            or "login required" in lowered
            or "human verification" in lowered
            or "chat window is not ready" in lowered
        ):
            self.task_repo.mark_status(task_id=task_id, status=TaskStatus.PENDING)
            self.session_repo.update_state(
                session_id,
                SessionState.WAIT_LOGIN,
                login_state="need_login",
            )
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
            self.session_repo.update_state(
                session_id,
                SessionState.UNHEALTHY,
                login_state="runtime_error",
            )
        else:
            self.task_repo.mark_status(task_id=task_id, status=TaskStatus.FAILED)
            self.session_repo.update_state(session_id, SessionState.READY)

    def _pick_next_ready_session(self) -> Optional[SessionORM]:
        all_sessions = self.session_repo.list(enabled_only=True)
        if not all_sessions:
            return None

        ready_sessions = [
            s
            for s in all_sessions
            if s.state == SessionState.READY
        ]
        if not ready_sessions:
            return None

        mode = self.dispatch_config_repo.get_mode()
        pool: list[SessionORM] = []
        if mode == "priority":
            for row in ready_sessions:
                weight = max(1, 201 - min(200, row.priority))
                pool.extend([row] * weight)
        else:
            # Round-robin mode ignores priority and rotates evenly among READY sessions.
            pool = sorted(ready_sessions, key=lambda row: row.id)

        if not pool:
            return None

        idx = self._cursor % len(pool)
        selected = pool[idx]
        self._cursor = (self._cursor + 1) % len(pool)
        return selected
