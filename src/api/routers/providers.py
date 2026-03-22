from __future__ import annotations

from fastapi import APIRouter, HTTPException, status


from src.models.provider import (
    ProviderConfigCreate,
    ProviderConfigRead,
    ProviderConfigUpdate,
    ProviderOpenResponse,
    ProviderClearSessionsResponse,
    ProviderSessionTargetResponse,
    AppParamRead,
    AppParamUpdate,
)

from src.storage.database import ProviderConfigORM
from src.storage.repositories import ProviderConfigRepository, SessionRepository, AppParamRepository

router = APIRouter(prefix="/api/providers", tags=["providers"])
provider_repo = ProviderConfigRepository()
session_repo = SessionRepository()
app_param_repo = AppParamRepository()


def _map_session_provider(name: str) -> str | None:
    # 直接返回自身，保持 provider 名称全链路一致
    return name if name else None


def _to_read(row: ProviderConfigORM) -> ProviderConfigRead:
    mapped = _map_session_provider(row.name)
    return ProviderConfigRead(
        name=row.name,
        url=row.url,
        icon=row.icon,
        builtin=row.name in provider_repo.DEFAULTS,
        session_provider=mapped if mapped else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[ProviderConfigRead])
def list_providers() -> list[ProviderConfigRead]:
    rows = provider_repo.list()
    return [_to_read(row) for row in rows]


@router.get("/app-params", response_model=AppParamRead)
def get_app_params() -> AppParamRead:
    row = app_param_repo.get()
    return AppParamRead(mode=row.mode, max_chat_rounds=row.max_chat_rounds, updated_at=row.updated_at)


@router.put("/app-params", response_model=AppParamRead)
def update_app_params(payload: AppParamUpdate) -> AppParamRead:
    updated = app_param_repo.update_config(
        mode=payload.mode.value if payload.mode else None,
        max_chat_rounds=payload.max_chat_rounds
    )
    return AppParamRead(mode=updated.mode, max_chat_rounds=updated.max_chat_rounds, updated_at=updated.updated_at)


@router.post("", response_model=ProviderConfigRead, status_code=status.HTTP_201_CREATED)
def create_provider(payload: ProviderConfigCreate) -> ProviderConfigRead:
    row = provider_repo.get(payload.name)
    if row is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"provider already exists: {payload.name}")
    created = provider_repo.upsert(payload.name, url=payload.url, icon=payload.icon)
    # 新增 provider 后自动 discover session，保持同步
    from src.api.routers.sessions import discover_sessions
    discover_sessions()
    return _to_read(created)


@router.put("/{provider_name}", response_model=ProviderConfigRead)
def update_provider(provider_name: str, payload: ProviderConfigUpdate) -> ProviderConfigRead:
    row = provider_repo.get(provider_name)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"provider not found: {provider_name}")
    updated = provider_repo.upsert(provider_name, url=payload.url, icon=payload.icon)
    # provider 更新后自动 discover session，保持同步
    from src.api.routers.sessions import discover_sessions
    discover_sessions()
    return _to_read(updated)


@router.delete("/{provider_name}")
def delete_provider(provider_name: str) -> dict[str, bool]:
    if provider_name in provider_repo.DEFAULTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"builtin provider cannot be deleted: {provider_name}",
        )

    deleted = provider_repo.delete(provider_name)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"provider not found: {provider_name}")

    # 自动清理相关 session
    cleared_count = session_repo.delete_by_provider(provider_name)
    return {"deleted": True, "sessions_cleared": cleared_count}


@router.post("/{provider_name}/open-browser", response_model=ProviderOpenResponse)
async def open_provider(provider_name: str) -> ProviderOpenResponse:
    row = provider_repo.get(provider_name)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"provider not found: {provider_name}")

    mapped = _map_session_provider(row.name)
    if mapped is not None:
        # Reuse the same profile namespace as session/worker to preserve login state.
        browser_key = f"s-{row.name}-1"
        browser_provider = mapped
    else:
        browser_key = f"provider-{row.name}"
        browser_provider = row.name

    # 自动调用 worker API 拉起 provider 页面
    import httpx
    verify_req = {
        "provider": browser_provider,
        "session_id": browser_key,
        "url": row.url,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("http://localhost:8000/api/worker/verify-session", json=verify_req)
            data = resp.json()
            open_message = data.get("message", "worker API 未返回结果")
            opened = data.get("ok", False)
    except Exception as exc:
        open_message = f"worker API 调用失败: {exc}"
        opened = False
    return ProviderOpenResponse(
        name=row.name,
        url=row.url,
        opened_in_server=opened,
        open_message=open_message,
    )


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
        session_provider=mapped,
        sessions_url=f"/admin/sessions?provider={mapped}",
    )
