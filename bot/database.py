from __future__ import annotations

from pathlib import Path

import aiosqlite

DEFAULT_AI_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_AI_MODEL = "openrouter/free"


class Database:
    """Async SQLite wrapper for guild configuration, memory and audit."""

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
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ai_api_key TEXT,
                ai_base_url TEXT,
                ai_model TEXT
            );
            CREATE TABLE IF NOT EXISTS conversation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                risk TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self._db.commit()
        for column, definition in (
            ("ai_api_key", "TEXT"),
            ("ai_base_url", "TEXT"),
            ("ai_model", "TEXT"),
        ):
            try:
                await self._db.execute(
                    f"ALTER TABLE guild_config ADD COLUMN {column} {definition}"
                )
            except aiosqlite.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database is not connected.")
        return self._db

    async def ensure_guild(self, guild_id: int) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO guild_config(guild_id) VALUES (?)", (guild_id,)
        )
        await self.conn.commit()

    async def set_ai_config(self, guild_id: int, api_key: str, base_url: str, model: str) -> None:
        await self.ensure_guild(guild_id)
        await self.conn.execute(
            "UPDATE guild_config SET ai_api_key=?, ai_base_url=?, ai_model=?, updated_at=CURRENT_TIMESTAMP WHERE guild_id=?",
            (api_key, base_url, model, guild_id),
        )
        await self.conn.commit()

    async def get_ai_config(self, guild_id: int) -> tuple[str, str, str] | None:
        cursor = await self.conn.execute(
            "SELECT ai_api_key, ai_base_url, ai_model FROM guild_config WHERE guild_id=?",
            (guild_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if not row or not row[0]:
            return None
        return str(row[0]), str(row[1] or DEFAULT_AI_BASE_URL), str(row[2] or DEFAULT_AI_MODEL)

    async def clear_ai_config(self, guild_id: int) -> None:
        await self.ensure_guild(guild_id)
        await self.conn.execute(
            "UPDATE guild_config SET ai_api_key=NULL, ai_base_url=NULL, ai_model=NULL, updated_at=CURRENT_TIMESTAMP WHERE guild_id=?",
            (guild_id,),
        )
        await self.conn.commit()

    async def add_memory(self, guild_id: int, user_id: int, role: str, content: str) -> None:
        await self.conn.execute(
            "INSERT INTO conversation_memory(guild_id,user_id,role,content) VALUES (?,?,?,?)",
            (guild_id, user_id, role, content[:8000]),
        )
        await self.conn.execute(
            """
            DELETE FROM conversation_memory
            WHERE guild_id=? AND user_id=? AND id NOT IN (
                SELECT id FROM conversation_memory
                WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 20
            )
            """,
            (guild_id, user_id, guild_id, user_id),
        )
        await self.conn.commit()

    async def get_memory(self, guild_id: int, user_id: int, limit: int = 12) -> list[tuple[str, str]]:
        cursor = await self.conn.execute(
            "SELECT role,content FROM conversation_memory WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT ?",
            (guild_id, user_id, limit),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [(str(role), str(content)) for role, content in reversed(rows)]

    async def log_action(self, guild_id: int, user_id: int, action: str, risk: str, status: str, details: str = "") -> None:
        await self.conn.execute(
            "INSERT INTO action_log(guild_id,user_id,action,risk,status,details) VALUES (?,?,?,?,?,?)",
            (guild_id, user_id, action, risk, status, details[:4000]),
        )
        await self.conn.commit()
