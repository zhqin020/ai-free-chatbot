from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.models.result import TaskResult
from src.models.task import TaskCreate, TaskPollRead, TaskRead
from src.parser import ResponseExtractor
from src.storage.database import TaskORM
from src.storage.repositories import AttemptRepository, LogRepository, TaskRepository

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
task_repo = TaskRepository()
log_repo = LogRepository()
attempt_repo = AttemptRepository()
response_extractor = ResponseExtractor()


def _to_task_read(row: TaskORM) -> TaskRead:
    latest_trace_id = log_repo.get_latest_trace_id(row.id)
    return TaskRead(
        id=row.id,
        status=row.status,
        external_id=row.external_id,
        provider_hint=row.provider_hint,
        latest_trace_id=latest_trace_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _build_task_payload(row: TaskORM) -> TaskPollRead:
    raw_row = task_repo.get_latest_raw_response(row.id)
    extracted_row = task_repo.get_latest_extracted_result(row.id)

    error_message: str | None = None
    extracted_json = None
    provider = row.provider_hint
    raw_response = None

    if raw_row is not None:
        provider = raw_row.provider
        raw_response = raw_row.response_text
        try:
            extracted_json = response_extractor.extract_json_candidate(raw_row.response_text)
        except Exception as exc:
            error_message = f"extract_error: {exc}"

    if error_message is None and extracted_row is not None and extracted_row.extraction_error:
        error_message = extracted_row.extraction_error

    attempt_count = attempt_repo.get_attempt_count(row.id)
    retry_count = max(attempt_count - 1, 0)

    latest_trace_id = log_repo.get_latest_trace_id(row.id)
    return TaskPollRead(
        id=row.id,
        status=row.status,
        external_id=row.external_id,
        provider_hint=row.provider_hint,
        latest_trace_id=latest_trace_id,
        provider=provider,
        raw_response=raw_response,
        extracted_json=extracted_json,
        error_message=error_message,
        retry_count=retry_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate) -> TaskRead:
    row = task_repo.create(payload)
    return _to_task_read(row)


@router.get("/{task_id}", response_model=TaskPollRead)
def get_task(task_id: str) -> TaskPollRead:
    row = task_repo.get(task_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task not found: {task_id}",
        )
    return _build_task_payload(row)


@router.get("/{task_id}/result", response_model=TaskResult)
def get_task_result(task_id: str) -> TaskResult:
    row = task_repo.get(task_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task not found: {task_id}",
        )

    payload = _build_task_payload(row)

    return TaskResult(
        task_id=payload.id,
        status=payload.status.value,
        provider=payload.provider,
        raw_response=payload.raw_response,
        extracted_json=payload.extracted_json,
        error_message=payload.error_message,
        retry_count=payload.retry_count,
        created_at=payload.created_at,
        updated_at=payload.updated_at,
    )
