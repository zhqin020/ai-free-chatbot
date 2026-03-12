from __future__ import annotations

from src.logging_mp import setup_logging as _setup_logging_mp


def setup_logging(level: str = "INFO", use_json: bool = True) -> None:
    """Compatibility wrapper for legacy imports.

    The parameters are kept for backward compatibility. `use_json` is ignored
    because `src.logging_mp` uses unified text formatter for console/file.
    """

    _ = use_json
    _setup_logging_mp(name=None, cfg_json_str=f'{{"level":"{level}","output":"file, console"}}')
