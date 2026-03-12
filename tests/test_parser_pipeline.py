from __future__ import annotations

from src.parser import JSONValidator, ResponseExtractor


def test_response_extractor_parses_fenced_json() -> None:
    text = """
前文说明
```json
{"case_status":"结案","judgment_result":"dismiss","timeline":{"filing_date":"2024-01-01"}}
```
后文
"""
    payload = ResponseExtractor().extract_json_candidate(text)
    assert payload["case_status"] == "结案"


def test_json_validator_accepts_chinese_keys() -> None:
    payload = {
        "案件状态": "正在进行",
        "判决结果": "pending",
        "节点时间": {
            "立案": "2024-01-01",
            "提交法官": "2024-01-02",
            "庭审": "2024-01-03",
            "判决": "2024-01-04",
        },
    }
    result = JSONValidator().validate(payload)
    assert result.ok is True
    assert result.value is not None
    assert result.value.case_status.value == "正在进行"
