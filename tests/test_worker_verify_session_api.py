import pytest
import requests

@pytest.mark.asyncio
async def test_worker_verify_session():
    API_URL = "http://127.0.0.1:8000/api/worker/verify-session"
    payload = {
        "provider": "deepseek",
        "session_id": "s-deepseek-1",
        "url": "https://chat.deepseek.com/"
    }
    resp = requests.post(API_URL, json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["session_id"] == payload["session_id"]
    assert data["provider"] == payload["provider"]
    assert data["url"] == payload["url"]
    assert "worker" in data["message"]
