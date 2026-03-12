from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "ai-free-chatbot"
    app_env: str = "dev"
    log_level: str = "INFO"
    db_url: str = "sqlite:///data/app.db"
    api_token: str = ""

    @property
    def sqlite_file(self) -> Path | None:
        prefix = "sqlite:///"
        if self.db_url.startswith(prefix):
            return Path(self.db_url[len(prefix) :])
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "ai-free-chatbot"),
        app_env=os.getenv("APP_ENV", "dev"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        db_url=os.getenv("DB_URL", "sqlite:///data/app.db"),
        api_token=os.getenv("API_TOKEN", ""),
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
