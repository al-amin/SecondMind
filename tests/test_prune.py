"""Tests for secondmind.prune — TTL-based note expiry.

Traces to SPEC.md §1.1 (ttl_days: "eligible for pruning ttl_days after
updated") and ROADMAP.md item 5. ttl_days has been stored on every note
since v1 but nothing acted on it until now.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from secondmind.models import KnowledgeType
from secondmind.prune import find_expired, prune
from secondmind.store import NoteNotFoundError, VaultStore


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class PruneTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = VaultStore(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestFindExpired(PruneTestCase):
    def test_note_with_no_ttl_is_never_expired(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x")
        expired = find_expired(self.store, now="2026-08-10T00:00:00Z")
        self.assertEqual(expired, [])

    def test_note_past_its_ttl_is_expired(self) -> None:
        import time

        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x", ttl_days=1)
        # Directly manipulate the stored 'updated' timestamp to simulate
        # time passing, rather than sleeping in a test.
        note_path = Path(self._tmp.name) / "a.md"
        content = note_path.read_text(encoding="utf-8")
        content = content.replace(
            f"updated: {self.store.get('a').updated}", "updated: 2020-01-01T00:00:00Z"
        )
        note_path.write_text(content, encoding="utf-8")

        expired = find_expired(self.store, now="2026-08-10T00:00:00Z")
        self.assertEqual(expired, ["a"])

    def test_note_within_its_ttl_is_not_expired(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x", ttl_days=30)
        # updated is "now" (just written) — well within a 30-day TTL.
        expired = find_expired(self.store, now="2026-08-10T00:00:00Z")
        self.assertEqual(expired, [])

    def test_multiple_notes_only_expired_ones_returned(self) -> None:
        self.store.put(id="fresh", type=KnowledgeType.CORE, title="F", body="x", ttl_days=30)
        self.store.put(id="stale", type=KnowledgeType.CORE, title="S", body="x", ttl_days=1)
        stale_path = Path(self._tmp.name) / "stale.md"
        content = stale_path.read_text(encoding="utf-8")
        content = content.replace(
            f"updated: {self.store.get('stale').updated}", "updated: 2020-01-01T00:00:00Z"
        )
        stale_path.write_text(content, encoding="utf-8")

        expired = find_expired(self.store, now="2026-08-10T00:00:00Z")
        self.assertEqual(expired, ["stale"])


class TestPrune(PruneTestCase):
    def test_prune_deletes_expired_notes(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x", ttl_days=1)
        note_path = Path(self._tmp.name) / "a.md"
        content = note_path.read_text(encoding="utf-8")
        content = content.replace(
            f"updated: {self.store.get('a').updated}", "updated: 2020-01-01T00:00:00Z"
        )
        note_path.write_text(content, encoding="utf-8")

        result = prune(self.store, now="2026-08-10T00:00:00Z")
        self.assertEqual(result["pruned"], ["a"])
        with self.assertRaises(NoteNotFoundError):
            self.store.get("a")

    def test_prune_dry_run_does_not_delete(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x", ttl_days=1)
        note_path = Path(self._tmp.name) / "a.md"
        content = note_path.read_text(encoding="utf-8")
        content = content.replace(
            f"updated: {self.store.get('a').updated}", "updated: 2020-01-01T00:00:00Z"
        )
        note_path.write_text(content, encoding="utf-8")

        result = prune(self.store, now="2026-08-10T00:00:00Z", dry_run=True)
        self.assertEqual(result["pruned"], ["a"])
        self.store.get("a")  # must not raise — dry run never deletes

    def test_prune_on_vault_with_no_expired_notes_is_a_noop(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x")
        result = prune(self.store, now="2026-08-10T00:00:00Z")
        self.assertEqual(result["pruned"], [])
        self.store.get("a")  # still there


if __name__ == "__main__":
    unittest.main()
