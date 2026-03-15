import json
import pytest
from fastapi.testclient import TestClient
from src.storage.repositories import ProviderConfigRepository
from src.api.main import create_app

@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_notify_ready_auto_extract_and_adapter_read(client: TestClient):
    # 1. 发现 provider 和 session
    client.post("/api/sessions/discover")
    # 2. 模拟页面含典型 chat 元素（假定后端已集成 Playwright mock 或 patch）
    # 3. 调用 notify-ready
    resp = client.post("/api/sessions/s-mock_openai-1/notify-ready")
    assert resp.status_code == 200
    # 4. 检查 provider 表 ready_selectors_json 字段
    repo = ProviderConfigRepository()
    row = repo.get("mock_openai")
    assert row is not None
    selectors = json.loads(row.ready_selectors_json)
    assert "input_selector" in selectors
    assert "send_button_selector" in selectors
    # response_selector 可选，实际页面可能未检测到
    # 5. 检查 DefaultProviderAdapter 能正确读取
    from src.browser.providers.base import DefaultProviderAdapter
    adapter = DefaultProviderAdapter("mock_openai")
    assert adapter.input_selectors and adapter.send_button_selectors
