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
    dev_guilds: tuple[int, ...] = ()
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-5-mini"

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not configured.")

        raw_guilds = os.getenv("DEV_GUILDS", "")
        guilds: list[int] = []
        for value in raw_guilds.split(","):
            value = value.strip()
            if value:
                guilds.append(int(value))

        return cls(
            discord_token=token,
            database_path=os.getenv("DATABASE_PATH", "data/bot.sqlite3"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            dev_guilds=tuple(guilds),
            ai_api_key=os.getenv("AI_API_KEY", "").strip(),
            ai_base_url=os.getenv("AI_BASE_URL", "https://api.openai.com/v1").strip(),
            ai_model=os.getenv("AI_MODEL", "gpt-5-mini").strip(),
        )
