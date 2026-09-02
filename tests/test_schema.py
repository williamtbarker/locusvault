from __future__ import annotations

import sqlite3
import unittest

from locusvault.schema import configure, migrate


class SchemaTests(unittest.TestCase):
    def test_migration_is_idempotent(self) -> None:
        connection = sqlite3.connect(":memory:")
        configure(connection)
        self.assertEqual(migrate(connection), 1)
        self.assertEqual(migrate(connection), 1)
        versions = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        if versions is None:
            self.fail("expected a migration count")
        self.assertEqual(versions[0], 1)
        connection.close()

    def test_foreign_keys_are_enabled(self) -> None:
        connection = sqlite3.connect(":memory:")
        configure(connection)
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()
        if enabled is None:
            self.fail("expected the foreign_keys pragma")
        self.assertEqual(enabled[0], 1)
        connection.close()


if __name__ == "__main__":
    unittest.main()
