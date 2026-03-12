from __future__ import annotations

import argparse

import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run mock openchat site for local browser-flow tests")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8010, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto reload")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run(
        "src.mock_openchat.site:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
