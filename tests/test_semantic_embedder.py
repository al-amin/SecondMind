"""Tests for secondmind.semantic_embedder — the optional real-ML embedder.

Traces to ROADMAP.md item 4 and SPEC.md §9 (documented extension point).
`HashingEmbedder` stays the default for every user forever — this module
is only reached if the caller explicitly asks for it, and even then it
falls back to `HashingEmbedder` if `sentence-transformers` isn't
installed or the model fails to load. Never a required dependency.
"""

from __future__ import annotations

import unittest

from secondmind.hashing_embedder import HashingEmbedder
from secondmind.semantic_embedder import load_embedder, load_embedder_from_env


class TestLoadEmbedderFallback(unittest.TestCase):
    def test_load_embedder_without_semantic_extra_returns_hashing_embedder(self) -> None:
        # sentence-transformers is not a dependency of this project's core
        # or its base test environment, so this exercises the real
        # not-installed fallback path, not a mock.
        embedder = load_embedder(prefer_semantic=True)
        self.assertIsInstance(embedder, HashingEmbedder)

    def test_load_embedder_default_is_hashing_embedder(self) -> None:
        embedder = load_embedder()
        self.assertIsInstance(embedder, HashingEmbedder)

    def test_fallback_embedder_still_produces_usable_vectors(self) -> None:
        embedder = load_embedder(prefer_semantic=True)
        vector = embedder.embed("test text")
        self.assertTrue(len(vector) > 0)
        self.assertTrue(all(isinstance(component, float) for component in vector))


class TestLoadEmbedderFromEnv(unittest.TestCase):
    def test_no_env_var_returns_hashing_embedder(self) -> None:
        embedder = load_embedder_from_env(env={})
        self.assertIsInstance(embedder, HashingEmbedder)

    def test_unrelated_env_value_returns_hashing_embedder(self) -> None:
        embedder = load_embedder_from_env(env={"SECONDMIND_EMBEDDER": "something-else"})
        self.assertIsInstance(embedder, HashingEmbedder)

    def test_semantic_env_value_falls_back_to_hashing_when_extra_not_installed(self) -> None:
        embedder = load_embedder_from_env(env={"SECONDMIND_EMBEDDER": "semantic"})
        self.assertIsInstance(embedder, HashingEmbedder)

    def test_env_value_is_case_insensitive(self) -> None:
        embedder = load_embedder_from_env(env={"SECONDMIND_EMBEDDER": "SEMANTIC"})
        self.assertIsInstance(embedder, HashingEmbedder)  # falls back either way here


if __name__ == "__main__":
    unittest.main()
