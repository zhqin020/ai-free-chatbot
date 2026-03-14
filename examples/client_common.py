from __future__ import annotations

import os
from typing import Any

import httpx


class ApiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 20.0) -> None:
        self.base_url = (base_url or os.getenv("API_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
        token = os.getenv("API_TOKEN", "")
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method=method, url=path, **kwargs)
        response.raise_for_status()
        if not response.text:
            return None
        return response.json()

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    @staticmethod
    def make_chat_request_payload(document_text: str, msg_id_prefix: str):
        import time
        if not hasattr(ApiClient.make_chat_request_payload, "count"):
            ApiClient.make_chat_request_payload.count = 1
        ApiClient.make_chat_request_payload.count += 1
        ret_json = '''{
    "case_id": "IMM-####-##(from document)",
    "case_type": "Mandamus|Other",
    "case_status": "Closed|On-Going",
    "judgment_result": "leave|grant|dismiss",
    "hearing": "true|false",
    "timeline": {
        "filing_date": "YYYY-MM-DD",
        "Applicant_file_completed": "YYYY-MM-DD",
        "reply_memo": "YYYY-MM-DD",
        "Sent_to_Court": "YYYY-MM-DD",
        "judgment_date": "YYYY-MM-DD"
    }
    }'''
        prompt = f"Extract legal status, judgment result, and key timeline nodes as JSON. the JSON should have the format {ret_json}, and the json is only result of the response no any other additional information. If any of the fields cannot be extracted, please set it to null or empty."
        return {
            "external_id": f"{msg_id_prefix}-{int(time.time())}-{ApiClient.make_chat_request_payload.count}",
            "prompt": prompt,
            "document_text": document_text
        }



    @staticmethod
    def make_chat_request_payload_v2(
        prompt_template: str,  # 模板字符串，需包含 <ret_json_template> 占位符
        ret_json_template: str,  # 期望输出 JSON 格式的字符串，将插入到 prompt_template
        document_text: str,      # 待处理的文档内容
        msg_id_prefix: str       # 任务 external_id 前缀，便于追踪
    ):
        """
        构造用于 chat/extract API 的请求 payload。
        参数：
            prompt_template: str
                提示词模板，需包含 <ret_json_template> 占位符。
                例如：
                "
                请抽取法律状态、判决结果和关键时间节点，只输出 JSON，格式如下：<ret_json_template>。
                如果无法抽取某字段，请置为 null 或空                 
                "
            ret_json_template: str
                期望的 JSON 格式描述字符串。
            document_text: str
                需要处理的原始文档内容。
            msg_id_prefix: str
                任务 external_id 前缀。
        返回：dict
            包含 external_id, prompt, document_text 字段的请求体。
        """
        import time
        # 计数器用于生成唯一 external_id
        if not hasattr(ApiClient.make_chat_request_payload_v2, "count"):
            ApiClient.make_chat_request_payload_v2.count = 1
        ApiClient.make_chat_request_payload_v2.count += 1

        # 用字符串替换插值生成最终 prompt
        prompt = prompt_template.replace("<ret_json_template>", ret_json_template)

        return {
            "external_id": f"{msg_id_prefix}-{int(time.time())}-{ApiClient.make_chat_request_payload_v2.count}",
            "prompt": prompt,
            "document_text": document_text
        }



def pretty_print(title: str, payload: Any) -> None:
    import json

    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
