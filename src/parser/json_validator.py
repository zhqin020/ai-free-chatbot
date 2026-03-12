from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError

from src.models.result import CaseStatus, LegalExtraction, Timeline


@dataclass
class ValidationResult:
    ok: bool
    value: LegalExtraction | None = None
    error_message: str | None = None


class JSONValidator:
    def validate(self, payload: dict[str, Any]) -> ValidationResult:
        normalized = self._normalize_payload(payload)
        try:
            value = LegalExtraction.model_validate(normalized)
            return ValidationResult(ok=True, value=value)
        except ValidationError as exc:
            return ValidationResult(ok=False, error_message=str(exc))

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        timeline = payload.get("timeline") or payload.get("节点时间") or {}
        case_status_raw = payload.get("case_status") or payload.get("案件状态")
        judgment_result = payload.get("judgment_result") or payload.get("判决结果")

        normalized = {
            "case_status": self._normalize_case_status(case_status_raw),
            "judgment_result": judgment_result,
            "timeline": {
                "filing_date": timeline.get("filing_date") or timeline.get("立案"),
                "judge_assignment_date": timeline.get("judge_assignment_date") or timeline.get("提交法官"),
                "trial_date": timeline.get("trial_date") or timeline.get("庭审"),
                "judgment_date": timeline.get("judgment_date") or timeline.get("判决"),
            },
        }
        return normalized

    def _normalize_case_status(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if text in {CaseStatus.CLOSED.value, "closed", "CLOSED"}:
            return CaseStatus.CLOSED.value
        if text in {CaseStatus.ONGOING.value, "ongoing", "ONGOING"}:
            return CaseStatus.ONGOING.value
        return text

    @staticmethod
    def to_storage_fields(value: LegalExtraction) -> dict[str, str | date | None]:
        timeline: Timeline = value.timeline
        return {
            "case_status": value.case_status.value,
            "judgment_result": value.judgment_result,
            "filing_date": timeline.filing_date,
            "judge_assignment_date": timeline.judge_assignment_date,
            "trial_date": timeline.trial_date,
            "judgment_date": timeline.judgment_date,
        }
