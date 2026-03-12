from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from src.models.session import Provider
from src.storage.repositories import LogRepository

router = APIRouter(prefix="/api/logs", tags=["logs"])
log_repo = LogRepository()


class LogItemResponse(BaseModel):
    id: int
    trace_id: str | None = None
    level: str
    provider: Provider | None = None
    task_id: str | None = None
    session_id: str | None = None
    event: str
    message: str
    created_at: datetime


class LogsQueryResponse(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[LogItemResponse]


@router.get("", response_model=LogsQueryResponse)
def get_logs(
    trace_id: str | None = None,
    level: str | None = None,
    provider: Provider | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> LogsQueryResponse:
    rows, total = log_repo.query_logs(
        trace_id=trace_id,
        level=level,
        provider=provider,
        task_id=task_id,
        session_id=session_id,
        start_at=start_at,
        end_at=end_at,
        page=page,
        page_size=page_size,
    )
    return LogsQueryResponse(
        page=page,
        page_size=page_size,
        total=total,
        items=[
            LogItemResponse(
                id=row.id,
                trace_id=row.trace_id,
                level=row.level,
                provider=row.provider,
                task_id=row.task_id,
                session_id=row.session_id,
                event=row.event,
                message=row.message,
                created_at=row.created_at,
            )
            for row in rows
        ],
    )
