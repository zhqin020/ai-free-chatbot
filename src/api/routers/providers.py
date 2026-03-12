from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.models.provider import (
    ProviderClearSessionsResponse,
    ProviderConfigCreate,
    ProviderConfigRead,
    ProviderConfigUpdate,
    ProviderOpenResponse,
    ProviderSessionTargetResponse,
)
from src.models.session import Provider
from src.storage.database import ProviderConfigORM
from src.storage.repositories import ProviderConfigRepository, SessionRepository

router = APIRouter(prefix="/api/providers", tags=["providers"])
provider_repo = ProviderConfigRepository()
session_repo = SessionRepository()


def _map_session_provider(name: str) -> Provider | None:
    if name == "mock_openai":
        return Provider.OPENCHAT
    try:
        return Provider(name)
    except ValueError:
        return None


def _to_read(row: ProviderConfigORM) -> ProviderConfigRead:
    mapped = _map_session_provider(row.name)
    return ProviderConfigRead(
        name=row.name,
        url=row.url,
        icon=row.icon,
        builtin=row.name in provider_repo.DEFAULTS,
        session_provider=mapped.value if mapped else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[ProviderConfigRead])
def list_providers() -> list[ProviderConfigRead]:
    rows = provider_repo.list()
    return [_to_read(row) for row in rows]


@router.post("", response_model=ProviderConfigRead, status_code=status.HTTP_201_CREATED)
def create_provider(payload: ProviderConfigCreate) -> ProviderConfigRead:
    row = provider_repo.get(payload.name)
    if row is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"provider already exists: {payload.name}")
    created = provider_repo.upsert(payload.name, url=payload.url, icon=payload.icon)
    return _to_read(created)


@router.put("/{provider_name}", response_model=ProviderConfigRead)
def update_provider(provider_name: str, payload: ProviderConfigUpdate) -> ProviderConfigRead:
    row = provider_repo.get(provider_name)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"provider not found: {provider_name}")
    updated = provider_repo.upsert(provider_name, url=payload.url, icon=payload.icon)
    return _to_read(updated)


@router.delete("/{provider_name}")
def delete_provider(provider_name: str) -> dict[str, bool]:
    deleted = provider_repo.delete(provider_name)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"provider not found: {provider_name}")
    return {"deleted": True}


@router.post("/{provider_name}/open-browser", response_model=ProviderOpenResponse)
def open_provider(provider_name: str) -> ProviderOpenResponse:
    row = provider_repo.get(provider_name)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"provider not found: {provider_name}")
    return ProviderOpenResponse(name=row.name, url=row.url)


@router.post("/{provider_name}/clear-sessions", response_model=ProviderClearSessionsResponse)
def clear_provider_sessions(provider_name: str) -> ProviderClearSessionsResponse:
    row = provider_repo.get(provider_name)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"provider not found: {provider_name}")

    mapped = _map_session_provider(row.name)
    if mapped is None:
        return ProviderClearSessionsResponse(name=row.name, session_provider=None, cleared_count=0)

    cleared = session_repo.delete_by_provider(mapped)
    return ProviderClearSessionsResponse(name=row.name, session_provider=mapped.value, cleared_count=cleared)


@router.get("/{provider_name}/session-target", response_model=ProviderSessionTargetResponse)
def provider_session_target(provider_name: str) -> ProviderSessionTargetResponse:
    row = provider_repo.get(provider_name)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"provider not found: {provider_name}")

    mapped = _map_session_provider(row.name)
    if mapped is None:
        return ProviderSessionTargetResponse(name=row.name, session_provider=None, sessions_url="/admin/sessions")

    return ProviderSessionTargetResponse(
        name=row.name,
        session_provider=mapped.value,
        sessions_url=f"/admin/sessions?provider={mapped.value}",
    )
