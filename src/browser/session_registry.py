from __future__ import annotations

from src.models.session import SessionConfig, SessionState
from src.storage.database import SessionORM
from src.storage.repositories import SessionRepository


class SessionRegistry:
    def __init__(self, session_repo: SessionRepository | None = None) -> None:
        self.session_repo = session_repo or SessionRepository()

    def register(self, config: SessionConfig) -> SessionORM:
        return self.session_repo.upsert(config)

    def remove(self, session_id: str) -> bool:
        return self.session_repo.delete(session_id)

    def list_all(self, enabled_only: bool = False) -> list[SessionORM]:
        return self.session_repo.list(enabled_only=enabled_only)

    def mark_ready(self, session_id: str) -> bool:
        return self.session_repo.update_state(
            session_id=session_id,
            state=SessionState.READY,
            login_state="logged_in",
        )

    def mark_busy(self, session_id: str) -> bool:
        return self.session_repo.update_state(session_id=session_id, state=SessionState.BUSY)

    def mark_wait_login(self, session_id: str) -> bool:
        return self.session_repo.update_state(
            session_id=session_id,
            state=SessionState.WAIT_LOGIN,
            login_state="need_login",
        )

    def mark_unhealthy(self, session_id: str) -> bool:
        return self.session_repo.update_state(session_id=session_id, state=SessionState.UNHEALTHY)

    def mark_recovering(self, session_id: str) -> bool:
        return self.session_repo.update_state(session_id=session_id, state=SessionState.RECOVERING)
