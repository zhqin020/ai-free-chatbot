from __future__ import annotations

try:
    from .client_common import ApiClient, pretty_print
except ImportError:
    from client_common import ApiClient, pretty_print


# Demonstrates /api/tasks create and get.
def main() -> None:
    client = ApiClient()
    try:
        created = client.post(
            "/api/tasks",
            json={
                "external_id": "ext-demo-001",
                "prompt": "Please extract legal milestones as JSON.",
                "document_text": "A sample legal document text goes here.",
                "provider_hint": "openchat",
            },
        )
        pretty_print("create task", created)

        task_id = created["id"]
        row = client.get(f"/api/tasks/{task_id}")
        pretty_print("get task", row)
    finally:
        client.close()


if __name__ == "__main__":
    main()
