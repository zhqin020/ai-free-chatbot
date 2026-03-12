from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.browser.runtime_health import check_provider_runtime
from src.models.result import TaskResult
from src.models.task import TaskCreate, TaskRead
from src.parser import JSONValidator, ResponseExtractor
from src.storage.database import TaskORM
from src.storage.repositories import AttemptRepository, LogRepository, TaskRepository

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
task_repo = TaskRepository()
log_repo = LogRepository()
attempt_repo = AttemptRepository()
response_extractor = ResponseExtractor()
json_validator = JSONValidator()


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


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate) -> TaskRead:
    ok, error_message = check_provider_runtime(payload.provider_hint)
    if not ok:
        detail = error_message or "runtime_unavailable: provider runtime is not ready"
        log_repo.add_log(
            level="ERROR",
            provider=payload.provider_hint,
            event="task_rejected",
            message=detail,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )

    row = task_repo.create(payload)
    return _to_task_read(row)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: str) -> TaskRead:
    row = task_repo.get(task_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task not found: {task_id}",
        )
    return _to_task_read(row)


@router.get("/{task_id}/result", response_model=TaskResult)
def get_task_result(task_id: str) -> TaskResult:
    row = task_repo.get(task_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task not found: {task_id}",
        )

    raw_row = task_repo.get_latest_raw_response(task_id)
    extracted_row = task_repo.get_latest_extracted_result(task_id)

    error_message: str | None = None
    extracted_json = None
    provider = row.provider_hint
    raw_response = None

    if raw_row is not None:
        provider = raw_row.provider
        raw_response = raw_row.response_text
        try:
            payload = response_extractor.extract_json_candidate(raw_row.response_text)
            validated = json_validator.validate(payload)
            if validated.ok:
                extracted_json = validated.value
            else:
                error_message = f"validate_error: {validated.error_message}"
        except Exception as exc:
            error_message = f"extract_error: {exc}"

    if error_message is None and extracted_row is not None and extracted_row.extraction_error:
        error_message = extracted_row.extraction_error

    attempt_count = attempt_repo.get_attempt_count(task_id)
    retry_count = max(attempt_count - 1, 0)

    return TaskResult(
        task_id=row.id,
        status=row.status.value,
        provider=provider,
        raw_response=raw_response,
        extracted_json=extracted_json,
        error_message=error_message,
        retry_count=retry_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
