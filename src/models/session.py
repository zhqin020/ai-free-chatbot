from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Provider(str, Enum):
    OPENCHAT = "openchat"
    GEMINI = "gemini"
    GROK = "grok"
    DEEPSEEK = "deepseek"


class SessionState(str, Enum):
    READY = "READY"
    BUSY = "BUSY"
    WAIT_LOGIN = "WAIT_LOGIN"
    UNHEALTHY = "UNHEALTHY"
    RECOVERING = "RECOVERING"


class SessionConfig(BaseModel):
    id: str = Field(min_length=1)
    provider: Provider
    chat_url: str = Field(min_length=1)
    enabled: bool = True
    priority: int = 100


class SessionUpdate(BaseModel):
    provider: Provider
    chat_url: str = Field(min_length=1)
    enabled: bool = True
    priority: int = 100


class SessionStatus(BaseModel):
    id: str
    state: SessionState
    enabled: bool = True
    login_state: str = "unknown"
    last_seen_at: Optional[datetime] = None


class SessionRead(BaseModel):
    id: str
    session_name: str
    http_session_id: Optional[str] = None
    start_time: datetime
    status: str
    provider: Provider
    chat_url: str
    enabled: bool
    priority: int
    state: SessionState
    login_state: str
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SessionHttpTrackingRead(BaseModel):
    session_id: str
    tracked: bool
    source: str
    cookie_name: str | None = None
    composed_session_id: str | None = None
    updated_at: datetime | None = None


class SessionOpenRead(BaseModel):
    session_id: str
    chat_url: str
    previous_http_session_id: str | None = None
    current_http_session_id: str | None = None
    requires_rebuild_confirmation: bool = False
    warning: str | None = None


class SessionRebuildRead(BaseModel):
    old_session_id: str
    rebuilt_session_id: str
    message: str


class SessionStatsRead(BaseModel):
    session_id: str
    implemented: bool
    interaction_count: int | None = None
    message: str


class SessionVerifyRead(BaseModel):
    session_id: str
    valid: bool
    deleted: bool = False
    reason: str
    stored_http_session_id: str | None = None
    current_http_session_id: str | None = None
    tracked: bool = False
    cookie_name: str | None = None
    composed_session_id: str | None = None
    updated_at: datetime | None = None
