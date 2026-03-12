from __future__ import annotations


class RetryHandler:
    def __init__(self, max_parse_retry: int = 1) -> None:
        self.max_parse_retry = max_parse_retry

    def should_retry_parse(self, attempt_no: int) -> bool:
        return attempt_no <= self.max_parse_retry
