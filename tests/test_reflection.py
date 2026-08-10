"""Tests for secondmind.reflection — client-driven session reflection.

Traces to ROADMAP.md item 7 and SPEC.md §10.3's corrected design: the
original plan (server asks the client's LLM to summarize via MCP
sampling) is not viable under the 2026-07-28 spec (no back-channel for
server-initiated requests on any transport). Corrected design: a tool
returns raw recent notes; the CALLING AI does the summarization in its
own turn and writes the result back via secondmind_put. This module is
therefore pure data retrieval — get_recent() — with zero LLM dependency,
zero sampling, zero back-channel usage.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from secondmind.models import KnowledgeType
from secondmind.reflection import get_recent
from secondmind.store import VaultStore


class TestGetRecent(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = VaultStore(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _put_with_updated(self, note_id: str, updated: str) -> None:
        self.store.put(id=note_id, type=KnowledgeType.CORE, title=note_id, body="x")
        path = Path(self._tmp.name) / f"{note_id}.md"
        content = path.read_text(encoding="utf-8")
        current_updated = self.store.get(note_id).updated
        content = content.replace(f"updated: {current_updated}", f"updated: {updated}")
        path.write_text(content, encoding="utf-8")

    def test_returns_notes_ordered_most_recently_updated_first(self) -> None:
        self._put_with_updated("old", "2020-01-01T00:00:00Z")
        self._put_with_updated("newest", "2026-01-03T00:00:00Z")
        self._put_with_updated("middle", "2026-01-02T00:00:00Z")

        recent = get_recent(self.store)
        self.assertEqual([item.id for item in recent], ["newest", "middle", "old"])

    def test_respects_limit(self) -> None:
        for i in range(5):
            self._put_with_updated(f"note-{i}", f"2026-01-0{i+1}T00:00:00Z")

        recent = get_recent(self.store, limit=2)
        self.assertEqual(len(recent), 2)
        self.assertEqual([item.id for item in recent], ["note-4", "note-3"])

    def test_default_limit_is_reasonable_not_the_whole_vault(self) -> None:
        for i in range(30):
            self.store.put(id=f"note-{i}", type=KnowledgeType.CORE, title=f"N{i}", body="x")
        recent = get_recent(self.store)
        self.assertLessEqual(len(recent), 20)

    def test_empty_vault_returns_empty(self) -> None:
        self.assertEqual(get_recent(self.store), [])

    def test_filters_by_type(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x")
        self.store.put(id="b", type=KnowledgeType.EPISODIC, title="B", body="y")
        recent = get_recent(self.store, type=KnowledgeType.EPISODIC)
        self.assertEqual([item.id for item in recent], ["b"])


if __name__ == "__main__":
    unittest.main()
