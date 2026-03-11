from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.models.session import Provider


class CaseStatus(str, Enum):
    CLOSED = "结案"
    ONGOING = "正在进行"


class Timeline(BaseModel):
    filing_date: Optional[date] = None
    judge_assignment_date: Optional[date] = None
    trial_date: Optional[date] = None
    judgment_date: Optional[date] = None


class LegalExtraction(BaseModel):
    case_status: CaseStatus
    judgment_result: str = Field(min_length=1)
    timeline: Timeline


class TaskResult(BaseModel):
    task_id: str
    status: str
    provider: Optional[Provider] = None
    raw_response: Optional[str] = None
    extracted_json: Optional[LegalExtraction] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime
