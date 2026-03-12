from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from src.config import reset_settings_cache
from src.storage.database import init_db


@pytest.fixture
def client() -> Iterator[TestClient]:
    db_path = Path("tmp/test_test_extract_api.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["DB_URL"] = "sqlite:///tmp/test_test_extract_api.db"
    reset_settings_cache()
    init_db()

    from src.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_test_extract_success(client: TestClient) -> None:
    response = client.post(
        "/api/test/extract",
        json={
            "prompt": "请提取案件结构化信息",
            "document_text": "文书正文",
            "raw_response": '{"case_id":"IMM-3-24","case_status":"结案","judgment_result":"dismiss","hearing":"no","timeline":{"filing_date":"2024-01-01","Applicant_file_completed":"2024-04-02","reply_memo":"2024-05-01","Sent_to_Court":"2024-06-14","judgment_date":"2024-10-01"}}',
            "provider_hint": "openchat",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["extracted_json"]["case_id"] == "IMM-3-24"
    assert body["extracted_json"]["case_status"] == "结案"
    assert body["extracted_json"]["hearing"] == "no"
    assert body["validation_errors"] == []


def test_test_extract_fail_and_retry_prompt(client: TestClient) -> None:
    response = client.post(
        "/api/test/extract",
        json={
            "prompt": "请提取案件结构化信息",
            "document_text": "文书正文",
            "raw_response": "this is not json",
            "provider_hint": "gemini",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["retry_prompt"] is not None
    assert len(body["validation_errors"]) == 1
