from __future__ import annotations


from fastapi import APIRouter, HTTPException, status

from src.models.result import TaskResult
from src.models.task import TaskCreate, TaskPollRead, TaskRead
from src.models.session import SessionState
from src.parser import ResponseExtractor
from src.storage.database import TaskORM
from src.storage.repositories import (
    AttemptRepository,
    LogRepository,
    SessionRepository,
    AppParamRepository,
    TaskRepository,
)


router = APIRouter(prefix="/api/tasks", tags=["tasks"])
task_repo = TaskRepository()
session_repo = SessionRepository()
attempt_repo = AttemptRepository()
log_repo = LogRepository()
response_extractor = ResponseExtractor()
dispatch_repo = AppParamRepository()
SessionState = SessionState

# 启动时自动清空 tasks 表，防止历史任务被 worker 处理
def _purge_all_tasks():
    from src.storage.database import session_scope, TaskORM
    with session_scope() as session:
        session.query(TaskORM).delete()
        session.flush()
_purge_all_tasks()

from src.logging_mp import setup_logging, startlog
from datetime import datetime
import threading

logger = startlog(__name__)

_rr_lock = threading.Lock()
_rr_cursor = 0

def _to_task_read(row: TaskORM) -> TaskRead:
    latest_trace_id = log_repo.get_latest_trace_id(row.id)
    return TaskRead(
        id=row.id,
        status=row.status,
        external_id=row.external_id,
        latest_trace_id=latest_trace_id,
        owner=getattr(row, 'owner', None),
        session_id=getattr(row, 'session_id', None),
        provider=getattr(row, 'provider', None),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _build_task_payload(row: TaskORM) -> TaskPollRead:
    raw_row = task_repo.get_latest_raw_response(row.id)
    extracted_row = task_repo.get_latest_extracted_result(row.id)

    error_message: str = ""
    extracted_json: dict = {}
    provider = getattr(row, 'provider', None) or ""
    raw_response = ""

    if raw_row is not None:
        provider = raw_row.provider or provider
        raw_response = raw_row.response_text or ""
        try:
            extracted = response_extractor.extract_json_candidate(raw_row.response_text)
            if extracted is not None:
                extracted_json = extracted
        except Exception as exc:
            error_message = f"extract_error: {exc}"

    if not error_message and extracted_row is not None and extracted_row.extraction_error:
        error_message = extracted_row.extraction_error or ""

    attempt_count = attempt_repo.get_attempt_count(row.id)
    retry_count = max(attempt_count - 1, 0)

    latest_trace_id = log_repo.get_latest_trace_id(row.id)
    # 确保 status 类型为 TaskStatus（枚举），防止字符串混入
    from src.models.task import TaskStatus as TaskStatusEnum
    status = getattr(row, 'status', None)
    if not isinstance(status, TaskStatusEnum):
        try:
            status = TaskStatusEnum(status)
        except Exception:
            status = TaskStatusEnum.CRITICAL
    # created_at/updated_at 必须为 datetime 且不为 None
    created_at = getattr(row, 'created_at', None)
    updated_at = getattr(row, 'updated_at', None)
    if not isinstance(created_at, datetime) or created_at is None:
        created_at = datetime.now()
    if not isinstance(updated_at, datetime) or updated_at is None:
        updated_at = datetime.now()
    # 其它字段类型安全
    # provider 字段优先 row.provider，保证为 str，兼容所有 provider
    prov = getattr(row, 'provider', None) or provider or ""
    if prov is not None and not isinstance(prov, str):
        prov = str(prov)

    logger.debug(f'[_build_task_payload] row:{row}, status:{status},provider:{prov}, row_response:{raw_response}, extracted_json:{extracted_json}')
    return TaskPollRead(
        id=str(row.id),
        status=status,
        owner=getattr(row, 'owner', None) or "",
        session_id=getattr(row, 'session_id', None) or "",
        external_id=getattr(row, 'external_id', None) or "",
        latest_trace_id=latest_trace_id or "",
        provider=prov,
        raw_response=raw_response,
        extracted_json=extracted_json,
        error_message=error_message,
        retry_count=int(retry_count) if retry_count is not None else 0,
        created_at=created_at,
        updated_at=updated_at,
    )


def _all_sessions_unhealthy_or_unavailable(request) -> bool:
    session_repo = SessionRepository()
    sessions = session_repo.list()
    if not sessions:
        return True
    pool = getattr(request.app.state, 'session_pool', None)
    if pool is None:
        raise RuntimeError('session_pool must be injected via app.state.session_pool')
    for s in sessions:
        key = s.provider  # provider 作为唯一 key，无需 make_key
        entry = pool._entries.get(key)
        if entry is not None:
            return False
    return True


from fastapi import Request

@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)

