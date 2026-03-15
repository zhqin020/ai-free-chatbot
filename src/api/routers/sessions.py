from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime

import asyncio


logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, status
import asyncio

from src.api.browser_open_service import (
    ensure_runtime_cookie_in_server_browser,
    inspect_runtime_page_state_in_server_browser,
    open_page_in_server_browser,
)
from src.models.session import (
    SessionConfig,
    SessionHttpTrackingRead,
    SessionOpenRead,
    SessionRebuildRead,
    SessionRead,
    SessionStatsRead,
    SessionState,
    SessionUpdate,
    SessionVerifyRead,
)
from src.storage.database import SessionORM
from src.storage.repositories import ProviderConfigRepository, SessionRepository

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
session_repo = SessionRepository()
provider_repo = ProviderConfigRepository()


def _to_session_read(row: SessionORM) -> SessionRead:
    return SessionRead(
        id=row.id,
        http_session_id=row.http_session_id,
        provider=row.provider,
        chat_url=row.chat_url,
        state=row.state,
        login_state=row.login_state,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _map_provider_name_to_session_provider(name: str) -> str | None:
    # 现在所有 provider 直接用 str
    return name


async def _probe_current_http_session_id(row: SessionORM) -> tuple[str | None, str | None, str | None]:
    extracted = await ensure_runtime_cookie_in_server_browser(
        
        key=row.id,
        url=row.chat_url,
        provider=getattr(row.provider, 'value', row.provider),
    )
    source = "browser_context"
    if extracted is None:
        return None, None, None
    cookie_name, cookie_value = extracted
    digest = hashlib.sha256(cookie_value.encode("utf-8")).hexdigest()[:12]
    return cookie_name, digest, source


def _page_gate_reason(page_state: dict[str, bool]) -> str:
    if page_state.get("cookie_required"):
        return "cookie consent required"
    if page_state.get("verification_required"):
        return "human verification required"
    if page_state.get("login_required"):
        return "login required"
    return "chat window is not ready"


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionConfig) -> SessionRead:
    _ = payload
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="manual session create is disabled; use POST /api/sessions/discover",
    )


@router.post("/discover", response_model=list[SessionRead])
def discover_sessions() -> list[SessionRead]:
    provider_rows = provider_repo.list()
    discovered: list[SessionRead] = []

    for index, provider_row in enumerate(provider_rows, start=1):
        mapped_provider = _map_provider_name_to_session_provider(provider_row.name)
        # 支持动态provider：只要有name就允许创建
        session_id = f"s-{provider_row.name}-1"
        existing = session_repo.get(session_id)
        config = SessionConfig(
            id=session_id,
            provider=mapped_provider,
            chat_url=provider_row.url,
        )
        row = session_repo.upsert(config)
        discovered.append(_to_session_read(row))

    return discovered


@router.get("", response_model=list[SessionRead])
def list_sessions() -> list[SessionRead]:
    rows = session_repo.list()
    return [_to_session_read(row) for row in rows]


@router.get("/{session_id}", response_model=SessionRead)
def get_session(session_id: str) -> SessionRead:
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    return _to_session_read(row)


@router.put("/{session_id}", response_model=SessionRead)
def update_session(session_id: str, payload: SessionUpdate) -> SessionRead:
    _ = session_id
    _ = payload
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="manual session update is disabled; update provider settings then run discover",
    )


@router.delete("/{session_id}")
def delete_session(session_id: str) -> dict[str, bool]:
    _ = session_id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="manual session delete is disabled; use provider clear-sessions action",
    )


@router.post("/{session_id}/mark-login-ok", response_model=SessionRead)
async def mark_login_ok(session_id: str) -> SessionRead:
    updated = session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    # 自动提取 chat selector 并写入 provider
    provider = row.provider
    chat_url = row.chat_url
    from src.api.browser_open_service import _open_pool
    try:
        page = await _open_pool.get_page(session_id=row.id, url=chat_url, provider=provider)
        selectors = await auto_extract_chat_selectors(page)
        provider_repo.update_ready_selectors(provider, selectors)
    except Exception as e:
        logger.warning(f"[mark_login_ok] auto extract selectors failed: {e}")
    return _to_session_read(row)

