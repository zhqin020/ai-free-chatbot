from __future__ import annotations

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
        "task_id": payload.get("task_id"),
        "status": payload.get("status"),
        "provider": payload.get("provider"),
        "retry_count": payload.get("retry_count"),
        "extracted_json": payload.get("extracted_json"),
        "error_message": payload.get("error_message"),
        "raw_response_preview": (
            raw_response[:280] + "..." if isinstance(raw_response, str) and len(raw_response) > 280 else raw_response
        ),
    }


def _has_provider_session(client: ApiClient, provider_hint: str) -> bool:
    rows = client.get("/api/sessions", params={"enabled_only": True})
    for row in rows:
        if row.get("provider") != provider_hint:
            continue
        return True
    return False


def _detect_login_required(client: ApiClient, task_id: str) -> str | None:
    logs = client.get(
        "/api/logs",
        params={"task_id": task_id, "page": 1, "page_size": 5},
    )
    for item in logs.get("items", []):
        event = (item.get("event") or "").lower()
        message = item.get("message") or ""
        lowered = message.lower()
        if (
            event == "session_login_required"
            or "session not logged in" in lowered
            or "human verification" in lowered
            or "login required" in lowered
        ):
            return message
    return None


def _detect_provider_login_needed(client: ApiClient, provider_hint: str) -> bool:
    rows = client.get("/api/sessions", params={"enabled_only": True})
    for row in rows:
        if row.get("provider") != provider_hint:
            continue
        if row.get("login_state") == "need_login":
            return True
    return False


def _provider_session_snapshot(client: ApiClient, provider_hint: str) -> list[dict[str, Any]]:
    rows = client.get("/api/sessions", params={"enabled_only": True})
    snapshots: list[dict[str, Any]] = []
    for row in rows:
        if row.get("provider") != provider_hint:
            continue
        snapshots.append(
            {
                "id": row.get("id"),
                "provider": row.get("provider"),
                "state": row.get("state"),
                "login_state": row.get("login_state"),
            }
        )
    return snapshots


# Real end-to-end flow:
# 1) create task -> 2) worker executes real provider call -> 3) poll status -> 4) fetch task result
#
# Prerequisites:
# - API server running (python -m src.api.main)
# - Worker running (python scripts/run_worker.py)
# - At least one OPENCHAT session exists and is logged in
#
# Optional env vars:
# - E2E_PROVIDER (default: openchat)
# - E2E_TIMEOUT_SECONDS (default: 300)
# - E2E_POLL_INTERVAL_SECONDS (default: 2)
def main() -> None:
    client = ApiClient()

    provider_hint = os.getenv("E2E_PROVIDER", "openchat")
    timeout_seconds = int(os.getenv("E2E_TIMEOUT_SECONDS", "300"))
    poll_interval_seconds = int(os.getenv("E2E_POLL_INTERVAL_SECONDS", "2"))

    prompt = "Extract legal status, judgment result, and key timeline nodes as JSON."
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
      "doc_id": 3,
      "entry_date": "2024-05-06",
      "entry_office": "Ottawa",
      "summary": "Communication to the Court from the Registry dated 06-MAY-2024 re: No Applicant's Record on file - Sent to Court"
    },
    {
      "id": null,
      "case_id": "IMM-1-24",
      "doc_id": 4,
      "entry_date": "2024-01-10",
      "entry_office": "Ottawa",
      "summary": "Letter advising that no decision has yet been made on the Applicant's temporary resident visa. As such, no reasons for decision exist. sent by Embassy of Canada, Beijing on 09-JAN-2024 pursuant to Rule 9(2) Received on 10-JAN-2024"
    },
    {
      "id": null,
      "case_id": "IMM-1-24",
      "doc_id": 5,
      "entry_date": "2024-01-04",
      "entry_office": "Vancouver",
      "summary": "Notice of appearance on behalf of the respondent filed on 04-JAN-2024 with proof of service on the tribunal the applicant"
    },
    {
      "id": null,
      "case_id": "IMM-1-24",
      "doc_id": 6,
      "entry_date": "2024-01-03",
      "entry_office": "St. John's",
      "summary": "Letter from Applicant dated 03-JAN-2024 indicating they have not received a decision and as no reasons for decison exist, they are not seeking reasons. received on 03-JAN-2024"
    },
    {
      "id": null,
      "case_id": "IMM-1-24",
      "doc_id": 7,
      "entry_date": "2024-01-02",
      "entry_office": "St. John's",
      "summary": "Memorandum to file from St. John's, NL dated 02-JAN-2024 Registry requested Applicant provide letter stating they have not received a decison therefore they do not need to receive reasons, per Rule 72 exemption amendments placed on file."
    },
    {
      "id": null,
      "case_id": "IMM-1-24",
      "doc_id": 8,
      "entry_date": "2024-01-02",
      "entry_office": "St. John's",
      "summary": "Memorandum to file from St. John's, NL dated 02-JAN-2024 ALJR served, per Rule 133, upon DoJ Halifax by email Jan 2, 2024. Ack of receipt placed on file."
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

    try:
        if not _has_provider_session(client, provider_hint):
            raise RuntimeError(
                "no enabled session found for provider "
                f"{provider_hint}; create one in /admin/sessions first"
            )

        created = client.post(
            "/api/tasks",
            json={
                "external_id": f"e2e-openchat-{int(time.time())}",
                "prompt": prompt,
                "document_text": document_text,
                "provider_hint": provider_hint,
            },
        )
        task_id = created["id"]
        pretty_print("task created", created)

        terminal_statuses = {"COMPLETED", "FAILED"}
        deadline = time.monotonic() + timeout_seconds
        while True:
            row = client.get(f"/api/tasks/{task_id}")
            pretty_print("task status", {"id": row["id"], "status": row["status"], "latest_trace_id": row.get("latest_trace_id")})

            login_required_message = _detect_login_required(client, task_id)
            if login_required_message:
                snapshots = _provider_session_snapshot(client, provider_hint)
                raise RuntimeError(
                    f"login required: {login_required_message}; session_snapshot={snapshots}"
                )

            if _detect_provider_login_needed(client, provider_hint):
                snapshots = _provider_session_snapshot(client, provider_hint)
                raise RuntimeError(
                    "login required: worker opened browser and detected session not logged in; "
                    "please complete login and click Mark Login OK in /admin/sessions; "
                    f"session_snapshot={snapshots}"
                )

            if row["status"] in terminal_statuses:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"task not finished in {timeout_seconds}s; check worker and openchat session login state"
                )
            time.sleep(poll_interval_seconds)

        result = client.get(f"/api/tasks/{task_id}/result")
        pretty_print("task result (real provider output)", _compact_result(result))
    finally:
        client.close()


if __name__ == "__main__":
    main()
