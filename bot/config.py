from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not configured.")
        return cls(
            discord_token=token,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
