from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.models.session import Provider


class CaseStatus(str, Enum):
    CLOSED = "Closed"
    ONGOING = "On-Going"


class JudgmentResult(str, Enum):
    LEAVE = "leave"
    GRANT = "grant"
    DISMISS = "dismiss"


class HearingStatus(str, Enum):
    YES = "true"
    NO = "false"


class Timeline(BaseModel):
    filing_date: Optional[date] = None
    Applicant_file_completed: Optional[date] = None
    reply_memo: Optional[date] = None
    Sent_to_Court: Optional[date] = None
    judgment_date: Optional[date] = None


class LegalExtraction(BaseModel):
    case_id: str = Field(min_length=1)
    case_status: CaseStatus
    judgment_result: JudgmentResult
    hearing: HearingStatus
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
