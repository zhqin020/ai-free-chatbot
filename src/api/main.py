
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
print("sys.path:", sys.path)

from contextlib import asynccontextmanager
from pathlib import Path
# 顶层初始化 session_pool 单例，确保主进程唯一
from src.browser.session_pool import get_global_provider_session_pool
session_pool = get_global_provider_session_pool()
print(f"[main] session_pool singleton id={id(session_pool)} pid={os.getpid()} import_path={session_pool.__class__.__module__}")
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers.logs import router as logs_router
from .routers.metrics import router as metrics_router
from .routers.mock_openai import router as mock_openai_router
from .routers.providers import router as providers_router
from .routers.sessions import router as sessions_router
from .routers.test_extract import router as test_extract_router
from .routers.tasks import router as tasks_router
from .routers.worker import router as worker_router
from src.config import get_settings
from src.logging_mp import setup_logging
from src.storage.database import Base
from src.storage.database import init_db


from sqlalchemy import create_engine
# 主进程唯一 worker 线程池和调度器
from src.browser.worker import ThreadedWorkerManager
# worker_thread 启动前确保所有表结构已创建
engine = create_engine("sqlite:///data/app.db")
Base.metadata.create_all(engine)

# 全局唯一 worker 线程池和调度器（主进程内存）
worker_manager = ThreadedWorkerManager(providers=["openchat", "deepseek", "other_provider"])  # 可根据实际 provider 列表初始化 
from src.logging_mp import setup_logging, startlog

logger = startlog(__name__) 

def _open_admin():
    global logger
    import time
    import subprocess
    import shutil
    import webbrowser
    time.sleep(1)
    url = "http://localhost:8000/admin"
    # 优先用 WSL/类 Unix 浏览器
    browser_bins = [
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "microsoft-edge",
        "microsoft-edge-stable",
    ]
    for browser_bin in browser_bins:
        browser_path = shutil.which(browser_bin)
        if browser_path:
            try:
                logger.info(f' Open admin page in browser:{browser_path}, url:{url}...')
                subprocess.Popen([
                    browser_path,
                    "--password-store=basic",
                    "--new-window",
                    url,
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return
            except Exception:
                pass
    # fallback 到 xdg-open
    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        try:
            subprocess.Popen([xdg_open, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
    # fallback 到 webbrowser
    try:
        webbrowser.open_new_tab(url)
        logger.info(f' Open admin page in browser, url:{url}...')
    except Exception:
        pass

def create_app() -> FastAPI:
    global logger
    settings = get_settings()
    effective_level = settings.log_level.upper()
    if settings.app_env.lower() == "dev" and effective_level == "INFO":
        effective_level = "DEBUG"
    logger = setup_logging(
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

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db()
        # 启动所有 worker 线程，具体逻辑委托 worker.py
        from src.browser.worker import start_all_worker_threads
        start_all_worker_threads(logger=logger)
        yield

    logger.info(f'starting FastAPI...')
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.session_pool = session_pool
    app.mount("/ui", StaticFiles(directory=static_dir), name="ui")
    # ...existing code...

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

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return FileResponse(static_dir / "favicon.png")

    @app.get("/admin/query", include_in_schema=False)
    def admin_query() -> FileResponse:
        return FileResponse(static_dir / "admin-query.html")

    @app.get("/admin/test-extract", include_in_schema=False)
    def admin_test_extract() -> FileResponse:
        return FileResponse(static_dir / "admin-test-extract.html")


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





# 顶层 app 供主程序直接启动使用
app = create_app()

# 只允许通过 uvicorn 命令行或 ASGI server 启动本应用，禁止 main.py 内部再 fork/spawn 进程。
if __name__ == "__main__":
    from fastapi.middleware.cors import CORSMiddleware
    import threading, os

    # 允许跨域，便于本地管理页面开发
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 仅主进程且未被 uvicorn worker/fork 启动时才自动打开管理页面
    logger.info("[main] Open admin interface...")
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and os.getppid() != os.getpid():
        threading.Thread(target=_open_admin, daemon=True).start()

    logger.info("[main] 启动主程序，监听 0.0.0.0:8000 ...")
    print("[main] 请使用如下命令启动服务，确保全局对象唯一：")
    print("  python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 ")
    print("或用 gunicorn -k uvicorn.workers.UvicornWorker src.api.main:app")
    print("main.py 内部已禁止自动 fork/spawn uvicorn 进程，防止全局单例失效。")
