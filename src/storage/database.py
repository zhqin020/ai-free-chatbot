from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Generator

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from src.config import get_settings
from src.models.result import CaseStatus
from src.models.session import Provider, SessionState
from src.models.task import TaskStatus


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class SessionORM(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[Provider] = mapped_column(
        Enum(Provider, native_enum=False), nullable=False
    )
    chat_url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    state: Mapped[SessionState] = mapped_column(
        Enum(SessionState, native_enum=False), default=SessionState.READY, nullable=False
    )
    login_state: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    attempts: Mapped[list[TaskAttemptORM]] = relationship(back_populates="session")


class ProviderConfigORM(Base):
    __tablename__ = "provider_configs"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TaskORM(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False), default=TaskStatus.PENDING, nullable=False
    )
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    document_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider_hint: Mapped[Provider | None] = mapped_column(
        Enum(Provider, native_enum=False), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    attempts: Mapped[list[TaskAttemptORM]] = relationship(back_populates="task")
    raw_responses: Mapped[list[RawResponseORM]] = relationship(back_populates="task")
    extracted_results: Mapped[list[ExtractedResultORM]] = relationship(back_populates="task")


class TaskAttemptORM(Base):
    __tablename__ = "task_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[TaskORM] = relationship(back_populates="attempts")
    session: Mapped[SessionORM] = relationship(back_populates="attempts")


class RawResponseORM(Base):
    __tablename__ = "raw_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    provider: Mapped[Provider] = mapped_column(
        Enum(Provider, native_enum=False), nullable=False
    )
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    task: Mapped[TaskORM] = relationship(back_populates="raw_responses")


class ExtractedResultORM(Base):
    __tablename__ = "extracted_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    case_status: Mapped[CaseStatus | None] = mapped_column(
        Enum(CaseStatus, native_enum=False), nullable=True
    )
    judgment_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    judge_assignment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    trial_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    judgment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_schema: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    task: Mapped[TaskORM] = relationship(back_populates="extracted_results")


class SystemMetricHourlyORM(Base):
    __tablename__ = "system_metrics_hourly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hour_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider: Mapped[Provider] = mapped_column(
        Enum(Provider, native_enum=False), nullable=False
    )
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timeout_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SystemLogORM(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[Provider | None] = mapped_column(
        Enum(Provider, native_enum=False), nullable=True
    )
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


def get_engine(echo: bool = False):
    settings = get_settings()
    sqlite_file = settings.sqlite_file
    if sqlite_file is not None:
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(settings.db_url, future=True, echo=echo)


def get_session_maker(echo: bool = False):
    engine = get_engine(echo=echo)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(echo: bool = False) -> None:
    engine = get_engine(echo=echo)
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(echo: bool = False) -> Generator:
    session_local = get_session_maker(echo=echo)
    session = session_local()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
