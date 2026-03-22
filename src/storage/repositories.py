from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select

from ..models.session import SessionConfig, SessionState
from ..models.result import CaseStatus
from ..models.task import TaskCreate, TaskStatus
from .database import (
    ExtractedResultORM,
    ProviderConfigORM,
    RawResponseORM,
    SessionORM,
    SystemLogORM,
    AppParamORM,
    TaskAttemptORM,
    TaskORM,
    session_scope,
)


class SessionRepository:
    def update_chat_url(self, session_id: str, chat_url: str) -> bool:
        with session_scope() as session:
            row = session.get(SessionORM, session_id)
            if row is None:
                return False
            row.chat_url = chat_url
            row.updated_at = datetime.now(UTC)
            session.flush()
            return True
    def upsert(self, config: SessionConfig) -> SessionORM:
        with session_scope() as session:
            row = session.get(SessionORM, config.id)
            if row is None:
                row = SessionORM(
                    id=config.id,
                    provider=config.provider,
                    chat_url=config.chat_url,
                )
                session.add(row)
            else:
                row.provider = config.provider
                row.chat_url = config.chat_url
                row.updated_at = datetime.now(UTC)
            session.flush()
            session.refresh(row)
            return row

    def list(self) -> list[SessionORM]:
        with session_scope() as session:
            stmt = select(SessionORM)
            rows = session.execute(stmt.order_by(SessionORM.id.asc())).scalars().all()
            return rows

    def get(self, session_id: str) -> Optional[SessionORM]:
        with session_scope() as session:
            return session.get(SessionORM, session_id)

    def update_http_session(self, session_id: str, http_session_id: str | None) -> bool:
        with session_scope() as session:
            row = session.get(SessionORM, session_id)
            if row is None:
                return False
            row.http_session_id = http_session_id
            row.updated_at = datetime.now(UTC)
            session.flush()
            return True

    # 已移除 update_state，所有会话状态仅内存维护

    def delete(self, session_id: str) -> bool:
        with session_scope() as session:
            row = session.get(SessionORM, session_id)
            if row is None:
                return False
            # 先删除所有依赖该 session 的 task_attempts 记录，避免外键约束错误
            from sqlalchemy import text
            session.execute(
                text("DELETE FROM task_attempts WHERE session_id = :sid"),
                {"sid": session_id}
            )
            session.delete(row)
            return True

    def disable(self, session_id: str, *, login_state: str = "invalid_session") -> bool:
        with session_scope() as session:
            row = session.get(SessionORM, session_id)
            if row is None:
                return False
            row.enabled = False
            row.state = SessionState.WAIT_LOGIN
            row.login_state = login_state
            row.updated_at = datetime.now(UTC)
            session.flush()
            return True

    def list_by_provider(self, provider: str) -> list[SessionORM]:
        with session_scope() as session:
            rows = session.execute(
                select(SessionORM)
                .where(SessionORM.provider == provider)
                .order_by(SessionORM.priority.asc(), SessionORM.id.asc())
            ).scalars().all()
            return rows

    def delete_by_provider(self, provider: str) -> int:
        with session_scope() as session:
            rows = session.execute(select(SessionORM).where(SessionORM.provider == provider)).scalars().all()
            count = len(rows)
            for row in rows:
                session.delete(row)
            return count

    def recover_stuck_busy_sessions(self, timeout_seconds: int | None = None) -> int:
        with session_scope() as session:
            stmt = select(SessionORM).where(
                SessionORM.state == SessionState.BUSY,
                SessionORM.login_state != "need_login",
            )
            if timeout_seconds is not None and timeout_seconds > 0:
                threshold = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
                stmt = stmt.where(SessionORM.updated_at < threshold)

            rows = session.execute(stmt).scalars().all()
            for row in rows:
                row.state = SessionState.READY
                row.updated_at = datetime.now(UTC)
            session.flush()
            return len(rows)

    def increment_chat_rounds(self, session_id: str) -> None:
        with session_scope() as session:
            row = session.get(SessionORM, session_id)
            if row:
                row.chat_rounds += 1
                row.updated_at = datetime.now(UTC)
                session.flush()

    def reset_chat_rounds(self, session_id: str) -> None:
        with session_scope() as session:
            row = session.get(SessionORM, session_id)
            if row:
                row.chat_rounds = 0
                row.updated_at = datetime.now(UTC)
                session.flush()


