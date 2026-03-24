from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Generator

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from ..config import get_settings
from ..models.result import CaseStatus
 
from ..models.task import TaskStatus


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class SessionORM(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(ForeignKey("provider_configs.name"), nullable=False)
    chat_url: Mapped[str] = mapped_column(Text, nullable=False)
    http_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 已移除 state/login_state 字段，所有会话状态仅内存维护
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 新增：优先级字段，默认100，支持 session 调度
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    chat_rounds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    attempts: Mapped[list[TaskAttemptORM]] = relationship(back_populates="session", cascade="all, delete-orphan")
    # 新增：与 TaskORM 的一对多关系
    tasks: Mapped[list[TaskORM]] = relationship("TaskORM", back_populates="session")

    # 新增：与 ProviderConfigORM 的多对一关系
    provider_config: Mapped[ProviderConfigORM] = relationship("ProviderConfigORM", back_populates="sessions", foreign_keys=[provider])


class ProviderConfigORM(Base):
    __tablename__ = "provider_configs"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(256), nullable=False)

    # 新增：用于存储 chat ready 页面特征（selectors），JSON 字符串 (Deprecated, use independent fields below)
    ready_selectors_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 拆分独立维护的 selector 字段
    new_chat_selector: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_selector: Mapped[str | None] = mapped_column(Text, nullable=True)
    send_button_selector: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_selector: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # 新增：保存获取的整个测试页面 DOM
    dom_sample: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 新增：优先级字段，默认100，可按Provider分配
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    need_login: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    lock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # 新增：与 TaskORM 的一对多关系
    tasks: Mapped[list[TaskORM]] = relationship("TaskORM", back_populates="provider_config")
    # 新增：与 SessionORM 的一对多关系
    sessions: Mapped[list[SessionORM]] = relationship("SessionORM", back_populates="provider_config")


class AppParamORM(Base):
    __tablename__ = "app_params"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    max_chat_rounds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    # 新增：任务归属线程/worker
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)  # 新增，允许为 None
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    document_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(ForeignKey("provider_configs.name"), nullable=True)  # 新增，允许为 None
    # provider_hint 字段已废弃，彻底移除
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    attempts: Mapped[list[TaskAttemptORM]] = relationship(back_populates="task")
    raw_responses: Mapped[list[RawResponseORM]] = relationship(back_populates="task")
    extracted_results: Mapped[list[ExtractedResultORM]] = relationship(back_populates="task")

    # 新增：与 SessionORM 的多对一关系
    session: Mapped[SessionORM | None] = relationship("SessionORM", back_populates="tasks", foreign_keys=[session_id])

    # 新增：与 ProviderConfigORM 的多对一关系
    provider_config: Mapped[ProviderConfigORM | None] = relationship("ProviderConfigORM", back_populates="tasks", foreign_keys=[provider])


class TaskAttemptORM(Base):
    __tablename__ = "task_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
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
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    task: Mapped[TaskORM] = relationship(back_populates="raw_responses")


class ExtractedResultORM(Base):
    __tablename__ = "extracted_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
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
    provider: Mapped[str] = mapped_column(
        String(64), nullable=False
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
    provider: Mapped[str | None] = mapped_column(
        String(64), nullable=True
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
    # 自动注册 pool_entries 表
    try:
        from src.models.pool_entry import Base as PoolEntryBase
        PoolEntryBase.metadata.create_all(engine)
    except ImportError:
        pass
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
