"""Tests for secondmind.store — vault-backed CRUD orchestration.

Traces to SPEC.md sections 1.3, 2, 5. Includes a pinned regression test for
the historical bug where supersede() minted a new id instead of reusing the
prior one, which caused duplicate notes in a prior system.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from secondmind.conflict import ChangeKind
from secondmind.models import KnowledgeItem, KnowledgeType
from secondmind.paths import InvalidNoteIdError
from secondmind.store import NoteNotFoundError, VaultStore


class TestVaultStorePutAndGet(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.vault_root = Path(self._tmp.name)
        self.store = VaultStore(self.vault_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_put_then_get_round_trips(self) -> None:
        result = self.store.put(
            id=None,
            type=KnowledgeType.SEMANTIC,
            title="First Note",
            body="Hello, SecondMind.",
        )
        item = self.store.get(result.id)
        self.assertEqual(item.title, "First Note")
        self.assertEqual(item.body, "Hello, SecondMind.")

    def test_put_without_id_generates_one(self) -> None:
        result = self.store.put(id=None, type=KnowledgeType.CORE, title="Auto Id", body="x")
        self.assertRegex(result.id, r"^[a-z0-9-]+$")

    def test_put_with_explicit_id_uses_it(self) -> None:
        result = self.store.put(
            id="explicit-id", type=KnowledgeType.CORE, title="Explicit", body="x"
        )
        self.assertEqual(result.id, "explicit-id")

    def test_get_missing_note_raises_not_found(self) -> None:
        with self.assertRaises(NoteNotFoundError):
            self.store.get("does-not-exist")

    def test_put_rejects_unsafe_id(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            self.store.put(id="../escape", type=KnowledgeType.CORE, title="X", body="x")

    def test_put_sets_created_and_updated_on_new_note(self) -> None:
        result = self.store.put(id="new-note", type=KnowledgeType.CORE, title="X", body="x")
        item = self.store.get("new-note")
        self.assertTrue(item.created)
        self.assertEqual(item.created, item.updated)

    def test_put_material_update_bumps_updated_but_keeps_created(self) -> None:
        self.store.put(id="note-1", type=KnowledgeType.CORE, title="X", body="v1")
        first = self.store.get("note-1")
        result = self.store.put(id="note-1", type=KnowledgeType.CORE, title="X", body="v2")
        self.assertEqual(result.kind, ChangeKind.MATERIAL)
        second = self.store.get("note-1")
        self.assertEqual(second.created, first.created)
        self.assertEqual(second.body, "v2")

    def test_put_identical_content_is_a_noop(self) -> None:
        self.store.put(id="note-2", type=KnowledgeType.CORE, title="X", body="same")
        first = self.store.get("note-2")
        result = self.store.put(id="note-2", type=KnowledgeType.CORE, title="X", body="same")
        self.assertEqual(result.kind, ChangeKind.IDENTICAL)
        second = self.store.get("note-2")
        self.assertEqual(second.updated, first.updated)


class TestVaultStoreList(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = VaultStore(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_list_returns_all_notes(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x")
        self.store.put(id="b", type=KnowledgeType.SEMANTIC, title="B", body="x")
        ids = {item.id for item in self.store.list()}
        self.assertEqual(ids, {"a", "b"})

    def test_list_filters_by_type(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x")
        self.store.put(id="b", type=KnowledgeType.SEMANTIC, title="B", body="x")
        results = self.store.list(type=KnowledgeType.CORE)
        self.assertEqual([item.id for item in results], ["a"])

    def test_list_on_empty_vault_returns_empty(self) -> None:
        self.assertEqual(self.store.list(), [])

    def test_list_filters_by_tag(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x", tags=["keep"])
        self.store.put(id="b", type=KnowledgeType.CORE, title="B", body="x", tags=["drop"])
        results = self.store.list(tag="keep")
        self.assertEqual([item.id for item in results], ["a"])


class TestVaultStoreSupersede(unittest.TestCase):
    """Pinned regression test: supersede must reuse the prior id.

    A previous system minted a new id on supersede instead of updating in
    place, which silently produced duplicate notes. This test exists to
    make sure SecondMind never regresses into that exact bug.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = VaultStore(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_supersede_reuses_the_prior_id_never_mints_a_new_one(self) -> None:
        original = self.store.put(
            id="lesson-1", type=KnowledgeType.SEMANTIC, title="Lesson", body="v1"
        )
        superseded = self.store.supersede(original.id, new_body="v2 — corrected")

        self.assertEqual(superseded.id, original.id)

        all_ids = {item.id for item in self.store.list()}
        self.assertEqual(all_ids, {"lesson-1"})  # never {"lesson-1", "lesson-1-<hash>"}

        item = self.store.get("lesson-1")
        self.assertEqual(item.body, "v2 — corrected")

    def test_supersede_missing_note_raises_not_found(self) -> None:
        with self.assertRaises(NoteNotFoundError):
            self.store.supersede("does-not-exist", new_body="x")


class TestVaultStoreCrashSafety(unittest.TestCase):
    def test_vault_directory_auto_created_on_first_put(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_root = Path(tmp) / "does" / "not" / "exist" / "yet"
            store = VaultStore(vault_root)
            store.put(id="x", type=KnowledgeType.CORE, title="X", body="x")
            self.assertTrue((vault_root / "x.md").exists())


if __name__ == "__main__":
    unittest.main()
