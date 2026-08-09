"""Tests for secondmind.search — Reciprocal Rank Fusion.

Traces to SPEC.md §3 (hybrid search: BM25 lexical rank + cosine dense
rank, fused via RRF). This module fuses two already-ranked id lists — it
has no knowledge of SQLite or embeddings; sqlite_index.py supplies the
ranked lists.
"""

from __future__ import annotations

import unittest

from secondmind.search import reciprocal_rank_fusion


class TestReciprocalRankFusion(unittest.TestCase):
    def test_item_ranked_first_in_both_lists_ranks_first_in_fusion(self) -> None:
        lexical = ["a", "b", "c"]
        dense = ["a", "c", "b"]
        fused = reciprocal_rank_fusion([lexical, dense])
        self.assertEqual(fused[0], "a")

    def test_item_present_in_both_lists_outranks_item_in_only_one(self) -> None:
        lexical = ["a", "b"]
        dense = ["c", "a"]
        fused = reciprocal_rank_fusion([lexical, dense])
        # "a" appears in both lists (ranks 1 and 2); "b" and "c" each appear
        # in only one list. "a" should fuse to the top.
        self.assertEqual(fused[0], "a")

    def test_empty_lists_return_empty_result(self) -> None:
        self.assertEqual(reciprocal_rank_fusion([[], []]), [])

    def test_single_list_preserves_its_order(self) -> None:
        self.assertEqual(reciprocal_rank_fusion([["x", "y", "z"]]), ["x", "y", "z"])

    def test_disjoint_lists_are_still_combined_without_error(self) -> None:
        fused = reciprocal_rank_fusion([["a", "b"], ["c", "d"]])
        self.assertEqual(set(fused), {"a", "b", "c", "d"})

    def test_no_list_at_all_returns_empty(self) -> None:
        self.assertEqual(reciprocal_rank_fusion([]), [])

    def test_result_respects_limit(self) -> None:
        fused = reciprocal_rank_fusion([["a", "b", "c", "d"]], limit=2)
        self.assertEqual(len(fused), 2)

    def test_duplicate_entries_within_one_list_are_deduplicated(self) -> None:
        fused = reciprocal_rank_fusion([["a", "a", "b"]])
        self.assertEqual(fused, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