# 辅助函数：自动提取 chat 页面 selector
async def auto_extract_chat_selectors(page):
    selectors = {}
    # 1. 输入框 selector
    input_candidates = [
        "textarea",
        "input[type='text']",
        "[contenteditable='true']",
        "textarea[aria-label]",
        "input[aria-label]",
    ]
    for sel in input_candidates:
        try:
            el = page.locator(sel).first
            if await el.is_visible():
                selectors["input_selector"] = sel
                break
        except Exception:
            continue
    # 2. 发送按钮 selector
    send_candidates = [
        "button:has-text('发送')",
        "button:has-text('Send')",
        "button[aria-label*='send' i]",
        "button[type='submit']",
    ]
    for sel in send_candidates:
        try:
            el = page.locator(sel).first
            if await el.is_visible():
                selectors["send_button_selector"] = sel
                break
        except Exception:
            continue
    # 3. 响应区域 selector
    response_candidates = [
        ".message, .response, .chat-message",
        "div[role='log']",
        "div[aria-live]",
        "article",
    ]
    for sel in response_candidates:
        try:
            el = page.locator(sel).first
            if await el.is_visible():
                selectors["response_selector"] = sel
                break
        except Exception:
            continue
    return selectors


@router.post("/{session_id}/open", response_model=SessionOpenRead)
async def open_session(session_id: str) -> SessionOpenRead:
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")

    # 检查 provider 是否存在
    provider_row = provider_repo.get(row.provider)
    if provider_row is None:
        # 自动删除该 session
        session_repo.delete(session_id)
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=f"provider '{row.provider}' 已被删除，当前会话已自动清理")

    previous_http = row.http_session_id
    _, current_http, _ = await _probe_current_http_session_id(row)

    requires_confirm = bool(previous_http and current_http and previous_http != current_http)
    warning = None
    if requires_confirm:
        warning = (
            "HTTP session changed. The stored session record may be expired. "
            "Please confirm rebuild before replacing this session record."
        )

    if current_http is not None:
        session_repo.update_http_session(row.id, current_http)

    opened, open_message = await open_page_in_server_browser(
        key=row.id,
        url=row.chat_url,
        provider=row.provider,
    )

    if opened:
        # Operator-triggered open implies human has prepared this session in browser.
        # Promote to READY to unblock scheduler; if still not actually ready,
        # worker will classify back to WAIT_LOGIN on next attempt.
        session_repo.update_state(row.id, SessionState.READY, login_state="logged_in")
    else:
        warning = f"{warning} | {open_message}" if warning else open_message

    return SessionOpenRead(
        session_id=row.id,
        chat_url=row.chat_url,
        previous_http_session_id=previous_http,
        current_http_session_id=current_http,
        requires_rebuild_confirmation=requires_confirm,
        warning=warning,
    )


@router.post("/{session_id}/rebuild", response_model=SessionRebuildRead)
def rebuild_session(session_id: str) -> SessionRebuildRead:
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")

    old_id = row.id
    config = SessionConfig(
        id=row.id,
        provider=row.provider,
        chat_url=row.chat_url,
        enabled=row.enabled,
        priority=row.priority,
    )

    session_repo.delete(old_id)
    rebuilt = session_repo.upsert(config)

    return SessionRebuildRead(
        old_session_id=old_id,
        rebuilt_session_id=rebuilt.id,
        message="session record rebuilt after HTTP session change confirmation",
    )


@router.get("/{session_id}/http-session", response_model=SessionHttpTrackingRead)
async def probe_http_session(session_id: str) -> SessionHttpTrackingRead:
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")

    cookie_name, digest, source = await _probe_current_http_session_id(row)
    if digest is None:
        session_repo.update_http_session(row.id, None)
        return SessionHttpTrackingRead(
            session_id=row.id,
            tracked=False,
            source="browser_context",
            composed_session_id=None,
            updated_at=None,
        )

    composed = f"{row.id}#{digest}"
    session_repo.update_http_session(row.id, digest)
    updated_at = datetime.now(UTC)
    return SessionHttpTrackingRead(
        session_id=row.id,
        tracked=True,
        source=source or "browser_context",
        cookie_name=cookie_name,
        composed_session_id=composed,
        updated_at=updated_at,
    )


