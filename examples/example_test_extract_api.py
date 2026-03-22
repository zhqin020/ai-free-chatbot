from __future__ import annotations

import argparse
import os
import time
from typing import Any

try:
    from .client_common import ApiClient, pretty_print
except ImportError:
    from client_common import ApiClient, pretty_print


def _compact_result(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    raw_response = payload.get("raw_response")
    return {
        "task_id": payload.get("task_id") or payload.get("id"),
        "status": payload.get("status"),
        "provider": payload.get("provider"),
        "retry_count": payload.get("retry_count"),
        "extracted_json": payload.get("extracted_json"),
        "error_message": payload.get("error_message"),
        "raw_response_preview": (
            raw_response[:280] + "..." if isinstance(raw_response, str) and len(raw_response) > 280 else raw_response
        ),
    }


def _collect_pending_diagnostics(client: ApiClient, task_id: str) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {"task_id": task_id}

    try:
        worker = client.get("/api/worker/status")
        diagnostics["worker"] = {
            "running": worker.get("running"),
            "pid": worker.get("pid"),
            "message": worker.get("message"),
        }
    except Exception as exc:
        diagnostics["worker_error"] = str(exc)

    try:
        sessions = client.get("/api/sessions", params={"enabled_only": True})
        ready_count = sum(1 for row in sessions if row.get("state") == "READY")
        diagnostics["sessions"] = {
            "enabled_total": len(sessions),
            "ready_total": ready_count,
            "states": [
                {
                    "id": row.get("id"),
                    "provider": row.get("provider"),
                    "state": row.get("state"),
                    "login_state": row.get("login_state"),
                }
                for row in sessions
            ],
        }
    except Exception as exc:
        diagnostics["sessions_error"] = str(exc)

    try:
        logs = client.get(
            "/api/logs",
            params={"task_id": task_id, "page": 1, "page_size": 5},
        )
        diagnostics["recent_logs"] = {
            "total": logs.get("total", 0),
            "items": [
                {
                    "level": item.get("level"),
                    "event": item.get("event"),
                    "message": item.get("message"),
                }
                for item in logs.get("items", [])
            ],
        }
    except Exception as exc:
        diagnostics["logs_error"] = str(exc)

    return diagnostics


# Real end-to-end flow:
# 1) create task -> 2) worker executes real provider call -> 3) poll status -> 4) fetch task result
#
# Prerequisites:
# - API server running (python -m src.api.main)
# - Worker running (python scripts/run_worker.py)
#
# Optional env vars:
# - E2E_TIMEOUT_SECONDS (default: 300)
# - E2E_POLL_INTERVAL_SECONDS (default: 2)
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create one extraction task and poll result via /api/tasks.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("E2E_TIMEOUT_SECONDS", "300")),
        help="Polling timeout seconds",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=int(os.getenv("E2E_POLL_INTERVAL_SECONDS", "2")),
        help="Polling interval seconds",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
        help="API base URL",
    )
    return parser.parse_args()



ret_json = '''{
    "case_id": "IMM-####-##(from document)",
    "case_type": "Mandamus|Other",
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
    }'''

