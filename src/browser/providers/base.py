from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class ProviderAdapter(ABC):
    provider_name: str = "unknown"
    input_selectors: tuple[str, ...] = ()
    send_button_selectors: tuple[str, ...] = ()
    response_selectors: tuple[str, ...] = ()

    @abstractmethod
    async def is_logged_in(self, page: Any) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def send_message(self, page: Any, message: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def wait_for_response(
        self,
        page: Any,
        previous_response: str | None = None,
        timeout_ms: int = 60000,
    ) -> Optional[str]:
        raise NotImplementedError

    async def _pick_visible_selector(self, page: Any, selectors: tuple[str, ...]) -> Optional[str]:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.is_visible():
                    return selector
            except Exception:
                continue
        return None

    @staticmethod
    def normalize_text(value: str | None) -> str:
        if not value:
            return ""
        return "\n".join(line.rstrip() for line in value.strip().splitlines()).strip()
