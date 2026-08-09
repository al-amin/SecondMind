"""Tests for secondmind.conflict — write classification before every put/import.

Traces to SPEC.md §5. Exists specifically to prevent the historical bug
class where a "supersede" operation minted a new id instead of updating in
place, causing duplicate notes.
"""

from __future__ import annotations

import unittest

from secondmind.conflict import ChangeKind, classify_change


class TestClassifyChange(unittest.TestCase):
    def test_no_existing_item_is_new(self) -> None:
        self.assertEqual(classify_change(existing_body=None, new_body="hello"), ChangeKind.NEW)

    def test_identical_body_is_identical(self) -> None:
        self.assertEqual(
            classify_change(existing_body="same text", new_body="same text"),
            ChangeKind.IDENTICAL,
        )

    def test_whitespace_only_difference_is_nonmaterial(self) -> None:
        self.assertEqual(
            classify_change(existing_body="hello world\n", new_body="hello world\n\n"),
            ChangeKind.NONMATERIAL,
        )

    def test_leading_trailing_whitespace_difference_is_nonmaterial(self) -> None:
        self.assertEqual(
            classify_change(existing_body="  hello  ", new_body="hello"),
            ChangeKind.NONMATERIAL,
        )

    def test_actual_content_change_is_material(self) -> None:
        self.assertEqual(
            classify_change(existing_body="hello world", new_body="goodbye world"),
            ChangeKind.MATERIAL,
        )

    def test_empty_to_nonempty_is_material(self) -> None:
        self.assertEqual(
            classify_change(existing_body="", new_body="new content"),
            ChangeKind.MATERIAL,
        )

    def test_empty_to_empty_is_identical(self) -> None:
        self.assertEqual(classify_change(existing_body="", new_body=""), ChangeKind.IDENTICAL)


if __name__ == "__main__":
    unittest.main()
