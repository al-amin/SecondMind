"""Tests for secondmind.migrate — importing an existing external vault.

Traces to ROADMAP.md item 9. v1 deliberately starts from an empty vault;
this scans any directory of Markdown+frontmatter files (an existing
personal Obsidian vault, or the AUPS CKL/second-brain-skill vault, which
SPEC.md §7 already documents as field-for-field compatible) and imports
whatever it can via the existing, already-tested import_bundle() path —
no new import machinery, just a directory-to-bundle adapter in front of
it. A malformed file is skipped and reported, never crashes the scan.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from secondmind.migrate import scan_external_vault
from secondmind.models import KnowledgeType
from secondmind.portability import import_bundle
from secondmind.store import VaultStore


class TestScanExternalVault(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, filename: str, content: str) -> None:
        (self.external_root / filename).write_text(content, encoding="utf-8")

    def test_scans_a_fully_compatible_note(self) -> None:
        self._write(
            "a.md",
            "---\nid: a\ntype: core\ntitle: A\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\nbody content\n",
        )
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["count"], 1)
        self.assertEqual(bundle["items"][0]["id"], "a")
        self.assertEqual(bundle["items"][0]["body"], "body content\n")

    def test_scans_multiple_notes(self) -> None:
        self._write(
            "a.md",
            "---\nid: a\ntype: core\ntitle: A\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\nx\n",
        )
        self._write(
            "b.md",
            "---\nid: b\ntype: semantic\ntitle: B\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\ny\n",
        )
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["count"], 2)
        self.assertEqual({item["id"] for item in bundle["items"]}, {"a", "b"})

    def test_note_missing_id_gets_one_generated_from_filename(self) -> None:
        self._write(
            "my-note.md",
            "---\ntype: core\ntitle: My Note\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\nx\n",
        )
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["count"], 1)
        self.assertTrue(bundle["items"][0]["id"])

    def test_note_missing_type_defaults_to_semantic(self) -> None:
        self._write(
            "a.md",
            "---\nid: a\ntitle: A\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\nx\n",
        )
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["items"][0]["type"], "semantic")

    def test_note_missing_title_defaults_to_filename(self) -> None:
        self._write(
            "untitled-note.md",
            "---\nid: a\ntype: core\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\nx\n",
        )
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["items"][0]["title"], "untitled-note")

    def test_note_missing_timestamps_get_generated(self) -> None:
        self._write("a.md", "---\nid: a\ntype: core\ntitle: A\n---\nx\n")
        bundle = scan_external_vault(self.external_root)
        item = bundle["items"][0]
        self.assertTrue(item["created"])
        self.assertTrue(item["updated"])

    def test_note_with_no_frontmatter_at_all_is_skipped_and_reported(self) -> None:
        self._write("plain.md", "Just plain text, no frontmatter block.\n")
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["count"], 0)

    def test_note_with_unrecognized_type_falls_back_to_semantic(self) -> None:
        self._write(
            "a.md",
            "---\nid: a\ntype: not-a-real-type\ntitle: A\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\nx\n",
        )
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["items"][0]["type"], "semantic")

    def test_empty_directory_returns_empty_bundle(self) -> None:
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["count"], 0)
        self.assertEqual(bundle["items"], [])

    def test_non_markdown_files_are_ignored(self) -> None:
        self._write("notes.txt", "not a markdown file")
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["count"], 0)

    def test_scanned_bundle_has_the_current_schema_version(self) -> None:
        bundle = scan_external_vault(self.external_root)
        self.assertEqual(bundle["schema_version"], 1)

    def test_filename_with_spaces_and_punctuation_produces_a_valid_id(self) -> None:
        # A realistic Obsidian vault filename — must not surface an id
        # that fails secondmind.paths.validate_note_id downstream, since
        # scan_external_vault's whole point is feeding import_bundle().
        self._write(
            "My Weird Note Name!.md",
            "---\ntype: core\ntitle: Test\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\nx\n",
        )
        bundle = scan_external_vault(self.external_root)
        import re

        self.assertRegex(bundle["items"][0]["id"], r"^[a-z0-9-]+$")

    def test_frontmatter_id_with_invalid_characters_is_sanitized(self) -> None:
        # An external system's own id convention might not match
        # SecondMind's [a-z0-9-]+ pattern (e.g. underscores, uppercase).
        self._write(
            "a.md",
            "---\nid: My_Weird_ID\ntype: core\ntitle: A\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\nx\n",
        )
        bundle = scan_external_vault(self.external_root)
        self.assertRegex(bundle["items"][0]["id"], r"^[a-z0-9-]+$")

    def test_sanitized_ids_do_not_collide_across_similarly_named_files(self) -> None:
        # Punctuation here is deliberately POSIX+Windows-safe (no
        # <>:"/\|?* — all reserved on Windows) since the point of this
        # test is id collision after sanitization, not filesystem
        # character limits (covered separately by the space/"!" case in
        # test_filename_with_spaces_and_punctuation_produces_a_valid_id).
        self._write(
            "Note One!.md",
            "---\ntype: core\ntitle: One\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\nx\n",
        )
        self._write(
            "Note One!!.md",
            "---\ntype: core\ntitle: One\ncreated: 2026-01-01T00:00:00Z\n"
            "updated: 2026-01-01T00:00:00Z\n---\ny\n",
        )
        bundle = scan_external_vault(self.external_root)
        ids = [item["id"] for item in bundle["items"]]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate ids: {ids}")


class TestScanThenImportIntegration(unittest.TestCase):
    def test_scanned_bundle_imports_cleanly_into_a_secondmind_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            external_root = Path(tmp) / "external"
            external_root.mkdir()
            (external_root / "a.md").write_text(
                "---\nid: a\ntype: core\ntitle: A\ncreated: 2026-01-01T00:00:00Z\n"
                "updated: 2026-01-01T00:00:00Z\n---\nimported body\n",
                encoding="utf-8",
            )
            bundle = scan_external_vault(external_root)

            store = VaultStore(Path(tmp) / "secondmind-vault")
            result = import_bundle(store, bundle)
            self.assertEqual(result["imported"], 1)
            self.assertEqual(store.get("a").body, "imported body\n")
            self.assertEqual(store.get("a").type, KnowledgeType.CORE)


if __name__ == "__main__":
    unittest.main()
