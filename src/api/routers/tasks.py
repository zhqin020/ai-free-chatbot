from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.models.task import TaskCreate, TaskRead
from src.storage.database import TaskORM
from src.storage.repositories import LogRepository, TaskRepository

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
task_repo = TaskRepository()
log_repo = LogRepository()


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
