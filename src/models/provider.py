from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskDispatchMode(str, Enum):
    ROUND_ROBIN = "round_robin"
    PRIORITY = "priority"


 


class ProviderConfigCreate(BaseModel):
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    icon: str = Field(min_length=1)


class ProviderConfigUpdate(BaseModel):
    url: str = Field(min_length=1)
    icon: str = Field(min_length=1)


class ProviderConfigRead(BaseModel):
    name: str
    url: str
    icon: str
    builtin: bool
    session_provider: str | None = None
    created_at: datetime
    updated_at: datetime


class ProviderOpenResponse(BaseModel):
    name: str
    url: str
    opened_in_server: bool = False
    open_message: str | None = None


class ProviderClearSessionsResponse(BaseModel):
    name: str
    session_provider: str | None = None
    cleared_count: int


class ProviderSessionTargetResponse(BaseModel):
    name: str
    session_provider: str | None = None
    sessions_url: str


class TaskDispatchConfigRead(BaseModel):
    mode: TaskDispatchMode
    updated_at: datetime


class TaskDispatchConfigUpdate(BaseModel):
    mode: TaskDispatchMode
