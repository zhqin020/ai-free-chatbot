from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.browser.scheduler import DispatchDecision
from src.browser.session_pool import ProviderSessionPoolManager
from src.browser.worker import MultiProviderTaskProcessor, ProcessResult, TaskProcessor



class FakeProcessor(TaskProcessor):
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.calls = 0

    async def process(self, decision: DispatchDecision) -> ProcessResult:
        _ = decision
        self.calls += 1
        return ProcessResult(ok=True, raw_response=f"ok-{self.tag}")


def test_provider_pool_manager_creates_dedicated_pools() -> None:
    manager = ProviderSessionPoolManager(headless=True)
    openchat_pool = manager.get_pool("openchat")
    gemini_pool = manager.get_pool("gemini")

    assert openchat_pool is not gemini_pool
    assert manager.get_pool("openchat") is openchat_pool


@pytest.mark.asyncio
async def test_multi_provider_processor_routes_by_provider() -> None:
    openchat = FakeProcessor("openchat")
    gemini = FakeProcessor("gemini")
    processor = MultiProviderTaskProcessor(
        processors={
            "openchat": openchat,
            "gemini": gemini,
        }
    )

    result = await processor.process(
        DispatchDecision(
            task_id="t1",
            session_id="s1",
            provider="gemini",
            attempt_id=1,
            attempt_no=1,
            dispatched_at=datetime.now(UTC),
        )
    )

    assert result.ok is True
    assert result.raw_response == "ok-gemini"
    assert openchat.calls == 0
    assert gemini.calls == 1
