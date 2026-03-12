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


def pretty_print(title: str, payload: Any) -> None:
    import json

    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
