
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routers.logs import router as logs_router
from src.api.routers.metrics import router as metrics_router
from src.api.routers.mock_openai import router as mock_openai_router
from src.api.routers.providers import router as providers_router
from src.api.routers.sessions import router as sessions_router
from src.api.routers.test_extract import router as test_extract_router
from src.api.routers.tasks import router as tasks_router
from src.api.routers.worker import router as worker_router
from src.config import get_settings
from src.logging_mp import setup_logging
from src.storage.database import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    effective_level = settings.log_level.upper()
    if settings.app_env.lower() == "dev" and effective_level == "INFO":
        effective_level = "DEBUG"
    setup_logging(
        name="api",
        cfg_json_str=(
            '{"level":"'
            + effective_level
            + '","output":"file, console","log_file":"api"}'
        ),
    )
    static_dir = Path(__file__).resolve().parent / "static"

    import threading
    import asyncio
    from src.browser.worker import SchedulerWorker

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db()
        # 启动 worker 主循环（后台线程，API/worker 合并进程）
        def worker_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            worker = SchedulerWorker()
            loop.run_until_complete(worker.run_forever())

        t = threading.Thread(target=worker_thread, name="WorkerThread", daemon=True)
        t.start()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.mount("/ui", StaticFiles(directory=static_dir), name="ui")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/admin/sessions", include_in_schema=False)
    def admin_sessions() -> FileResponse:
        return FileResponse(static_dir / "admin-sessions.html")

    @app.get("/admin", include_in_schema=False)
    def admin_home() -> FileResponse:
        return FileResponse(static_dir / "admin-home.html")

    @app.get("/admin/settings", include_in_schema=False)
    def admin_settings() -> FileResponse:
        return FileResponse(static_dir / "admin-settings.html")

    @app.get("/admin/query", include_in_schema=False)
    def admin_query() -> FileResponse:
        return FileResponse(static_dir / "admin-query.html")

    @app.get("/admin/test-extract", include_in_schema=False)
    def admin_test_extract() -> FileResponse:
        return FileResponse(static_dir / "admin-test-extract.html")

    @app.get("/admin/worker", include_in_schema=False)
    def admin_worker() -> FileResponse:
        return FileResponse(static_dir / "admin-worker.html")

    @app.get("/admin/mock-openai", include_in_schema=False)
    def admin_mock_openai() -> FileResponse:
        return FileResponse(static_dir / "admin-mock-openai.html")



    @app.get("/admin/auto-script-gen", include_in_schema=False)
    def admin_auto_script_gen() -> FileResponse:
        return FileResponse(static_dir / "admin-auto-script-gen.html")

    app.include_router(tasks_router)
    app.include_router(sessions_router)
    app.include_router(providers_router)
    app.include_router(test_extract_router)
    app.include_router(worker_router)
    app.include_router(mock_openai_router)
    app.include_router(metrics_router)
    app.include_router(logs_router)
    return app


app = create_app()