@router.post("/{session_id}/verify", response_model=SessionVerifyRead)
async def verify_session(session_id: str) -> SessionVerifyRead:
    # 健康检查：页面对象未关闭，但内容异常时仅记录日志
    from src.browser.browser_controller import BrowserController
    from src.browser.session_pool import BrowserSessionPool
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")

    # 检查 provider 是否存在
    provider_row = provider_repo.get(row.provider)
    if provider_row is None:
        session_repo.delete(session_id)
        return SessionVerifyRead(
            session_id=row.id,
            valid=False,
            deleted=True,
            reason=f"provider '{row.provider}' 已被删除，会话已自动清理",
            stored_http_session_id=None,
            current_http_session_id=None,
            tracked=False,
            updated_at=datetime.now(UTC),
        )
    try:
        from src.api.browser_open_service import _open_pool
        key = _open_pool._make_key(row.provider, row.id)
        entry = _open_pool._entries.get(key)
        if entry is not None and not entry.page.is_closed():
            required_selector = _open_pool.required_selector or None
            if required_selector:
                healthy = await entry.controller.is_page_healthy(entry.page, required_selector=required_selector)
                if not healthy:
                    logger.error(f"Session page unhealthy: session_id=%s provider=%s url=%s selector=%s", row.id, row.provider, entry.url, required_selector)
    except Exception as exc:
        logger.error(f"Session health check error: session_id=%s provider=%s error=%s", row.id, row.provider, exc)
    stored_http = row.http_session_id
    cookie_name, current_http, _ = await _probe_current_http_session_id(row)
    page_state = await inspect_runtime_page_state_in_server_browser(
        key=row.id,
        url=row.chat_url,
        provider=row.provider,
    )
    updated_at = datetime.now(UTC)
    logger.info(f"[verify_session] session_id={row.id} provider={row.provider} stored_http={stored_http} current_http={current_http} cookie_name={cookie_name} page_state={page_state}")

    if page_state is not None and not page_state.get("chat_ready", False):
        reason = _page_gate_reason(page_state)
        session_repo.update_state(session_id, SessionState.WAIT_LOGIN, login_state="need_login")
        return SessionVerifyRead(
            session_id=row.id,
            valid=False,
            deleted=False,
            reason=f"session not ready: {reason}",
            stored_http_session_id=stored_http,
            current_http_session_id=current_http,
            tracked=False,
            cookie_name=cookie_name,
            updated_at=updated_at,
        )

    # Rule 1: cannot probe current HTTP session -> report invalid, do not delete.
    if current_http is None:
        if page_state is not None and page_state.get("chat_ready", False):
            session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
            return SessionVerifyRead(
                session_id=row.id,
                valid=True,
                deleted=False,
                reason="session valid: chat window ready (cookie unavailable)",
                stored_http_session_id=stored_http,
                current_http_session_id=None,
                tracked=False,
                updated_at=updated_at,
            )
        return SessionVerifyRead(
            session_id=row.id,
            valid=False,
            deleted=False,
            reason="unable to verify: no current HTTP session tracked",
            stored_http_session_id=stored_http,
            current_http_session_id=None,
            tracked=False,
            updated_at=updated_at,
        )

    # Rule 2: first successful tracking (no stored id yet) -> initialize and keep.
    if stored_http is None:
        session_repo.update_http_session(row.id, current_http)
        session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
        return SessionVerifyRead(
            session_id=row.id,
            valid=True,
            deleted=False,
            reason="session valid: HTTP session initialized",
            stored_http_session_id=None,
            current_http_session_id=current_http,
            tracked=True,
            cookie_name=cookie_name,
            composed_session_id=f"{row.id}#{current_http}",
            updated_at=updated_at,
        )

    # Rule 3: mismatch means HTTP session changed.
    # Keep this endpoint non-destructive for operator workflows:
    # return invalid signal but do not force state downgrade here.
    if stored_http != current_http:
        if page_state is not None and page_state.get("chat_ready", False):
            session_repo.update_http_session(row.id, current_http)
            session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
            return SessionVerifyRead(
                session_id=row.id,
                valid=True,
                deleted=False,
                reason="session valid: HTTP session refreshed from browser state",
                stored_http_session_id=stored_http,
                current_http_session_id=current_http,
                tracked=True,
                cookie_name=cookie_name,
                composed_session_id=f"{row.id}#{current_http}",
                updated_at=updated_at,
            )
        return SessionVerifyRead(
            session_id=row.id,
            valid=False,
            deleted=False,
            reason="session changed: HTTP session differs from tracked record",
            stored_http_session_id=stored_http,
            current_http_session_id=current_http,
            tracked=False,
            updated_at=updated_at,
        )

    # Rule 4: consistent id -> valid.
    session_repo.update_http_session(row.id, current_http)
    session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
    return SessionVerifyRead(
        session_id=row.id,
        valid=True,
        deleted=False,
        reason="session valid: HTTP session matches record",
        stored_http_session_id=stored_http,
        current_http_session_id=current_http,
        tracked=True,
        cookie_name=cookie_name,
        composed_session_id=f"{row.id}#{current_http}",
        updated_at=updated_at,
    )


@router.get("/{session_id}/stats", response_model=SessionStatsRead)
def session_stats(session_id: str) -> SessionStatsRead:
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    return SessionStatsRead(
        session_id=row.id,
        implemented=False,
        interaction_count=None,
        message="stats for completed interactions is planned; will be linked to metrics in a later task",
    )
