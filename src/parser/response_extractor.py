from __future__ import annotations

import json
import re
import logging
from typing import Any

from src.logging_mp import startlog

logger = startlog(__name__)


class ResponseExtractor:
    def extract_json_candidate(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("empty response")

        for block in self._find_fenced_json_blocks(text):
            parsed = self._try_parse_json(block)
            if parsed is not None:
                return parsed

        for obj in self._find_brace_objects(text):
            parsed = self._try_parse_json(obj)
            if parsed is not None:
                return parsed

        parsed = self._try_parse_json(text)
        if parsed is not None:
            return parsed

        raise ValueError("no valid json object found")

    def _find_fenced_json_blocks(self, text: str) -> list[str]:
        pattern = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
        return [m.group(1).strip() for m in pattern.finditer(text)]

    def _find_brace_objects(self, text: str) -> list[str]:
        objs: list[str] = []
        start = -1
        depth = 0
        for idx, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = idx
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start >= 0:
                        objs.append(text[start : idx + 1])
        return objs

    def _try_parse_json(self, candidate: str) -> dict[str, Any] | None:
        fixed = candidate.strip()
        if not fixed:
            return None
        fixed = fixed.replace("\u201c", '"').replace("\u201d", '"')
        fixed = fixed.replace("\u2018", "'").replace("\u2019", "'")
        
        # 启发式修复：LLM 经常在 CSS 选择器中写出未转义的双引号，例如 "has-text("New Chat")"
        # 这种修复会将 :has-text("...") 转换为 :has-text('...') 或类似形式以满足 JSON 规范
        try:
            # 尝试修复 :has-text("...") 内部的双引号
            fixed = re.sub(r'(:has-text\()\s*"([^"]*?)"\s*(\))', r"\1'\2'\3", fixed)
            # 尝试修复 [attr="..."] 内部的双引号 (支持 =, *=, ^=, $=, ~=, |=, !=)
            fixed = re.sub(r'(\[[^\]=^$~*|!]+[=~|^$*!]=?)\s*"([^"]*?)"\s*(\])', r"\1'\2'\3", fixed)
        except Exception as e:
            logger.warning(f"[_try_parse_json] heuristic repair failed: {e}")

        try:
            parsed = json.loads(fixed)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            logger.debug(f"[_try_parse_json] parse failed after repair. fixed_text={fixed!r} error={e}")
            return None
        return None
