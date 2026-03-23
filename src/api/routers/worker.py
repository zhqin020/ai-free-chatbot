
from fastapi import Body, Query
from fastapi import APIRouter
from pydantic import BaseModel
from src.storage.repositories import SessionRepository
from src.browser.session_pool import get_global_provider_session_pool

from src.logging_mp import setup_logging, startlog
logger = startlog('routers.worker')

# 注册 worker 路由
router = APIRouter(prefix="/api/worker", tags=["worker"])

# 会话验证请求模型
class VerifySessionRequest(BaseModel):
    provider: str
    session_id: str
    url: str

# 会话验证响应模型
class VerifySessionResponse(BaseModel):
    ok: bool
    message: str
    session_id: str
    provider: str
    url: str


from src.browser.worker import WorkerCommand, WorkerCommandResult, put_command, get_command_result
import uuid


@router.post("/verify-session", response_model=VerifySessionResponse)
async def verify_session(req: VerifySessionRequest = Body(...)) -> VerifySessionResponse:
    """
    由 worker 线程处理页面操作，API 线程仅写入命令队列并等待结果。
    无论 session 是否存在，均下发 verify_session 命令，由 worker 线程自动拉起/修复 session 并写入 owner。
    """
    try:
        # 1. 查询 session 记录，若无 owner 则选择 provider 对应的 worker 线程
        session_repo = SessionRepository()
        session_row = session_repo.get(req.session_id)
        if session_row and getattr(session_row, 'owner', None):
            target_thread_id = str(session_row.owner)
        else:
            from threading import enumerate as thread_enumerate
            threads = list(thread_enumerate())
            target_thread_id = None
            for t in threads:
                if t.name == f"WorkerThread-{req.provider}" and getattr(t, 'ident', None):
                    target_thread_id = str(t.ident)
                    break
            
            if not target_thread_id:
                from src.storage.repositories import ProviderConfigRepository
                provider_row = ProviderConfigRepository().get(req.provider)
                if not provider_row or not getattr(provider_row, 'enable', True):
                    return VerifySessionResponse(
                        ok=False,
                        message=f"provider is disabled: {req.provider}",
                        session_id=req.session_id,
                        provider=req.provider,
                        url=req.url,
                    )
                logger.info(f"[worker] dynamically starting worker thread for provider={req.provider}...")
                from src.browser.worker import start_worker_thread
                new_t = start_worker_thread(req.provider, logger)
                target_thread_id = str(new_t.ident)
        command_id = uuid.uuid4().hex
        command = WorkerCommand(
            command_id=command_id,
            command_type="verify_session",
            params={
                "provider": req.provider,
                "session_id": req.session_id,
                "url": req.url,
            },
            target_thread_id=target_thread_id,
            session_id=req.session_id,
        )
        put_command(command)
        logger.info(f"[worker] verify-session enqueued: command_id={command_id} target_thread_id={target_thread_id}")
        # 2. 阻塞等待 worker 线程处理结果
        result: WorkerCommandResult | None = get_command_result(command_id, timeout=10.0)
        if result is None:
            return VerifySessionResponse(
                ok=False,
                message="worker 线程处理超时或无响应",
                session_id=req.session_id,
                provider=req.provider,
                url=req.url,
            )
        if result.status == "success":
            return VerifySessionResponse(
                ok=True,
                message="会话页面已由 worker 线程创建/激活，可复用",
                session_id=req.session_id,
                provider=req.provider,
                url=req.url,
            )
        else:
            return VerifySessionResponse(
                ok=False,
                message=result.error_message or "worker 线程处理失败",
                session_id=req.session_id,
                provider=req.provider,
                url=req.url,
            )
    except Exception as exc:
        logger.error(f"[worker] verify-session error: {exc}")
        return VerifySessionResponse(
            ok=False,
            message=f"worker verify-session 异常: {exc}",
            session_id=req.session_id,
            provider=req.provider,
            url=req.url,
        )


import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_TMP_DIR = _REPO_ROOT / "tmp"
_LOG_DIR = _REPO_ROOT / "logs"
_STATE_FILE = _TMP_DIR / "worker_manager_state.json"
_WORKER_LOG_FILE = _LOG_DIR / "worker-managed.log"
_STATE_LOCK = threading.Lock()


class WorkerStatusResponse(BaseModel):
    running: bool
    pid: int | None = None
    managed_by_api: bool = False
    started_at: datetime | None = None
    uptime_seconds: int | None = None
    command: str | None = None
    message: str | None = None


class WorkerActionResponse(BaseModel):
    action: str
    status: WorkerStatusResponse





from fastapi import Query
from typing import List

class SessionPoolEntryInfo(BaseModel):
    key: str
    url: str
    thread_id: int

@router.get("/session-pool-entries", response_model=List[SessionPoolEntryInfo])
def get_session_pool_entries(provider: str = Query(None)) -> List[SessionPoolEntryInfo]:
    """
    查询当前 worker 进程内存中的 session pool entries
    """
    pool = get_global_provider_session_pool()
    logger.info(f"[worker] session-pool-entries called: provider={provider}, entries={list(pool._entries.keys())}")
    entries = []
    for key, entry in pool._entries.items():
        if provider is None or key == provider or key.startswith(f"{provider}:"):
            entries.append(SessionPoolEntryInfo(key=key, url=entry.url, thread_id=entry.thread_id))
    return entries
