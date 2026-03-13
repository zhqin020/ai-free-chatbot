import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.models.task import TaskStatus
from src.storage.repositories import SessionRepository
from src.models.session import SessionState

client = TestClient(app)

def test_task_status_critical(monkeypatch):
    # patch SessionRepository.list 静态方法，确保接口调用时返回空
    monkeypatch.setattr(SessionRepository, "list", lambda self, enabled_only=True: [])
    # 创建任务
    resp = client.post("/api/tasks", json={
        "prompt": "test", "document_text": "doc"
    })
    assert resp.status_code == 201
    task_id = resp.json()["id"]
    # 查询任务状态
    resp2 = client.get(f"/api/tasks/{task_id}")
    assert resp2.status_code == 200
    assert resp2.json()["status"] == TaskStatus.CRITICAL
