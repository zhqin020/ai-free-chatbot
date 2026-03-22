# worker_api_server.py
# 启动 worker API 独立进程，监听 8000 端口
import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
