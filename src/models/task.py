from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.models.session import Provider


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    EXTRACTING = "EXTRACTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskCreate(BaseModel):
    external_id: Optional[str] = None
    prompt: str = Field(min_length=1)
    document_text: str = Field(min_length=1)
    provider_hint: Optional[Provider] = None


class TaskRead(BaseModel):
    id: str
    status: TaskStatus
    external_id: Optional[str] = None
    provider_hint: Optional[Provider] = None
    latest_trace_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
