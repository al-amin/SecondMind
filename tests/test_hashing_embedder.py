"""Tests for secondmind.hashing_embedder — stdlib-only semantic layer.

Traces to SPEC.md §3 (hybrid search). Trigram/hashing embedding, not a real
ML model — documented honestly as typo-tolerant, not truly semantic.
"""

from __future__ import annotations

import math
import unittest

from secondmind.hashing_embedder import HashingEmbedder, cosine_similarity


class TestHashingEmbedder(unittest.TestCase):
    def setUp(self) -> None:
        self.embedder = HashingEmbedder(dimensions=256)

    def test_embed_returns_fixed_dimension_vector(self) -> None:
        vector = self.embedder.embed("hello world")
        self.assertEqual(len(vector), 256)

    def test_embed_is_deterministic(self) -> None:
        first = self.embedder.embed("some text")
        second = self.embedder.embed("some text")
        self.assertEqual(first, second)

    def test_embed_empty_string_returns_zero_vector(self) -> None:
        vector = self.embedder.embed("")
        self.assertEqual(vector, [0.0] * 256)

    def test_embed_is_l2_normalized_for_nonempty_text(self) -> None:
        vector = self.embedder.embed("some reasonably long piece of text")
        magnitude = math.sqrt(sum(component**2 for component in vector))
        self.assertAlmostEqual(magnitude, 1.0, places=6)

    def test_similar_text_has_higher_similarity_than_unrelated_text(self) -> None:
        a = self.embedder.embed("the quick brown fox jumps")
        b = self.embedder.embed("the quick brown fox leaps")
        c = self.embedder.embed("stock market prices fell today")
        self.assertGreater(cosine_similarity(a, b), cosine_similarity(a, c))

    def test_typo_tolerant_similarity_still_positive(self) -> None:
        a = self.embedder.embed("knowledge management system")
        b = self.embedder.embed("knowledg managment system")  # typos
        self.assertGreater(cosine_similarity(a, b), 0.3)


class TestCosineSimilarity(unittest.TestCase):
    def test_identical_vectors_similarity_is_one(self) -> None:
        vector = [0.6, 0.8]
        self.assertAlmostEqual(cosine_similarity(vector, vector), 1.0, places=6)

    def test_orthogonal_vectors_similarity_is_zero(self) -> None:
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0, places=6)

    def test_zero_vector_similarity_is_zero_not_a_crash(self) -> None:
        self.assertEqual(cosine_similarity([0.0, 0.0], [1.0, 0.0]), 0.0)


if __name__ == "__main__":
    unittest.main()
