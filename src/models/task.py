from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field




class TaskStatus(str, Enum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    EXTRACTING = "EXTRACTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CRITICAL = "CRITICAL"


class TaskCreate(BaseModel):
    external_id: Optional[str] = None
    prompt: str = Field(min_length=1)
    document_text: str = Field(min_length=1)
    provider_hint: Optional[str] = None


class TaskRead(BaseModel):
    id: str
    status: TaskStatus
    external_id: Optional[str] = None
    provider_hint: Optional[str] = None
    latest_trace_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TaskPollRead(BaseModel):
    id: str
    status: TaskStatus
    external_id: Optional[str] = None
    provider_hint: Optional[str] = None
    latest_trace_id: Optional[str] = None
    provider: Optional[str] = None
    raw_response: Optional[str] = None
    extracted_json: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime
