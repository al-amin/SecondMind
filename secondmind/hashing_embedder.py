"""Stdlib-only trigram hashing embedder — the semantic half of hybrid search.

Bounded-context responsibility: turn text into a fixed-dimension vector
using only :mod:`hashlib`, with no ML model and no third-party dependency,
per the zero-install constraint (SPEC.md §2/§3). This buys typo tolerance
("knowledg managment" still matches "knowledge management") through
character-trigram overlap — it is NOT true semantic understanding (it will
not connect "car" and "automobile"). That tradeoff is the correct one for a
personal knowledge base that must run with nothing installed; a future
optional ML-backed embedder could implement the same interface behind a
try/except fallback to this one, without changing any caller.
"""

from __future__ import annotations

import hashlib
import math

_DEFAULT_DIMENSIONS = 256


class HashingEmbedder:
    """Feature-hashes character trigrams of ``text`` into an L2-normalized vector.

    Complexity: O(len(text)) to extract trigrams, O(1) amortized per
    trigram to hash and accumulate — no dictionary of a growing vocabulary
    is ever built, so memory use is bounded by ``dimensions`` regardless of
    corpus size.
    """

    def __init__(self, dimensions: int = _DEFAULT_DIMENSIONS) -> None:
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        """Return an L2-normalized ``dimensions``-length vector for ``text``.

        Empty or whitespace-only text returns an all-zero vector — never a
        division-by-zero crash on normalization.
        """
        vector = [0.0] * self._dimensions
        normalized = text.lower().strip()
        if not normalized:
            return vector

        trigrams = self._trigrams(normalized)
        for trigram in trigrams:
            index = self._hash_index(trigram)
            vector[index] += 1.0

        return self._l2_normalize(vector)

    def _trigrams(self, text: str) -> list[str]:
        padded = f"  {text}  "
        if len(padded) < 3:
            return [padded]
        return [padded[i : i + 3] for i in range(len(padded) - 2)]

    def _hash_index(self, trigram: str) -> int:
        digest = hashlib.blake2b(trigram.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self._dimensions

    def _l2_normalize(self, vector: list[float]) -> list[float]:
        magnitude = math.sqrt(sum(component**2 for component in vector))
        if magnitude == 0.0:
            return vector
        return [component / magnitude for component in vector]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors.

    Returns ``0.0`` (not a crash) if either vector has zero magnitude.
    """
    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x**2 for x in a))
    magnitude_b = math.sqrt(sum(y**2 for y in b))
    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0
    return dot_product / (magnitude_a * magnitude_b)
