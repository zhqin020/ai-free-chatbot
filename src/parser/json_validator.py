from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError

from src.models.result import CaseStatus, HearingStatus, JudgmentResult, LegalExtraction, Timeline


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
        case_id = payload.get("case_id") or payload.get("case_number") or payload.get("案件编号") or payload.get("案号")
        case_status_raw = payload.get("case_status") or payload.get("案件状态")
        judgment_result = payload.get("judgment_result") or payload.get("判决结果")
        hearing_raw = payload.get("hearing") or payload.get("是否庭审")

        applicant_file_completed = (
            timeline.get("Applicant_file_completed")
            or timeline.get("applicant_file_completed")
            or timeline.get("judge_assignment_date")
            or timeline.get("提交法官")
        )
        reply_memo = (
            timeline.get("reply_memo")
            or timeline.get("trial_date")
            or timeline.get("庭审")
        )
        sent_to_court = (
            timeline.get("Sent_to_Court")
            or timeline.get("sent_to_court")
            or timeline.get("提交法院")
            or timeline.get("sent_to_court_date")
        )

        normalized = {
            "case_id": str(case_id).strip() if case_id is not None else None,
            "case_status": self._normalize_case_status(case_status_raw),
            "judgment_result": self._normalize_judgment_result(judgment_result),
            "hearing": self._normalize_hearing(hearing_raw),
            "timeline": {
                "filing_date": timeline.get("filing_date") or timeline.get("立案"),
                "Applicant_file_completed": applicant_file_completed,
                "reply_memo": reply_memo,
                "Sent_to_Court": sent_to_court,
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

    def _normalize_judgment_result(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {JudgmentResult.LEAVE.value, JudgmentResult.GRANT.value, JudgmentResult.DISMISS.value}:
            return text
        return text

    def _normalize_hearing(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {HearingStatus.YES.value, "是", "有", "true", "1"}:
            return HearingStatus.YES.value
        if text in {HearingStatus.NO.value, "否", "无", "false", "0"}:
            return HearingStatus.NO.value
        return text

    @staticmethod
    def to_storage_fields(value: LegalExtraction) -> dict[str, str | date | None]:
        timeline: Timeline = value.timeline
        return {
            "case_status": value.case_status.value,
            "judgment_result": value.judgment_result.value,
            "filing_date": timeline.filing_date,
            # Reuse existing DB columns for backward compatibility.
            "judge_assignment_date": timeline.Applicant_file_completed,
            "trial_date": timeline.Sent_to_Court or timeline.reply_memo,
            "judgment_date": timeline.judgment_date,
        }
