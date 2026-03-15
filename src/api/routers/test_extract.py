from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.result import LegalExtraction

from src.parser import JSONValidator, ResponseExtractor
from src.prompt import PromptGenerator
from fastapi import APIRouter

router = APIRouter(prefix="/api/test", tags=["test-extract"])


class TestExtractRequest(BaseModel):
    prompt: str = Field(min_length=1)
    document_text: str = Field(min_length=1)
    raw_response: str = Field(min_length=1)
    provider_hint: str | None = None


class TestExtractResponse(BaseModel):
    provider_hint: str | None = None
    generated_prompt: str
    raw_response: str
    valid: bool
    extracted_json: LegalExtraction | None = None
    validation_errors: list[str]
    retry_prompt: str | None = None


prompt_generator = PromptGenerator()
response_extractor = ResponseExtractor()
json_validator = JSONValidator()


@router.post("/extract", response_model=TestExtractResponse)
def extract_handler(payload: TestExtractRequest) -> TestExtractResponse:
    generated_prompt = prompt_generator.build_base_prompt(payload.prompt)
    generated_prompt = f"{generated_prompt}\n\n文书原文：\n{payload.document_text}"

    try:
        json_payload = response_extractor.extract_json_candidate(payload.raw_response)
    except Exception as exc:
        error_message = f"extract_error: {exc}"
        return TestExtractResponse(
            provider_hint=payload.provider_hint,
            generated_prompt=generated_prompt,
            raw_response=payload.raw_response,
            valid=False,
            extracted_json=None,
            validation_errors=[error_message],
            retry_prompt=prompt_generator.build_retry_prompt(generated_prompt, error_message),
        )

    validated = json_validator.validate(json_payload)
    if not validated.ok or validated.value is None:
        error_message = f"validate_error: {validated.error_message}"
        return TestExtractResponse(
            provider_hint=payload.provider_hint,
            generated_prompt=generated_prompt,
            raw_response=payload.raw_response,
            valid=False,
            extracted_json=None,
            validation_errors=[error_message],
            retry_prompt=prompt_generator.build_retry_prompt(generated_prompt, error_message),
        )

    return TestExtractResponse(
        provider_hint=payload.provider_hint,
        generated_prompt=generated_prompt,
        raw_response=payload.raw_response,
        valid=True,
        extracted_json=validated.value,
        validation_errors=[],
        retry_prompt=None,
    )
