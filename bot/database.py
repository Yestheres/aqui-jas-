from __future__ import annotations

from pathlib import Path

import aiosqlite


class Database:
    """Async SQLite wrapper for persistent server data and audit logs."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def log_action(
        self,
        guild_id: int,
        user_id: int,
        action: str,
        status: str,
        details: str = "",
    ) -> None:
        if self._db is None:
            raise RuntimeError("Database is not connected.")
        await self._db.execute(
            """
            INSERT INTO action_log(guild_id, user_id, action, status, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, action, status, details[:4000]),
        )
        await self._db.commit()
