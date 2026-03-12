from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routers.logs import router as logs_router
from src.api.routers.metrics import router as metrics_router
from src.api.routers.sessions import router as sessions_router
from src.api.routers.test_extract import router as test_extract_router
from src.api.routers.tasks import router as tasks_router
from src.config import get_settings
from src.logger import setup_logging
from src.storage.database import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(tasks_router)
    app.include_router(sessions_router)
    app.include_router(test_extract_router)
    app.include_router(metrics_router)
    app.include_router(logs_router)
    return app


app = create_app()
