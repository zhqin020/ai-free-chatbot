from __future__ import annotations

from datetime import datetime, timedelta, UTC

try:
    from .client_common import ApiClient, pretty_print
except ImportError:
    from client_common import ApiClient, pretty_print


# Demonstrates /api/metrics and /api/logs query patterns.
def main() -> None:
    client = ApiClient()
    try:
        summary = client.get("/api/metrics/summary")
        pretty_print("metrics summary", summary)

        providers = client.get("/api/metrics/providers")
        pretty_print("metrics providers", providers)

        logs_latest = client.get("/api/logs", params={"page": 1, "page_size": 20})
        pretty_print("logs latest", logs_latest)

        start_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        error_logs = client.get(
            "/api/logs",
            params={
                "level": "ERROR",
                "start_at": start_at,
                "page": 1,
                "page_size": 20,
            },
        )
        pretty_print("logs errors recent", error_logs)
    finally:
        client.close()


if __name__ == "__main__":
    main()
