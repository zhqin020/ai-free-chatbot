from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.models.session import Provider, SessionConfig, SessionRead, SessionState, SessionUpdate
from src.storage.database import SessionORM
from src.storage.repositories import ProviderConfigRepository, SessionRepository

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
session_repo = SessionRepository()
provider_repo = ProviderConfigRepository()


def _to_session_read(row: SessionORM) -> SessionRead:
    return SessionRead(
        id=row.id,
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


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionConfig) -> SessionRead:
    row = session_repo.upsert(payload)
    return _to_session_read(row)


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
            enabled=existing.enabled if existing is not None else True,
            priority=existing.priority if existing is not None else (100 + index),
        )
        row = session_repo.upsert(config)
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
    row = session_repo.upsert(
        SessionConfig(
            id=session_id,
            provider=payload.provider,
            chat_url=payload.chat_url,
            enabled=payload.enabled,
            priority=payload.priority,
        )
    )
    return _to_session_read(row)


@router.delete("/{session_id}")
def delete_session(session_id: str) -> dict[str, bool]:
    deleted = session_repo.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    return {"deleted": True}


@router.post("/{session_id}/mark-login-ok", response_model=SessionRead)
def mark_login_ok(session_id: str) -> SessionRead:
    updated = session_repo.update_state(session_id, SessionState.READY, login_state="logged_in")
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    return _to_session_read(row)


@router.post("/{session_id}/notify-ready", response_model=SessionRead)
def notify_ready(session_id: str) -> SessionRead:
    # Alias for automation scripts: explicitly notify worker the session is human-ready.
    return mark_login_ok(session_id)


@router.post("/{session_id}/open")
def open_session(session_id: str) -> dict[str, str]:
    row = session_repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"session not found: {session_id}")
    return {"session_id": row.id, "chat_url": row.chat_url}