document_text = '''
{
  "case_id": "IMM-1-24",
  "case_number": "IMM-1-24",
  "title": "Peng Yang v. MCI",
  "court": "Halifax",
  "date": "2024-01-01",
  "case_type": "Immigration Matters",
  "action_type": "Immigration Matters",
  "nature_of_proceeding": "Imm - Appl. for leave & jud. review - Arising outside Canada",
  "filing_date": "2024-01-01",
  "office": "Halifax",
  "style_of_cause": "Peng Yang v. MCI",
  "language": "English",
  "url": "https://www.fct-cf.ca/en/court-files-and-decisions/court-files",
  "html_content": "",
  "scraped_at": "2025-12-16T18:19:51.369881",
  "docket_entries": [
    {
      "id": null,
      "case_id": "IMM-1-24",
      "doc_id": 1,
      "entry_date": "2024-05-08",
      "entry_office": "Ottawa",
      "summary": "Memorandum to file from Ottawa Principal Office dated 08-MAY-2024 Final Order sent to all parties on May 8, 2024 placed on file."
    },
    {
      "id": null,
      "case_id": "IMM-1-24",
      "doc_id": 2,
      "entry_date": "2024-05-08",
      "entry_office": "Ottawa",
      "summary": "(Final decision) Order rendered by The Honourable Mr. Justice Pentney at Ottawa on 08-MAY-2024 dismissing the application for leave Decision filed on 08-MAY-2024 Considered by the Court without personal appearance entered in J. & O. Book, volume 1181 page(s) 48 - 50 Copy of the order sent to all parties Transmittal Letters placed on file."
    },

    {
      "id": null,
      "case_id": "IMM-1-24",
      "doc_id": 9,
      "entry_date": "2024-01-02",
      "entry_office": "St. John's",
      "summary": "Application for leave and judicial review against a decision Order of MANDAMUS, IRCC, Beijing, China, W308966713, no decision date filed on 02-JAN-2024 Written reasons not received by the Applicant Tariff fee of $50.00 received"
    }
  ]
}
        '''

prompt_templ = f"Extract legal status, judgment result, and key timeline nodes as JSON. the JSON should have the format <ret_json_template>, and the json is the only result of the response no any other additional information. If any of the fields cannot be extracted, please set it to null or empty.\n the document text is:\n"

    
def main() -> None:
    args = _parse_args()
    client = ApiClient(base_url=args.base_url)

    # 客户端无需检查会话状态，直接发送请求

    # 连续多次请求
    N = 1
    results = []
     
    for i in range(N):
        print(f"\n===== Run {i+1} =====")
        
        #request_payload = ApiClient.make_chat_request_payload(document_text=document_text, msg_id_prefix=f"e2e-openchat")
        request_payload = ApiClient.make_chat_request_payload_v2(
            prompt_template=prompt_templ,
            ret_json_template=ret_json,
            document_text=document_text,
            msg_id_prefix=f"e2e-example"
        )
        created = client.post(
            "/api/tasks",
            json=request_payload,
        )
        task_id = created["id"]
        pretty_print("task created", created)

        timeout_seconds = args.timeout_seconds
        poll_interval_seconds = args.poll_interval_seconds
        terminal_statuses = {"COMPLETED", "FAILED", "CRITICAL"}
        deadline = time.monotonic() + timeout_seconds
        final_row: dict[str, Any] | None = None
        while True:
            row = client.get(f"/api/tasks/{task_id}")
            pretty_print(
                "task status",
                {
                    "id": row["id"],
                    "status": row["status"],
                    "latest_trace_id": row.get("latest_trace_id"),
                    "error_message": row.get("error_message"),
                },
            )
            if row["status"] == "CRITICAL":
                print("[CRITICAL] 服务端已不可用，终止轮询。请检查服务端健康状态。")
                final_row = row
                break
            if row["status"] in terminal_statuses:
                final_row = row
                break
            if time.monotonic() >= deadline:
                diagnostics = _collect_pending_diagnostics(client, task_id)
                pretty_print("pending diagnostics", diagnostics)
                raise TimeoutError(
                    f"task not finished in {timeout_seconds}s; check worker/server logs for details"
                )
            time.sleep(poll_interval_seconds)
        if final_row is not None:
            pretty_print("task result (merged task payload)", _compact_result(final_row))
            results.append({
                "run": i+1,
                "provider": final_row.get("provider"),
                "status": final_row.get("status"),
                "error_message": final_row.get("error_message"),
            })
    print("\n===== 汇总结果 =====")
    for r in results:
        print(f"Run {r['run']}: provider={r['provider']} status={r['status']} error={r['error_message']}")
    client.close()


if __name__ == "__main__":
    main()
