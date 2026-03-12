from __future__ import annotations

try:
    from .client_common import ApiClient, pretty_print
except ImportError:
    from client_common import ApiClient, pretty_print


# Demonstrates /api/sessions CRUD and actions.
def main() -> None:
    client = ApiClient()
    session_id = "s-example-openchat-1"
    try:
        created = client.post(
            "/api/sessions",
            json={
                "id": session_id,
                "provider": "openchat",
                "chat_url": "https://example.com/openchat",
                "enabled": True,
                "priority": 80,
            },
        )
        pretty_print("create session", created)

        all_rows = client.get("/api/sessions")
        pretty_print("list sessions", all_rows)

        updated = client.put(
            f"/api/sessions/{session_id}",
            json={
                "provider": "openchat",
                "chat_url": "https://example.com/openchat/v2",
                "enabled": False,
                "priority": 95,
            },
        )
        pretty_print("update session", updated)

        login_ok = client.post(f"/api/sessions/{session_id}/mark-login-ok")
        pretty_print("mark login ok", login_ok)

        open_result = client.post(f"/api/sessions/{session_id}/open")
        pretty_print("open session link", open_result)

        deleted = client.delete(f"/api/sessions/{session_id}")
        pretty_print("delete session", deleted)
    finally:
        client.close()


if __name__ == "__main__":
    main()
