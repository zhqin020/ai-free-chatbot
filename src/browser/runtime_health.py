from __future__ import annotations

from pathlib import Path




def check_provider_runtime(provider: Provider | None = None) -> tuple[bool, str | None]:
    _ = provider
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return False, (
            "runtime_unavailable: playwright import failed; "
            f"{exc}. Install dependencies and run: playwright install chromium"
        )

    try:
        with sync_playwright() as p:
            executable = p.chromium.executable_path
        if not executable:
            return False, "runtime_unavailable: playwright chromium path is empty"

        if not Path(executable).exists():
            return False, (
                "runtime_unavailable: playwright chromium executable not found at "
                f"{executable}. Run: playwright install chromium"
            )
        return True, None
    except Exception as exc:
        return False, (
            "runtime_unavailable: playwright runtime check failed; "
            f"{exc}. Run: playwright install chromium"
        )
