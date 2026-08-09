"""Tests for secondmind.sqlite_index — the disposable/rebuildable FTS5 index.

Traces to SPEC.md §2 (concurrency: WAL + busy_timeout, atomic rebuild) and
§3 (hybrid BM25 + cosine search, RRF fusion). The index is never the only
place a fact lives — it can be deleted and rebuilt from the vault at any
time (verified by test_rebuild_from_items_replaces_prior_content).
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from secondmind.models import KnowledgeItem, KnowledgeType
from secondmind.sqlite_index import SqliteIndex


def _item(id: str, title: str, body: str, type: KnowledgeType = KnowledgeType.SEMANTIC) -> KnowledgeItem:
    return KnowledgeItem(
        id=id,
        type=type,
        title=title,
        body=body,
        created="2026-08-09T00:00:00Z",
        updated="2026-08-09T00:00:00Z",
    )


class TestSqliteIndexBasicSearch(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "index.db"
        self.index = SqliteIndex(self.db_path)

    def tearDown(self) -> None:
        self.index.close()
        self._tmp.cleanup()

    def test_put_then_search_finds_the_note_by_exact_word(self) -> None:
        self.index.put(_item("a", "Kubernetes Guide", "How to deploy pods safely"))
        results = self.index.search("kubernetes")
        self.assertIn("a", results)

    def test_search_on_empty_index_returns_empty(self) -> None:
        self.assertEqual(self.index.search("anything"), [])

    def test_search_empty_query_returns_empty_not_a_crash(self) -> None:
        self.index.put(_item("a", "Title", "Body"))
        self.assertEqual(self.index.search(""), [])

    def test_put_twice_with_same_id_updates_not_duplicates(self) -> None:
        self.index.put(_item("a", "First", "original content"))
        self.index.put(_item("a", "First Updated", "revised content"))
        results = self.index.search("revised")
        self.assertEqual(results.count("a"), 1)

    def test_delete_removes_from_search_results(self) -> None:
        self.index.put(_item("a", "Removable", "unique searchable term xylophone"))
        self.index.delete("a")
        self.assertEqual(self.index.search("xylophone"), [])

    def test_search_ranks_more_relevant_result_first(self) -> None:
        self.index.put(_item("a", "Off Topic", "something about gardening"))
        self.index.put(_item("b", "On Topic", "python python python programming python"))
        results = self.index.search("python")
        self.assertEqual(results[0], "b")

    def test_search_is_typo_tolerant_via_dense_fallback(self) -> None:
        self.index.put(_item("a", "Note", "knowledge management system design"))
        results = self.index.search("knowledg managment")  # typos, no exact BM25 hit
        self.assertIn("a", results)

    def test_search_respects_limit(self) -> None:
        for i in range(5):
            self.index.put(_item(f"note-{i}", f"Note {i}", "shared searchable keyword"))
        results = self.index.search("shared", limit=2)
        self.assertEqual(len(results), 2)


class TestSqliteIndexRebuild(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "index.db"
        self.index = SqliteIndex(self.db_path)

    def tearDown(self) -> None:
        self.index.close()
        self._tmp.cleanup()

    def test_rebuild_from_items_replaces_prior_content(self) -> None:
        self.index.put(_item("stale", "Stale Note", "old unique term marmoset"))
        self.index.rebuild([_item("fresh", "Fresh Note", "new unique term giraffe")])
        self.assertEqual(self.index.search("marmoset"), [])
        self.assertIn("fresh", self.index.search("giraffe"))

    def test_open_never_leaves_a_dangling_handle_that_would_block_unlink_on_windows(
        self,
    ) -> None:
        # Deterministic version of the windows-latest bug: unlink a path
        # that sqlite3.Connection still holds a live handle to raises
        # PermissionError on Windows (POSIX allows it, so this can't be
        # observed directly on this dev machine). Simulating unlink's
        # Windows behavior with a mock proves _open() actually closes its
        # connection before propagating a failure, regardless of which OS
        # runs the test.
        corrupt_db_path = Path(self._tmp.name) / "corrupt-handle-check.db"
        corrupt_db_path.write_bytes(b"not a real sqlite file")

        real_connect = sqlite3.connect
        opened_connections = []

        def tracking_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            opened_connections.append(connection)
            return connection

        real_unlink = Path.unlink

        def windows_style_unlink(self, missing_ok=False):
            for connection in opened_connections:
                try:
                    connection.execute("SELECT 1")
                    raise PermissionError(
                        "simulated WinError 32: file still has an open handle"
                    )
                except sqlite3.ProgrammingError:
                    continue  # this connection is already closed — fine
            real_unlink(self, missing_ok=missing_ok)

        with patch("sqlite3.connect", side_effect=tracking_connect):
            with patch.object(Path, "unlink", windows_style_unlink):
                recovered_index = SqliteIndex(corrupt_db_path)  # must not raise
        try:
            self.assertEqual(recovered_index.search("anything"), [])
        finally:
            recovered_index.close()

    def test_opening_a_corrupt_db_file_recovers_instead_of_crashing(self) -> None:
        # Direct regression test for the __init__-level bug: a corrupt
        # file used to raise sqlite3.DatabaseError straight out of the
        # constructor, violating the documented "always rebuildable, never
        # crashes" contract (SPEC.md section 2, Exception & Edge Case
        # Matrix "corrupt/truncated SQLite index" row).
        corrupt_db_path = Path(self._tmp.name) / "corrupt-init.db"
        corrupt_db_path.write_bytes(b"not a real sqlite file")
        recovered_index = SqliteIndex(corrupt_db_path)  # must not raise
        try:
            self.assertEqual(recovered_index.search("anything"), [])
        finally:
            recovered_index.close()

    def test_rebuild_on_corrupt_or_missing_db_recovers_cleanly(self) -> None:
        # Uses its own isolated path, not self.db_path — setUp's self.index
        # holds an open connection to self.db_path for the whole test, and
        # on Windows a still-open handle from a DIFFERENT SqliteIndex
        # instance blocks rebuild()'s os.replace() onto that same path (no
        # amount of retrying helps; the handle is only released in
        # tearDown). Reusing self.db_path here was a test-isolation bug,
        # not a production code bug.
        corrupt_db_path = Path(self._tmp.name) / "corrupt.db"
        corrupt_db_path.write_bytes(b"not a real sqlite file")
        recovering_index = SqliteIndex(corrupt_db_path)
        recovering_index.rebuild([_item("a", "A", "content")])
        self.assertIn("a", recovering_index.search("content"))
        recovering_index.close()


class TestSqliteIndexConcurrency(unittest.TestCase):
    def test_two_index_handles_can_read_and_write_the_same_db_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "shared.db"
            writer = SqliteIndex(db_path)
            reader = SqliteIndex(db_path)
            try:
                writer.put(_item("a", "Shared", "concurrent access term"))
                results = reader.search("concurrent")
                self.assertIn("a", results)
            finally:
                writer.close()
                reader.close()


if __name__ == "__main__":
    unittest.main()
