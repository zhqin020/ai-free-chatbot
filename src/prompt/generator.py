from __future__ import annotations

from src.prompt.template import EXTRACTION_FORMAT_TEMPLATE, RETRY_FORMAT_TEMPLATE


class PromptGenerator:
    def build_base_prompt(self, user_prompt: str) -> str:
        prompt = user_prompt.strip()
        if not prompt:
            return EXTRACTION_FORMAT_TEMPLATE
        return f"{prompt}\n\n{EXTRACTION_FORMAT_TEMPLATE}"

    def build_retry_prompt(self, previous_prompt: str, error_message: str) -> str:
        retry_suffix = RETRY_FORMAT_TEMPLATE.format(error_message=error_message)
        return f"{previous_prompt}\n\n[FORMAT_RETRY]\n{retry_suffix}"
