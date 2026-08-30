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
    dev_guild_id: int | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not configured.")

        raw_guild = os.getenv("DEV_GUILD_ID", "").strip()
        try:
            dev_guild_id = int(raw_guild) if raw_guild else None
        except ValueError as exc:
            raise RuntimeError(
                "DEV_GUILD_ID precisa ser um ID numérico do Discord."
            ) from exc

        return cls(
            discord_token=token,
            database_path=os.getenv("DATABASE_PATH", "data/bot.sqlite3"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            dev_guild_id=dev_guild_id,
        )
