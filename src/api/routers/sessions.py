from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from src.api.browser_open_service import (
    ensure_runtime_cookie_in_server_browser,
    inspect_runtime_page_state_in_server_browser,
    open_page_in_server_browser,
)
from src.models.session import (
    Provider,
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
from src.storage.repositories import ProviderConfigRepository, SessionRepository, SessionTrackingRepository

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
session_repo = SessionRepository()
provider_repo = ProviderConfigRepository()
tracking_repo = SessionTrackingRepository()


def _to_session_read(row: SessionORM) -> SessionRead:
    ordinal_match = re.search(r"-(\d+)$", row.id)
    ordinal = ordinal_match.group(1) if ordinal_match else "1"
    session_name = f"{row.provider.value}-{ordinal}"

    tracking = tracking_repo.get(row.id)
    http_session_id = tracking.http_session_id if tracking is not None else None
    if tracking is None:
        tracking_repo.upsert(
            session_id=row.id,
            session_name=session_name,
            start_time=row.created_at,
            status=row.state.value,
            http_session_id=http_session_id,
        )
    else:
        tracking_repo.upsert(
            session_id=row.id,
            session_name=session_name,
            start_time=tracking.start_time,
            status=row.state.value,
            http_session_id=http_session_id,
        )

    return SessionRead(
        id=row.id,
        session_name=session_name,
        http_session_id=http_session_id,
        start_time=row.created_at,
        status=row.state.value,
        provider=row.provider,
        chat_url=row.chat_url,
        enabled=row.enabled,
        priority=row.priority,
        state=row.state,
        login_state=row.login_state,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _map_provider_name_to_session_provider(name: str) -> Provider | None:
    if name == "mock_openai":
        return Provider.OPENCHAT
    try:
        return Provider(name)
    except ValueError:
        return None


async def _probe_current_http_session_id(row: SessionORM) -> tuple[str | None, str | None, str | None]:
    extracted = await ensure_runtime_cookie_in_server_browser(
        key=row.id,
        url=row.chat_url,
        provider=row.provider.value,
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
        if mapped_provider is None:
            continue

        session_id = f"s-{provider_row.name}-1"
        existing = session_repo.get(session_id)
        config = SessionConfig(
            id=session_id,
            provider=mapped_provider,
            chat_url=provider_row.url,
            enabled=True,
            priority=existing.priority if existing is not None else (100 + index),
        )
        row = session_repo.upsert(config)
        ordinal_match = re.search(r"-(\d+)$", row.id)
        ordinal = ordinal_match.group(1) if ordinal_match else "1"
        previous_tracking = tracking_repo.get(row.id)
        tracking_repo.upsert(
            session_id=row.id,
            session_name=f"{row.provider.value}-{ordinal}",
            start_time=previous_tracking.start_time if previous_tracking is not None else row.created_at,
            status=row.state.value,
            http_session_id=previous_tracking.http_session_id if previous_tracking is not None else None,
        )
        discovered.append(_to_session_read(row))

    return discovered


@router.get("", response_model=list[SessionRead])
def list_sessions(enabled_only: bool = False) -> list[SessionRead]:
    rows = session_repo.list(enabled_only=enabled_only)
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
def mark_login_ok(session_id: str) -> SessionRead:
    updated = session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    tracking_repo.update_status(session_id, SessionState.READY.value)
    return _to_session_read(row)


@router.post("/{session_id}/notify-ready", response_model=SessionRead)
def notify_ready(session_id: str) -> SessionRead:
    # Alias for automation scripts: explicitly notify worker the session is human-ready.
    return mark_login_ok(session_id)


@router.post("/{session_id}/open", response_model=SessionOpenRead)
async def open_session(session_id: str) -> SessionOpenRead:
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")

    previous_tracking = tracking_repo.get(row.id)
    previous_http = previous_tracking.http_session_id if previous_tracking is not None else None
    _, current_http, _ = await _probe_current_http_session_id(row)

    requires_confirm = bool(previous_http and current_http and previous_http != current_http)
    warning = None
    if requires_confirm:
        warning = (
            "HTTP session changed. The stored session record may be expired. "
            "Please confirm rebuild before replacing this session record."
        )

    if current_http is not None:
        tracking_repo.update_http_session(row.id, current_http)

    opened, open_message = await open_page_in_server_browser(
        key=row.id,
        url=row.chat_url,
        provider=row.provider.value,
    )

    if opened:
        # Operator-triggered open implies human has prepared this session in browser.
        # Promote to READY to unblock scheduler; if still not actually ready,
        # worker will classify back to WAIT_LOGIN on next attempt.
        session_repo.update_state(row.id, SessionState.READY, login_state="logged_in")
        tracking_repo.update_status(row.id, SessionState.READY.value)
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
    tracking_repo.delete(old_id)
    rebuilt = session_repo.upsert(config)

    ordinal_match = re.search(r"-(\d+)$", rebuilt.id)
    ordinal = ordinal_match.group(1) if ordinal_match else "1"
    tracking_repo.upsert(
        session_id=rebuilt.id,
        session_name=f"{rebuilt.provider.value}-{ordinal}",
        start_time=rebuilt.created_at,
        status=rebuilt.state.value,
        http_session_id=None,
    )

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
        tracking_repo.update_http_session(row.id, None)
        return SessionHttpTrackingRead(
            session_id=row.id,
            tracked=False,
            source="browser_context",
            composed_session_id=None,
            updated_at=None,
        )

    composed = f"{row.id}#{digest}"
    tracking_repo.update_http_session(row.id, digest)
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
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    tracking = tracking_repo.get(session_id)
    stored_http = tracking.http_session_id if tracking is not None else None
    cookie_name, current_http, _ = await _probe_current_http_session_id(row)
    page_state = await inspect_runtime_page_state_in_server_browser(
        key=row.id,
        url=row.chat_url,
        provider=row.provider.value,
    )
    updated_at = datetime.now(UTC)

    if page_state is not None and not page_state.get("chat_ready", False):
        reason = _page_gate_reason(page_state)
        session_repo.update_state(session_id, SessionState.WAIT_LOGIN, login_state="need_login")
        tracking_repo.update_status(session_id, SessionState.WAIT_LOGIN.value)
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
            tracking_repo.update_status(session_id, SessionState.READY.value)
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
        tracking_repo.update_http_session(row.id, current_http)
        session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
        tracking_repo.update_status(session_id, SessionState.READY.value)
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
            tracking_repo.update_http_session(row.id, current_http)
            session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
            tracking_repo.update_status(session_id, SessionState.READY.value)
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
    tracking_repo.update_http_session(row.id, current_http)
    session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
    tracking_repo.update_status(session_id, SessionState.READY.value)
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
