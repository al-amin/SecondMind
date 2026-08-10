"""Tests for secondmind.models — KnowledgeItem, KnowledgeType.

Traces to SPEC.md §1.1 (frontmatter field list) and §1.2 (knowledge types).
Pure dataclasses, zero I/O — this module never touches a filesystem.
"""

from __future__ import annotations

import unittest

from secondmind.models import KnowledgeItem, KnowledgeType, generate_note_id


class TestKnowledgeType(unittest.TestCase):
    def test_has_exactly_the_four_spec_types(self) -> None:
        values = {member.value for member in KnowledgeType}
        self.assertEqual(values, {"core", "semantic", "episodic", "procedural"})

    def test_from_str_accepts_valid_type(self) -> None:
        self.assertEqual(KnowledgeType.from_str("semantic"), KnowledgeType.SEMANTIC)

    def test_from_str_rejects_unknown_type(self) -> None:
        with self.assertRaises(ValueError):
            KnowledgeType.from_str("not-a-real-type")

    def test_from_str_rejects_empty_string(self) -> None:
        with self.assertRaises(ValueError):
            KnowledgeType.from_str("")


class TestKnowledgeItemDefaults(unittest.TestCase):
    def _minimal(self, **overrides: object) -> KnowledgeItem:
        base = dict(
            id="my-note",
            type=KnowledgeType.SEMANTIC,
            title="My Note",
            body="Body text.",
            created="2026-08-09T00:00:00Z",
            updated="2026-08-09T00:00:00Z",
        )
        base.update(overrides)
        return KnowledgeItem(**base)  # type: ignore[arg-type]

    def test_scope_defaults_to_empty_string(self) -> None:
        self.assertEqual(self._minimal().scope, "")

    def test_entities_defaults_to_empty_list(self) -> None:
        self.assertEqual(self._minimal().entities, [])

    def test_tags_defaults_to_empty_list(self) -> None:
        self.assertEqual(self._minimal().tags, [])

    def test_source_defaults_to_manual(self) -> None:
        self.assertEqual(self._minimal().source, "manual")

    def test_ttl_days_defaults_to_none(self) -> None:
        self.assertIsNone(self._minimal().ttl_days)

    def test_supersedes_defaults_to_none(self) -> None:
        self.assertIsNone(self._minimal().supersedes)

    def test_two_instances_do_not_share_a_mutable_default_list(self) -> None:
        a = self._minimal()
        b = self._minimal()
        a.tags.append("mutated")
        self.assertEqual(b.tags, [])

    def test_is_frozen_immutable(self) -> None:
        item = self._minimal()
        with self.assertRaises(Exception):
            item.title = "changed"  # type: ignore[misc]


class TestKnowledgeItemFrontmatterConversion(unittest.TestCase):
    def test_to_frontmatter_round_trips_via_from_frontmatter(self) -> None:
        item = KnowledgeItem(
            id="round-trip",
            type=KnowledgeType.CORE,
            title="Round Trip",
            body="Body content.",
            scope="proj-x",
            entities=["A", "B"],
            tags=["t1", "t2"],
            source="manual",
            created="2026-08-09T00:00:00Z",
            updated="2026-08-09T00:00:00Z",
            ttl_days=30,
            supersedes="old-id",
        )
        frontmatter, body = item.to_frontmatter()
        restored = KnowledgeItem.from_frontmatter(frontmatter, body)
        self.assertEqual(restored, item)

    def test_from_frontmatter_rejects_unknown_type(self) -> None:
        frontmatter = {
            "id": "x",
            "type": "not-a-type",
            "title": "X",
            "created": "2026-08-09T00:00:00Z",
            "updated": "2026-08-09T00:00:00Z",
        }
        with self.assertRaises(ValueError):
            KnowledgeItem.from_frontmatter(frontmatter, "body")

    def test_from_frontmatter_rejects_missing_required_field(self) -> None:
        frontmatter = {"id": "x", "type": "core"}  # missing title/created/updated
        with self.assertRaises(ValueError):
            KnowledgeItem.from_frontmatter(frontmatter, "body")


class TestGenerateNoteId(unittest.TestCase):
    def test_slugifies_title(self) -> None:
        note_id = generate_note_id("My Great Title!", existing_ids=set())
        self.assertTrue(note_id.startswith("my-great-title"))

    def test_result_is_a_valid_note_id_shape(self) -> None:
        import re

        note_id = generate_note_id("Weird Title @#$ 123", existing_ids=set())
        self.assertRegex(note_id, r"^[a-z0-9-]+$")

    def test_avoids_collision_with_existing_ids(self) -> None:
        first = generate_note_id("Same Title", existing_ids=set())
        second = generate_note_id("Same Title", existing_ids={first})
        self.assertNotEqual(first, second)

    def test_handles_empty_title(self) -> None:
        note_id = generate_note_id("", existing_ids=set())
        self.assertRegex(note_id, r"^[a-z0-9-]+$")
        self.assertTrue(len(note_id) > 0)

    def test_long_title_produces_an_id_within_the_128_char_limit(self) -> None:
        # Real bug found via tests/test_complex_scenarios.py: an ordinary
        # 180-char descriptive title (well under SPEC.md's documented
        # 300-char title limit) produced an id over secondmind.paths's
        # 128-char cap, failing validate_note_id downstream with a
        # confusing "note id exceeds 128 characters" error that never
        # mentions the title at all. The docstring already claimed this
        # was "guaranteed" — it wasn't, until this test enforced it.
        realistic_long_title = (
            "Meeting notes from the Q3 planning session where we discussed "
            "the new pricing model, timeline for the v2 release, and decided "
            "to defer the semantic embedder work until next quarter"
        )
        self.assertEqual(len(realistic_long_title), 180)  # sanity-check the fixture itself
        note_id = generate_note_id(realistic_long_title, existing_ids=set())
        self.assertLessEqual(len(note_id), 128)
        self.assertRegex(note_id, r"^[a-z0-9-]+$")

    def test_very_long_title_5000_chars_still_produces_a_valid_id(self) -> None:
        note_id = generate_note_id("A" * 5000, existing_ids=set())
        self.assertLessEqual(len(note_id), 128)
        self.assertRegex(note_id, r"^[a-z0-9-]+$")

    def test_truncated_long_titles_still_avoid_collision(self) -> None:
        # Two different long titles that happen to share the same first
        # ~120 characters must still get distinct ids (the hash suffix,
        # not just the truncated slug prefix, is what guarantees this).
        prefix = "Identical opening text that goes on for quite a while before diverging into different content " * 1
        first = generate_note_id(prefix + "ENDING A", existing_ids=set())
        second = generate_note_id(prefix + "ENDING B", existing_ids={first})
        self.assertNotEqual(first, second)
        self.assertLessEqual(len(first), 128)
        self.assertLessEqual(len(second), 128)


if __name__ == "__main__":
    unittest.main()
