from __future__ import annotations

EXTRACTION_FORMAT_TEMPLATE = """
请分析以下文书，并只输出一个 JSON 对象，不要输出额外说明。

JSON 必须包含：
{
  "case_status": "结案|正在进行",
  "judgment_result": "string",
  "timeline": {
    "filing_date": "YYYY-MM-DD|null",
    "judge_assignment_date": "YYYY-MM-DD|null",
    "trial_date": "YYYY-MM-DD|null",
    "judgment_date": "YYYY-MM-DD|null"
  }
}
""".strip()


RETRY_FORMAT_TEMPLATE = """
你上一条回复未通过 JSON 校验，错误原因：{error_message}

请仅返回一个合法 JSON 对象，结构必须是：
{{
  "case_status": "结案|正在进行",
  "judgment_result": "string",
  "timeline": {{
    "filing_date": "YYYY-MM-DD|null",
    "judge_assignment_date": "YYYY-MM-DD|null",
    "trial_date": "YYYY-MM-DD|null",
    "judgment_date": "YYYY-MM-DD|null"
  }}
}}

不要输出 markdown 代码块，不要输出解释。
""".strip()