def create_task(payload: TaskCreate, request: Request) -> TaskRead:
    """
    任务分派去中心化：
    - 遍历 session_pool，选第一个健康 session，将其 thread_id 赋值给 owner 字段
    - 若无可用 session，依然入库，status=CRITICAL，owner/session_id/provider 允许为 None
    """
    import threading
    session_repo = SessionRepository()
    sessions = session_repo.list()
    from src.browser.session_pool import get_global_provider_session_pool
    pool = get_global_provider_session_pool()
    ready_entries = []
    busy_entries = []
    if pool is not None and sessions:
        for s in sessions:
            key = s.provider  # provider 作为唯一 key，无需 make_key
            entry = pool._entries.get(key)
            if entry is not None:
                # 避免在 API 线程跨线程访问 Playwright page
                ready_entries.append(entry)
    # 分配策略：优先 READY，若无则 BUSY，均使用轮询
    logger.info(f"[create_task] READY sessions count:{len(ready_entries)}, BUSY sessions count:{len(busy_entries)}")
    target_entry = None
    global _rr_cursor

    if len(ready_entries) > 0:
        with _rr_lock:
            _rr_cursor = (_rr_cursor + 1) % len(ready_entries)
            target_entry = ready_entries[_rr_cursor]
    elif len(busy_entries) > 0:
        with _rr_lock:
            _rr_cursor = (_rr_cursor + 1) % len(busy_entries)
            target_entry = busy_entries[_rr_cursor]

    # 补全 owner、session_id、provider 字段
    if target_entry is not None:
        logger.info(
            f"[create_task] target_entry: "
            f"session_id={getattr(target_entry, 'session_id', None)}, "
            f"provider={getattr(target_entry, 'provider', None)}, "
            f"thread_id={getattr(target_entry, 'thread_id', None)}, "
            f"page={getattr(target_entry, 'page', None)}"
        )
        payload.owner = str(getattr(target_entry, 'thread_id', None))
        payload.session_id = getattr(target_entry, 'session_id', None)
        payload.provider = getattr(target_entry, 'provider', None)
        status = None  # 用默认 PENDING
    else:
        logger.info("[create_task] target_entry: None (无可用 session，任务将以 CRITICAL 状态入库)")
        payload.owner = None
        payload.session_id = None
        payload.provider = None
        status = "CRITICAL"

    # 入库，始终生成 TaskORM
    row = task_repo.create(payload)
    # 如果无可用 session，需立即将 status 设为 CRITICAL
    if status == "CRITICAL":
        row.status = "CRITICAL"
        from src.storage.database import session_scope
        with session_scope() as session:
            db_row = session.get(type(row), row.id)
            if db_row:
                db_row.status = "CRITICAL"
                session.flush()
    logger.info(f"[create_task] 任务已入库: task_id={row.id} owner={row.owner} session_id={row.session_id} provider={row.provider} status={row.status} 当前API线程={threading.get_ident()}")
    return _to_task_read(row)


@router.get("/{task_id}", response_model=TaskPollRead)
def get_task(task_id: str, request: Request) -> TaskPollRead:
    import traceback
    try:
        row = task_repo.get(task_id)
        if row is None:
            logger.error(f"[get_task] 404: task not found: {task_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"task not found: {task_id}",
            )
        payload = _build_task_payload(row)
        # 仅在任务未完成时，才根据 session 健康情况设置为 CRITICAL
        if payload.status in ("PENDING", "DISPATCHED", "EXTRACTING"):
            if _all_sessions_unhealthy_or_unavailable(request):
                payload.status = "CRITICAL"
        # 日志提前，确保422前输出
        try:
            print(f"[debug-get_task] payload dict: {payload.dict()}")
            print(f"[debug-get_task] payload types: {{k: type(v) for k, v in payload.dict().items()}}")
            from pydantic import BaseModel
            print(f"[debug-get_task] TaskPollRead model fields: {list(TaskPollRead.__fields__.keys())}")
        except Exception as log_exc:
            print(f"[debug-get_task] log error: {log_exc}")
        return payload
    except Exception as e:
        import sys
        logger.error(f"[get_task] Exception: {e}\n{traceback.format_exc()}\nargs={locals()}\npython={sys.version}")
        raise HTTPException(status_code=500, detail=f"get_task internal error: {e}")


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