class TaskRepository:
    def create(self, payload: TaskCreate) -> TaskORM:
        now = datetime.now(UTC)
        with session_scope() as session:
            row = TaskORM(
                id=str(uuid4()),
                external_id=payload.external_id,
                status=TaskStatus.PENDING,
                prompt_text=payload.prompt,
                document_text=payload.document_text,
                # provider_hint 字段已废弃
                owner=payload.owner,
                session_id=payload.session_id,
                provider=payload.provider,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return row
    def get(self, task_id: str) -> Optional[TaskORM]:
        with session_scope() as session:
            return session.get(TaskORM, task_id)

    def claim_next_pending(self, owner: Optional[str] = None) -> Optional[TaskORM]:
        with session_scope() as session:
            stmt = select(TaskORM).where(TaskORM.status == TaskStatus.PENDING)
            if owner is not None:
                stmt = stmt.where(TaskORM.owner == owner)
            row = session.execute(stmt.order_by(TaskORM.created_at.asc())).scalars().first()
            if row is None:
                return None
            row.status = TaskStatus.DISPATCHED
            row.updated_at = datetime.now(UTC)
            session.flush()
            session.refresh(row)
            return row

    def mark_status(self, task_id: str, status: TaskStatus) -> bool:
        with session_scope() as session:
            row = session.get(TaskORM, task_id)
            if row is None:
                return False
            row.status = status
            row.updated_at = datetime.now(UTC)
            session.flush()
            return True

    def recover_timeouts(self, timeout_seconds: int) -> list[str]:
        threshold = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        recovered: list[str] = []
        with session_scope() as session:
            dispatched = session.execute(
                select(TaskORM).where(
                    TaskORM.status == TaskStatus.DISPATCHED,
                    TaskORM.updated_at < threshold,
                )
            ).scalars().all()

            for task in dispatched:
                task.status = TaskStatus.FAILED
                task.updated_at = datetime.now(UTC)
                recovered.append(task.id)

            pending = session.execute(
                select(TaskORM).where(
                    TaskORM.status == TaskStatus.PENDING,
                    TaskORM.updated_at < threshold,
                )
            ).scalars().all()

            for task in pending:
                task.status = TaskStatus.FAILED
                task.updated_at = datetime.now(UTC)
                recovered.append(task.id)

            session.flush()
        return recovered

    def save_raw_response(self, task_id: str, provider: str, response_text: str) -> None:
        with session_scope() as session:
            row = RawResponseORM(
                task_id=task_id,
                provider=provider,
                response_text=response_text,
            )
            session.add(row)
            session.flush()

    def save_extracted_result(
        self,
        task_id: str,
        *,
        valid_schema: bool,
        extraction_error: str | None = None,
        case_status: CaseStatus | str | None = None,
        judgment_result: str | None = None,
        filing_date: date | None = None,
        judge_assignment_date: date | None = None,
        trial_date: date | None = None,
        judgment_date: date | None = None,
    ) -> None:
        normalized_status: CaseStatus | None
        if case_status is None or isinstance(case_status, CaseStatus):
            normalized_status = case_status
        else:
            normalized_status = CaseStatus(case_status)

        with session_scope() as session:
            row = ExtractedResultORM(
                task_id=task_id,
                case_status=normalized_status,
                judgment_result=judgment_result,
                filing_date=filing_date,
                judge_assignment_date=judge_assignment_date,
                trial_date=trial_date,
                judgment_date=judgment_date,
                valid_schema=valid_schema,
                extraction_error=extraction_error,
            )
            session.add(row)
            session.flush()

    def update_prompt(self, task_id: str, prompt_text: str) -> bool:
        with session_scope() as session:
            row = session.get(TaskORM, task_id)
            if row is None:
                return False
            row.prompt_text = prompt_text
            row.updated_at = datetime.now(UTC)
            session.flush()
            return True

    def get_latest_raw_response(self, task_id: str) -> RawResponseORM | None:
        with session_scope() as session:
            row = session.execute(
                select(RawResponseORM)
                .where(RawResponseORM.task_id == task_id)
                .order_by(RawResponseORM.captured_at.desc(), RawResponseORM.id.desc())
                .limit(1)
            ).scalars().first()
            return row

    def get_latest_extracted_result(self, task_id: str) -> ExtractedResultORM | None:
        with session_scope() as session:
            row = session.execute(
                select(ExtractedResultORM)
                .where(ExtractedResultORM.task_id == task_id)
                .order_by(ExtractedResultORM.created_at.desc(), ExtractedResultORM.id.desc())
                .limit(1)
            ).scalars().first()
            return row


class ProviderConfigRepository:
    def update_ready_selectors(self, name: str, selectors: dict) -> bool:
        from src import logging_mp
        logger = logging_mp.get_logger("storage.repositories")
        logger.info(f"[update_ready_selectors] provider={name} selectors={selectors}")
        """
        更新 provider 的 ready_selectors_json 字段，selectors 为 dict，将以 JSON 字符串存储。
        """
        import json
        with session_scope() as session:
            row = session.get(ProviderConfigORM, name)
            if row is None:
                return False
            row.ready_selectors_json = json.dumps(selectors, ensure_ascii=False)
            row.updated_at = datetime.now(UTC)
            session.flush()
            return True
        
    DEFAULTS: dict[str, dict[str, str]] = {
        "mock_openai": {"url": "http://127.0.0.1:8010/", "icon": "🧪"},
        "deepseek": {"url": "https://chat.deepseek.com/", "icon": "🤖"},
    }

    def ensure_defaults(self) -> None:
        now = datetime.now(UTC)
        with session_scope() as session:
            for name, value in self.DEFAULTS.items():
                row = session.get(ProviderConfigORM, name)
                if row is None:
                    row = ProviderConfigORM(
                        name=name,
                        url=value["url"],
                        icon=value["icon"],
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)

    def list(self) -> list[ProviderConfigORM]:
        self.ensure_defaults()
        with session_scope() as session:
            rows = session.execute(select(ProviderConfigORM).order_by(ProviderConfigORM.name.asc())).scalars().all()
            return rows

    def get(self, name: str) -> ProviderConfigORM | None:
        self.ensure_defaults()
        with session_scope() as session:
            return session.get(ProviderConfigORM, name)

    def upsert(self, name: str, *, url: str, icon: str) -> ProviderConfigORM:
        now = datetime.now(UTC)
        with session_scope() as session:
            row = session.get(ProviderConfigORM, name)
            if row is None:
                row = ProviderConfigORM(
                    name=name,
                    url=url,
                    icon=icon,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.url = url
                row.icon = icon
                row.updated_at = now
            session.flush()
            session.refresh(row)
            return row

    def delete(self, name: str) -> bool:
        with session_scope() as session:
            row = session.get(ProviderConfigORM, name)
            if row is None:
                return False
            session.delete(row)
            return True
class AppParamRepository:
    DEFAULT_ID = 1
    DEFAULT_MODE = "priority"
    DEFAULT_MAX_CHAT_ROUNDS = 0

    def _ensure_row(self, session, timestamp: datetime) -> AppParamORM:
        row = session.get(AppParamORM, self.DEFAULT_ID)
        if row is None:
            row = AppParamORM(
                id=self.DEFAULT_ID,
                mode=self.DEFAULT_MODE,
                max_chat_rounds=self.DEFAULT_MAX_CHAT_ROUNDS,
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(row)
        return row

    def get(self) -> AppParamORM:
        now = datetime.now(UTC)
        with session_scope() as session:
            row = self._ensure_row(session, now)
            session.flush()
            session.refresh(row)
            return row

    def get_mode(self) -> str:
        return self.get().mode

    def update_config(self, *, mode: str | None = None, max_chat_rounds: int | None = None) -> AppParamORM:
        now = datetime.now(UTC)
        with session_scope() as session:
            row = self._ensure_row(session, now)
            if mode is not None:
                row.mode = mode
            if max_chat_rounds is not None:
                row.max_chat_rounds = max_chat_rounds
            row.updated_at = now
            session.flush()
            session.refresh(row)
            return row

class AttemptRepository:
    def start_attempt(self, task_id: str, session_id: str, attempt_no: int) -> TaskAttemptORM:
        with session_scope() as session:
            row = TaskAttemptORM(
                task_id=task_id,
                session_id=session_id,
                attempt_no=attempt_no,
                status="STARTED",
                started_at=datetime.now(UTC),
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return row

    def finish_attempt(
        self,
        attempt_id: int,
        status: str,
        latency_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        with session_scope() as session:
            row = session.get(TaskAttemptORM, attempt_id)
            if row is None:
                return False
            row.status = status
            row.latency_ms = latency_ms
            row.error_message = error_message
            row.finished_at = datetime.now(UTC)
            session.flush()
            return True

    def next_attempt_no(self, task_id: str) -> int:
        with session_scope() as session:
            count = session.execute(
                select(func.count(TaskAttemptORM.id)).where(TaskAttemptORM.task_id == task_id)
            ).scalar_one()
            return int(count) + 1

    def get_attempt_count(self, task_id: str) -> int:
        with session_scope() as session:
            count = session.execute(
                select(func.count(TaskAttemptORM.id)).where(TaskAttemptORM.task_id == task_id)
            ).scalar_one()
            return int(count)

    def has_session_attempts(self, session_id: str) -> bool:
        with session_scope() as session:
            count = session.execute(
                select(func.count(TaskAttemptORM.id)).where(TaskAttemptORM.session_id == session_id)
            ).scalar_one()
            return int(count) > 0


class LogRepository:
    def add_log(
        self,
        *,
        trace_id: str | None = None,
        level: str,
        event: str,
        message: str,
        provider: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
    ) -> SystemLogORM:
        with session_scope() as session:
            row = SystemLogORM(
                trace_id=trace_id,
                level=level.upper(),
                provider=provider,
                task_id=task_id,
                session_id=session_id,
                event=event,
                message=message,
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return row

    def query_logs(
        self,
        *,
        trace_id: str | None = None,
        level: str | None = None,
        provider: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SystemLogORM], int]:
        if page < 1:
            page = 1
        page_size = max(1, min(page_size, 200))

        with session_scope() as session:
            stmt = select(SystemLogORM)
            count_stmt = select(func.count(SystemLogORM.id))

            if level:
                stmt = stmt.where(SystemLogORM.level == level.upper())
                count_stmt = count_stmt.where(SystemLogORM.level == level.upper())
            if trace_id:
                stmt = stmt.where(SystemLogORM.trace_id == trace_id)
                count_stmt = count_stmt.where(SystemLogORM.trace_id == trace_id)
            if provider is not None:
                stmt = stmt.where(SystemLogORM.provider == provider)
                count_stmt = count_stmt.where(SystemLogORM.provider == provider)
            if task_id:
                stmt = stmt.where(SystemLogORM.task_id == task_id)
                count_stmt = count_stmt.where(SystemLogORM.task_id == task_id)
            if session_id:
                stmt = stmt.where(SystemLogORM.session_id == session_id)
                count_stmt = count_stmt.where(SystemLogORM.session_id == session_id)
            if start_at is not None:
                stmt = stmt.where(SystemLogORM.created_at >= start_at)
                count_stmt = count_stmt.where(SystemLogORM.created_at >= start_at)
            if end_at is not None:
                stmt = stmt.where(SystemLogORM.created_at <= end_at)
                count_stmt = count_stmt.where(SystemLogORM.created_at <= end_at)

            total = int(session.execute(count_stmt).scalar_one())
            rows = session.execute(
                stmt.order_by(SystemLogORM.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
            return rows, total

    def get_latest_trace_id(self, task_id: str) -> str | None:
        with session_scope() as session:
            row = session.execute(
                select(SystemLogORM.trace_id)
                .where(SystemLogORM.task_id == task_id)
                .where(SystemLogORM.trace_id.is_not(None))
                .order_by(SystemLogORM.created_at.desc(), SystemLogORM.id.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            return row[0]
