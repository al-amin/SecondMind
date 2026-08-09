"""Tests for secondmind.portability — schema-versioned export/import.

Traces to SPEC.md §7 (export/import bundle schema): idempotent, forward-
tolerant of a newer schema_version than this build knows about, interop-
shaped with the existing AUPS CKL / second-brain-skill bundle format.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from secondmind.models import KnowledgeType
from secondmind.portability import export_bundle, import_bundle
from secondmind.store import VaultStore


class TestExportBundle(unittest.TestCase):
    def test_export_includes_all_notes_with_full_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            store.put(id="a", type=KnowledgeType.CORE, title="A", body="body-a", tags=["t1"])
            bundle = export_bundle(store)
            self.assertEqual(bundle["schema_version"], 1)
            self.assertEqual(bundle["count"], 1)
            item = bundle["items"][0]
            self.assertEqual(item["id"], "a")
            self.assertEqual(item["body"], "body-a")
            self.assertEqual(item["tags"], ["t1"])

    def test_export_of_empty_vault_has_zero_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            bundle = export_bundle(store)
            self.assertEqual(bundle["count"], 0)
            self.assertEqual(bundle["items"], [])


class TestImportBundle(unittest.TestCase):
    def test_import_creates_notes_in_a_fresh_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_store = VaultStore(Path(tmp) / "source")
            source_store.put(id="a", type=KnowledgeType.CORE, title="A", body="content-a")
            bundle = export_bundle(source_store)

            target_store = VaultStore(Path(tmp) / "target")
            result = import_bundle(target_store, bundle)
            self.assertEqual(result["imported"], 1)
            self.assertEqual(target_store.get("a").body, "content-a")

    def test_import_is_idempotent_no_duplicates_on_second_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_store = VaultStore(Path(tmp) / "source")
            source_store.put(id="a", type=KnowledgeType.CORE, title="A", body="content-a")
            bundle = export_bundle(source_store)

            target_store = VaultStore(Path(tmp) / "target")
            import_bundle(target_store, bundle)
            import_bundle(target_store, bundle)  # second import, same bundle

            self.assertEqual(len(target_store.list()), 1)

    def test_import_forward_tolerant_of_newer_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            bundle = {
                "schema_version": 999,  # newer than anything this build knows
                "count": 1,
                "items": [
                    {
                        "id": "future-note",
                        "type": "core",
                        "title": "Future",
                        "body": "from a newer schema",
                        "created": "2026-08-09T00:00:00Z",
                        "updated": "2026-08-09T00:00:00Z",
                    }
                ],
            }
            result = import_bundle(store, bundle)  # must not raise
            self.assertEqual(result["imported"], 1)
            self.assertEqual(store.get("future-note").body, "from a newer schema")

    def test_import_dry_run_does_not_write_anything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            bundle = {
                "schema_version": 1,
                "count": 1,
                "items": [
                    {
                        "id": "a",
                        "type": "core",
                        "title": "A",
                        "body": "x",
                        "created": "2026-08-09T00:00:00Z",
                        "updated": "2026-08-09T00:00:00Z",
                    }
                ],
            }
            result = import_bundle(store, bundle, dry_run=True)
            self.assertEqual(result["imported"], 1)
            self.assertEqual(store.list(), [])

    def test_import_with_missing_items_key_returns_zero_imported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            result = import_bundle(store, {"schema_version": 1, "count": 0})
            self.assertEqual(result["imported"], 0)

    def test_import_skips_malformed_item_and_reports_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp))
            bundle = {
                "schema_version": 1,
                "count": 1,
                "items": [{"id": "broken"}],  # missing required fields
            }
            result = import_bundle(store, bundle)
            self.assertEqual(result["imported"], 0)
            self.assertEqual(len(result["errors"]), 1)


class TestExportImportRoundTrip(unittest.TestCase):
    def test_full_round_trip_preserves_every_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_store = VaultStore(Path(tmp) / "source")
            source_store.put(
                id="full",
                type=KnowledgeType.PROCEDURAL,
                title="Full Note",
                body="Complete content here.",
                scope="proj-x",
                tags=["a", "b"],
                ttl_days=30,
            )
            bundle = export_bundle(source_store)

            target_store = VaultStore(Path(tmp) / "target")
            import_bundle(target_store, bundle)

            original = source_store.get("full")
            restored = target_store.get("full")
            self.assertEqual(original, restored)


if __name__ == "__main__":
    unittest.main()
