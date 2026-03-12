from __future__ import annotations

from src.parser import JSONValidator, ResponseExtractor


def test_response_extractor_parses_fenced_json() -> None:
    text = """
前文说明
```json
{"case_id":"IMM-3-24","case_status":"结案","judgment_result":"dismiss","hearing":"no","timeline":{"filing_date":"2024-01-01","Applicant_file_completed":"2024-04-02","reply_memo":"2024-05-01","Sent_to_Court":"2024-06-14","judgment_date":"2024-10-01"}}
```
后文
"""
    payload = ResponseExtractor().extract_json_candidate(text)
    assert payload["case_status"] == "结案"
    assert payload["case_id"] == "IMM-3-24"


def test_json_validator_accepts_chinese_keys() -> None:
    payload = {
        "案号": "IMM-3-24",
        "案件状态": "正在进行",
        "判决结果": "grant",
        "是否庭审": "yes",
        "节点时间": {
            "立案": "2024-01-01",
            "提交法官": "2024-01-02",
            "庭审": "2024-01-03",
            "提交法院": "2024-01-04",
            "判决": "2024-01-04",
        },
    }
    result = JSONValidator().validate(payload)
    assert result.ok is True
    assert result.value is not None
    assert result.value.case_id == "IMM-3-24"
    assert result.value.case_status.value == "正在进行"
