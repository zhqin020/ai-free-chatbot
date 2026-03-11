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


class SessionStatus(BaseModel):
    id: str
    state: SessionState
    enabled: bool = True
    login_state: str = "unknown"
    last_seen_at: Optional[datetime] = None
