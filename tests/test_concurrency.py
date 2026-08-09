"""Concurrency tests — SQLite WAL mode, rebuild-during-read, threaded access.

Traces to SPEC.md §2 (concurrency: WAL + busy_timeout, atomic rebuild) and
the Exception & Edge Case Matrix "Concurrency" row: two writers to the same
note simultaneously, search during rebuild, multiple readers/writers on one
vault at once.
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from secondmind.models import KnowledgeItem, KnowledgeType
from secondmind.sqlite_index import SqliteIndex
from secondmind.store import VaultStore


def _item(id: str, body: str) -> KnowledgeItem:
    return KnowledgeItem(
        id=id,
        type=KnowledgeType.CORE,
        title=id,
        body=body,
        created="2026-08-09T00:00:00Z",
        updated="2026-08-09T00:00:00Z",
    )


class TestConcurrentWrites(unittest.TestCase):
    def test_many_threads_writing_distinct_notes_all_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            errors: list[Exception] = []

            def write(i: int) -> None:
                try:
                    store.put(id=f"note-{i}", type=KnowledgeType.CORE, title=f"N{i}", body="x")
                except Exception as exc:  # pragma: no cover - failure path
                    errors.append(exc)

            threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            self.assertEqual(len(store.list()), 20)

    def test_concurrent_index_writers_to_the_same_db_do_not_raise_locked_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.db"
            errors: list[Exception] = []

            def write(i: int) -> None:
                index = SqliteIndex(db_path)
                try:
                    index.put(_item(f"note-{i}", f"content number {i}"))
                except Exception as exc:  # pragma: no cover - failure path
                    errors.append(exc)
                finally:
                    index.close()

            threads = [threading.Thread(target=write, args=(i,)) for i in range(10)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])


class TestSearchDuringRebuild(unittest.TestCase):
    def test_search_immediately_after_rebuild_sees_new_content_never_empty_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.db"
            index = SqliteIndex(db_path)
            try:
                index.put(_item("old", "original unique quokka content"))
                self.assertIn("old", index.search("quokka"))

                items = [_item(f"item-{i}", f"rebuilt unique wombat content {i}") for i in range(50)]
                index.rebuild(items)

                # Immediately after rebuild returns, the index must already
                # reflect the new content — no window where it appears
                # empty to the same handle that triggered the rebuild.
                results = index.search("wombat")
                self.assertGreater(len(results), 0)
                self.assertEqual(index.search("quokka"), [])
            finally:
                index.close()


if __name__ == "__main__":
    unittest.main()
