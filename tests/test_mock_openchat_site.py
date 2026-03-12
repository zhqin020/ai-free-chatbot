from __future__ import annotations

from fastapi.testclient import TestClient

from src.mock_openchat.site import build_mock_json_payload, create_app


def test_mock_site_home_contains_required_flow_and_selectors() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    body = response.text

    # Cookie -> human verification -> login flow hints
    assert "Cookie 设置" in body
    assert "Verify you are human" in body
    assert "Sign in" in body

    # Keep selectors compatible with OpenChatAdapter
    assert "data-testid=\"chat-input\"" in body
    assert "data-testid=\"send-button\"" in body
    assert "data-testid', 'assistant-message'" in body


def test_mock_json_payload_matches_required_template_keys() -> None:
    payload = build_mock_json_payload("case AB-42 请提取")

    assert payload["case_id"].startswith("AB-42")
    assert payload["case_status"] in {"结案", "正在进行"}
    assert payload["judgment_result"] in {"leave", "grant", "dismiss"}
    assert payload["hearing"] in {"yes", "no"}

    timeline = payload["timeline"]
    assert "filing_date" in timeline
    assert "Applicant_file_completed" in timeline
    assert "reply_memo" in timeline
    assert "Sent_to_Court" in timeline
    assert "judgment_date" in timeline


def test_mock_json_api_returns_template_payload() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/mock-json", params={"message": "2026-88 abc"})

    assert response.status_code == 200
    body = response.json()
    assert body["case_id"].endswith("###")
    assert "timeline" in body
