from __future__ import annotations

EXTRACTION_FORMAT_TEMPLATE = """
请分析以下文书，并只输出一个 JSON 对象，不要输出额外说明。

JSON 必须包含：
{
  "case_id": "string",
  "case_status": "Closed|On-Going",
  "judgment_result": "leave|grant|dismiss",
  "hearing": "true|false",
  "timeline": {
    "filing_date": "YYYY-MM-DD",
    "Applicant_file_completed": "YYYY-MM-DD",
    "reply_memo": "YYYY-MM-DD",
    "Sent_to_Court": "YYYY-MM-DD",
    "judgment_date": "YYYY-MM-DD"
  }
}
""".strip()


RETRY_FORMAT_TEMPLATE = """
你上一条回复未通过 JSON 校验，错误原因：{error_message}

请仅返回一个合法 JSON 对象，结构必须是：
{{
  "case_id": "string",
  "case_status": "Closed|On-Going",
  "judgment_result": "leave|grant|dismiss",
  "hearing": "true|false",
  "timeline": {{
    "filing_date": "YYYY-MM-DD",
    "Applicant_file_completed": "YYYY-MM-DD",
    "reply_memo": "YYYY-MM-DD",
    "Sent_to_Court": "YYYY-MM-DD",
    "judgment_date": "YYYY-MM-DD"
  }}
}}

不要输出 markdown 代码块，不要输出解释。
""".strip()
