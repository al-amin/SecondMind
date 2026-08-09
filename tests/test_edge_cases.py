"""Exception & Edge Case Matrix — every row from the project plan mapped to
a named test here. Traces to the plan's "Exception & Edge Case Matrix"
table and SPEC.md's error-handling clauses. Rows already covered by a
dedicated test elsewhere are referenced, not duplicated.

Already covered elsewhere (not re-tested here):
- Input validation (id shape, path traversal): tests/test_paths.py
- Silent clobber / supersede duplicate-id bug: tests/test_store.py
- SQL injection resistance (parameterized queries): implicit in
  sqlite_index.py using ? placeholders everywhere — see this file's
  test_search_query_with_sql_metacharacters_does_not_crash below.
- Corrupt/missing SQLite index recovery: tests/test_sqlite_index.py
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from secondmind.models import KnowledgeItem, KnowledgeType
from secondmind.paths import InvalidNoteIdError
from secondmind.sqlite_index import SqliteIndex
from secondmind.store import NoteNotFoundError, VaultStore


class TestFilesystemEdgeCases(unittest.TestCase):
    def test_vault_directory_missing_is_auto_created_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_root = Path(tmp) / "not-yet-created"
            store = VaultStore(missing_root)
            store.put(id="a", type=KnowledgeType.CORE, title="A", body="x")
            self.assertTrue(missing_root.exists())

    def test_oversized_note_body_is_written_without_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            large_body = "x" * (2 * 1024 * 1024)  # 2MB
            store.put(id="large", type=KnowledgeType.CORE, title="Large", body=large_body)
            item = store.get("large")
            self.assertEqual(len(item.body), len(large_body))

    def test_non_ascii_body_round_trips_intact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            body = "héllo wörld — 日本語 テスト 🎉"
            store.put(id="unicode-note", type=KnowledgeType.CORE, title="Unicode", body=body)
            item = store.get("unicode-note")
            self.assertEqual(item.body, body)


class TestDataIntegrityEdgeCases(unittest.TestCase):
    def test_get_after_delete_raises_not_found_not_stale_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            store.put(id="a", type=KnowledgeType.CORE, title="A", body="x")
            note_file = Path(tmp) / "a.md"
            note_file.unlink()
            with self.assertRaises(NoteNotFoundError):
                store.get("a")

    def test_search_index_out_of_sync_with_vault_is_recoverable_via_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_root = Path(tmp) / "vault"
            store = VaultStore(vault_root)
            store.put(id="a", type=KnowledgeType.CORE, title="A", body="original unique zzyzx")

            db_path = Path(tmp) / "index.db"
            index = SqliteIndex(db_path)
            try:
                # Index never saw "a" — simulates a stale/out-of-sync index.
                self.assertEqual(index.search("zzyzx"), [])
                index.rebuild(store.list())
                self.assertIn("a", index.search("zzyzx"))
            finally:
                index.close()


class TestProcessLifecycleEdgeCases(unittest.TestCase):
    def test_list_on_index_that_was_never_populated_returns_empty_not_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "fresh.db"
            index = SqliteIndex(db_path)
            try:
                self.assertEqual(index.search("anything"), [])
            finally:
                index.close()

    def test_double_close_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = SqliteIndex(Path(tmp) / "index.db")
            index.close()
            # A second close on an already-closed sqlite3 connection is a
            # documented no-op, not an exception — verifying that here.
            index.close()


class TestSecurityEdgeCases(unittest.TestCase):
    def test_search_query_with_sql_metacharacters_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = SqliteIndex(Path(tmp) / "index.db")
            try:
                index.put(
                    KnowledgeItem(
                        id="a",
                        type=KnowledgeType.CORE,
                        title="A",
                        body="normal content",
                        created="2026-08-09T00:00:00Z",
                        updated="2026-08-09T00:00:00Z",
                    )
                )
                adversarial_queries = [
                    "'; DROP TABLE items; --",
                    "\" OR 1=1 --",
                    "*",
                    "MATCH",
                ]
                for query in adversarial_queries:
                    index.search(query)  # must not raise
            finally:
                index.close()

    def test_put_with_id_containing_null_byte_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            with self.assertRaises(InvalidNoteIdError):
                store.put(id="note\x00id", type=KnowledgeType.CORE, title="X", body="x")


if __name__ == "__main__":
    unittest.main()
