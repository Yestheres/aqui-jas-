from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    database_path: str = "data/bot.sqlite3"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not configured.")

        return cls(
            discord_token=token,
            database_path=os.getenv("DATABASE_PATH", "data/bot.sqlite3"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
