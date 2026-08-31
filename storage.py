from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# Keep the current GitHub database filename so an existing deployment does not
# silently start with a new empty database.
DATABASE_PATH = Path(__file__).parent / "data" / "aqui_jas.sqlite3"


class Database:
    def __init__(self, path: Path = DATABASE_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}

    @classmethod
    def _ensure_column(
        cls,
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        if column not in cls._columns(connection, table):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id TEXT PRIMARY KEY,
                    approval_channel_id TEXT,
                    publication_channel_id TEXT,
                    trap_channel_id TEXT,
                    suspicious_role_id TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            if self._columns(connection, "guild_settings"):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO guild_config (
                        guild_id, approval_channel_id, publication_channel_id
                    )
                    SELECT
                        CAST(guild_id AS TEXT),
                        CAST(staff_channel_id AS TEXT),
                        CAST(partnership_channel_id AS TEXT)
                    FROM guild_settings
                    """
                )
                connection.execute(
                    """
                    UPDATE guild_config
                    SET approval_channel_id = COALESCE(
                            approval_channel_id,
                            (SELECT CAST(staff_channel_id AS TEXT)
                             FROM guild_settings
                             WHERE CAST(guild_settings.guild_id AS TEXT) = guild_config.guild_id)
                        ),
                        publication_channel_id = COALESCE(
                            publication_channel_id,
                            (SELECT CAST(partnership_channel_id AS TEXT)
                             FROM guild_settings
                             WHERE CAST(guild_settings.guild_id AS TEXT) = guild_config.guild_id)
                        )
                    """
                )

            request_columns = self._columns(connection, "partnership_requests")
            if request_columns and "requester_id" not in request_columns:
                connection.execute(
                    "ALTER TABLE partnership_requests RENAME TO partnership_requests_legacy"
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS partnership_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    requester_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    link TEXT NOT NULL,
                    approval_message_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    awaiting_channel INTEGER NOT NULL DEFAULT 0,
                    publication_channel_id TEXT,
                    published_message_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reviewed_by TEXT
                )
                """
            )

            if self._columns(connection, "partnership_requests_legacy"):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO partnership_requests (
                        id, guild_id, requester_id, description, link, status, created_at
                    )
                    SELECT
                        id,
                        CAST(guild_id AS TEXT),
                        CAST(user_id AS TEXT),
                        description,
                        invite_url,
                        status,
                        created_at
                    FROM partnership_requests_legacy
                    """
                )

            self._ensure_column(connection, "partnership_requests", "approval_message_id", "TEXT")
            self._ensure_column(
                connection,
                "partnership_requests",
                "awaiting_channel",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(connection, "partnership_requests", "publication_channel_id", "TEXT")
            self._ensure_column(connection, "partnership_requests", "published_message_id", "TEXT")
            self._ensure_column(connection, "partnership_requests", "reviewed_by", "TEXT")

            # Recover requests that were in the middle of a review when the bot
            # was restarted. They become pending again instead of being stuck.
            connection.execute(
                "UPDATE partnership_requests SET status='pending', awaiting_channel=0 WHERE status='approving'"
            )

            # Remove historical duplicates before creating the invariant below.
            # We preserve every row; only newer duplicate active requests are
            # marked rejected.
            connection.execute(
                """
                UPDATE partnership_requests
                SET status = 'rejected',
                    reviewed_by = COALESCE(reviewed_by, 'system-duplicate-cleanup')
                WHERE id IN (
                    SELECT newer.id
                    FROM partnership_requests AS newer
                    JOIN partnership_requests AS older
                      ON older.guild_id = newer.guild_id
                     AND older.requester_id = newer.requester_id
                     AND older.status IN ('pending', 'publishing')
                     AND newer.status IN ('pending', 'publishing')
                     AND older.id < newer.id
                )
                """
            )

            # One active partnership request per user/server. Partial indexes
            # keep approved/rejected history intact.
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_partnership
                ON partnership_requests (guild_id, requester_id)
                WHERE status IN ('pending', 'publishing')
                """
            )
            connection.commit()

    def set_approval_channel(self, guild_id: int, channel_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO guild_config (guild_id, approval_channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    approval_channel_id = excluded.approval_channel_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), str(channel_id)),
            )

    def get_approval_channel(self, guild_id: int) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT approval_channel_id FROM guild_config WHERE guild_id = ?",
                (str(guild_id),),
            ).fetchone()
        return int(row["approval_channel_id"]) if row and row["approval_channel_id"] else None

    def set_publication_channel(self, guild_id: int, channel_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO guild_config (guild_id, approval_channel_id, publication_channel_id)
                VALUES (
                    ?,
                    COALESCE((SELECT approval_channel_id FROM guild_config WHERE guild_id = ?), ''),
                    ?
                )
                ON CONFLICT(guild_id) DO UPDATE SET
                    publication_channel_id = excluded.publication_channel_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), str(guild_id), str(channel_id)),
            )

    def get_publication_channel(self, guild_id: int) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT publication_channel_id FROM guild_config WHERE guild_id = ?",
                (str(guild_id),),
            ).fetchone()
        return int(row["publication_channel_id"]) if row and row["publication_channel_id"] else None

    def set_trap_config(self, guild_id: int, channel_id: int, role_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO guild_config
                    (guild_id, approval_channel_id, trap_channel_id, suspicious_role_id)
                VALUES (
                    ?,
                    COALESCE((SELECT approval_channel_id FROM guild_config WHERE guild_id = ?), ''),
                    ?, ?
                )
                ON CONFLICT(guild_id) DO UPDATE SET
                    trap_channel_id = excluded.trap_channel_id,
                    suspicious_role_id = excluded.suspicious_role_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), str(guild_id), str(channel_id), str(role_id)),
            )

    def get_trap_config(self, guild_id: int) -> dict[str, int] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT trap_channel_id, suspicious_role_id FROM guild_config WHERE guild_id = ?",
                (str(guild_id),),
            ).fetchone()
        if not row or not row["trap_channel_id"] or not row["suspicious_role_id"]:
            return None
        return {
            "channel_id": int(row["trap_channel_id"]),
            "role_id": int(row["suspicious_role_id"]),
        }

    def clear_trap_config(self, guild_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE guild_config
                SET trap_channel_id = NULL,
                    suspicious_role_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ?
                """,
                (str(guild_id),),
            )

    def create_request(
        self,
        guild_id: int,
        requester_id: int,
        description: str,
        link: str,
    ) -> int | None:
        # BEGIN IMMEDIATE serializes the check + insert. This closes the race
        # where two nearly simultaneous /parceria interactions both saw no
        # pending request and then both inserted one.
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT id
                FROM partnership_requests
                WHERE guild_id = ?
                  AND requester_id = ?
                  AND status IN ('pending', 'publishing')
                LIMIT 1
                """,
                (str(guild_id), str(requester_id)),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                return None

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO partnership_requests
                        (guild_id, requester_id, description, link)
                    VALUES (?, ?, ?, ?)
                    """,
                    (str(guild_id), str(requester_id), description, link),
                )
            except sqlite3.IntegrityError:
                connection.rollback()
                return None

            request_id = int(cursor.lastrowid)
            connection.commit()
            return request_id

    def get_active_request(self, guild_id: int, requester_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM partnership_requests
                WHERE guild_id = ?
                  AND requester_id = ?
                  AND status IN ('pending', 'publishing')
                ORDER BY id ASC
                LIMIT 1
                """,
                (str(guild_id), str(requester_id)),
            ).fetchone()
        return dict(row) if row else None

    def set_message_id(self, request_id: int, message_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE partnership_requests SET approval_message_id = ? WHERE id = ?",
                (str(message_id), request_id),
            )

    def get_request(self, request_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM partnership_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_pending_requests(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM partnership_requests
                WHERE status = 'pending' AND approval_message_id IS NOT NULL
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def set_awaiting_channel(self, request_id: int, awaiting: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE partnership_requests
                SET awaiting_channel = ?
                WHERE id = ? AND status = 'pending'
                """,
                (1 if awaiting else 0, request_id),
            )
            return cursor.rowcount == 1

    def start_publication(
        self,
        request_id: int,
        reviewer_id: int,
        channel_id: int,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE partnership_requests
                SET status = 'publishing',
                    awaiting_channel = 0,
                    reviewed_by = ?,
                    publication_channel_id = ?
                WHERE id = ? AND status = 'pending'
                """,
                (str(reviewer_id), str(channel_id), request_id),
            )
            return cursor.rowcount == 1

    def complete_publication(self, request_id: int, message_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE partnership_requests
                SET status = 'approved', published_message_id = ?
                WHERE id = ? AND status = 'publishing'
                """,
                (str(message_id), request_id),
            )

    def reset_publication(self, request_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE partnership_requests
                SET status = 'pending', awaiting_channel = 1
                WHERE id = ? AND status = 'publishing'
                """,
                (request_id,),
            )

    def clear_stale_active_requests(self, guild_id: int, requester_id: int, keep_request_id: int) -> None:
        """Finalize any older active duplicate left by a previous bot version or interrupted flow."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE partnership_requests
                SET status = 'rejected',
                    reviewed_by = COALESCE(reviewed_by, 'system-stale-cleanup'),
                    awaiting_channel = 0
                WHERE guild_id = ?
                  AND requester_id = ?
                  AND id != ?
                  AND status IN ('pending', 'publishing')
                """,
                (str(guild_id), str(requester_id), keep_request_id),
            )

    def reset_pending_request_for_deleted_message(self, message_id: int) -> bool:
        """Release a pending request when its staff message no longer exists."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE partnership_requests
                SET status = 'rejected',
                    awaiting_channel = 0,
                    reviewed_by = COALESCE(reviewed_by, 'system-message-deleted')
                WHERE approval_message_id = ?
                  AND status = 'pending'
                """,
                (str(message_id),),
            )
            return cursor.rowcount == 1

    def review_request(
        self,
        request_id: int,
        status: str,
        reviewer_id: int,
    ) -> bool:
        if status not in {"approved", "rejected"}:
            raise ValueError("status inválido")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE partnership_requests
                SET status = ?, reviewed_by = ?
                WHERE id = ? AND status = 'pending'
                """,
                (status, str(reviewer_id), request_id),
            )
            return cursor.rowcount == 1
