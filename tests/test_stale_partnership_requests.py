import tempfile
import unittest
from pathlib import Path

from storage import Database


class StalePartnershipRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tempdir.name) / "test.sqlite3")
        self.db.initialize()

    def tearDown(self) -> None:
        self.db.close()
        self.tempdir.cleanup()

    def test_stale_pending_request_allows_new_request(self) -> None:
        guild_id = 101
        requester_id = 202

        with self.db._connect() as connection:
            connection.execute(
                """
                INSERT INTO partnership_requests
                    (guild_id, requester_id, description, link, status, approval_message_id, created_at)
                VALUES (?, ?, ?, ?, 'pending', '999999', datetime('now', '-31 days'))
                """,
                (str(guild_id), str(requester_id), "Primeira descrição", "https://discord.gg/primeiro"),
            )
            connection.commit()

        second_request = self.db.create_request(guild_id, requester_id, "Segunda descrição", "https://discord.gg/segundo")
        self.assertIsNotNone(second_request)
        self.db.set_message_id(second_request, 12345)

        active = self.db.get_active_request(guild_id, requester_id)
        self.assertIsNotNone(active)
        self.assertEqual(active["description"], "Segunda descrição")


if __name__ == "__main__":
    unittest.main()
