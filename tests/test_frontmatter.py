"""Tests for secondmind.frontmatter — the hand-rolled YAML-subset codec.

Traces to SPEC.md §1.1 (frontmatter field list) and §2 (storage guarantees:
a malformed/missing frontmatter must never crash, per the Exception & Edge
Case Matrix "Input validation" row).
"""

from __future__ import annotations

import unittest

from secondmind.frontmatter import (
    FrontmatterError,
    dump,
    parse,
)


class TestParseRoundTrip(unittest.TestCase):
    def test_parses_scalar_fields(self) -> None:
        text = (
            "---\n"
            "id: my-note\n"
            "type: semantic\n"
            "title: My Note\n"
            "created: 2026-08-09T00:00:00Z\n"
            "updated: 2026-08-09T00:00:00Z\n"
            "---\n"
            "Body text here.\n"
        )
        fm, body = parse(text)
        self.assertEqual(fm["id"], "my-note")
        self.assertEqual(fm["type"], "semantic")
        self.assertEqual(fm["title"], "My Note")
        self.assertEqual(body, "Body text here.\n")

    def test_parses_list_fields(self) -> None:
        text = (
            "---\n"
            "id: my-note\n"
            "tags: [alpha, beta, gamma]\n"
            "entities: []\n"
            "---\n"
            "Body.\n"
        )
        fm, _ = parse(text)
        self.assertEqual(fm["tags"], ["alpha", "beta", "gamma"])
        self.assertEqual(fm["entities"], [])

    def test_parses_null_field(self) -> None:
        text = "---\nid: my-note\nttl_days: null\nsupersedes: null\n---\nBody.\n"
        fm, _ = parse(text)
        self.assertIsNone(fm["ttl_days"])
        self.assertIsNone(fm["supersedes"])

    def test_parses_int_field(self) -> None:
        text = "---\nid: my-note\nttl_days: 30\n---\nBody.\n"
        fm, _ = parse(text)
        self.assertEqual(fm["ttl_days"], 30)
        self.assertIsInstance(fm["ttl_days"], int)

    def test_dump_then_parse_round_trips_exactly(self) -> None:
        fm = {
            "id": "roundtrip-note",
            "type": "core",
            "title": "Round Trip",
            "scope": "",
            "entities": ["Al Amin", "SecondMind"],
            "tags": ["test", "roundtrip"],
            "source": "manual",
            "created": "2026-08-09T00:00:00Z",
            "updated": "2026-08-09T00:00:00Z",
            "ttl_days": None,
            "supersedes": None,
        }
        body = "This is the note body.\n\nWith multiple paragraphs.\n"
        text = dump(fm, body)
        parsed_fm, parsed_body = parse(text)
        self.assertEqual(parsed_fm, fm)
        self.assertEqual(parsed_body, body)

    def test_dump_then_parse_round_trips_empty_lists_and_strings(self) -> None:
        fm = {"id": "x", "tags": [], "scope": "", "title": ""}
        text = dump(fm, "")
        parsed_fm, parsed_body = parse(text)
        self.assertEqual(parsed_fm["tags"], [])
        self.assertEqual(parsed_fm["scope"], "")
        self.assertEqual(parsed_fm["title"], "")
        self.assertEqual(parsed_body, "")

    def test_values_containing_colons_are_preserved(self) -> None:
        fm = {"id": "x", "title": "Time is 10:30, ratio 2:1"}
        text = dump(fm, "body")
        parsed_fm, _ = parse(text)
        self.assertEqual(parsed_fm["title"], "Time is 10:30, ratio 2:1")

    def test_values_containing_hash_are_preserved(self) -> None:
        fm = {"id": "x", "title": "Issue #123 needs a fix"}
        text = dump(fm, "body")
        parsed_fm, _ = parse(text)
        self.assertEqual(parsed_fm["title"], "Issue #123 needs a fix")


class TestParseEdgeCases(unittest.TestCase):
    def test_missing_frontmatter_raises_frontmatter_error(self) -> None:
        with self.assertRaises(FrontmatterError):
            parse("Just a body, no frontmatter at all.\n")

    def test_unterminated_frontmatter_raises_frontmatter_error(self) -> None:
        with self.assertRaises(FrontmatterError):
            parse("---\nid: my-note\ntitle: Unterminated\n")

    def test_empty_frontmatter_block_parses_to_empty_dict(self) -> None:
        text = "---\n---\nBody.\n"
        fm, body = parse(text)
        self.assertEqual(fm, {})
        self.assertEqual(body, "Body.\n")

    def test_empty_string_raises_frontmatter_error(self) -> None:
        with self.assertRaises(FrontmatterError):
            parse("")

    def test_malformed_line_without_colon_raises_frontmatter_error(self) -> None:
        text = "---\nid: my-note\nthis line has no colon\n---\nBody.\n"
        with self.assertRaises(FrontmatterError):
            parse(text)

    def test_body_with_no_trailing_newline_is_preserved(self) -> None:
        text = "---\nid: x\n---\nNo trailing newline"
        _, body = parse(text)
        self.assertEqual(body, "No trailing newline")

    def test_body_that_itself_contains_triple_dash_is_preserved(self) -> None:
        text = "---\nid: x\n---\nBody with\n---\na horizontal rule inside\n"
        _, body = parse(text)
        self.assertEqual(body, "Body with\n---\na horizontal rule inside\n")


if __name__ == "__main__":
    unittest.main()
