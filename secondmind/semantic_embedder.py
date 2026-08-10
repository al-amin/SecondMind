"""Optional real-ML embedder — opt-in only, never a required dependency.

Bounded-context responsibility: give ``store``/``sqlite_index`` a way to
use a genuine semantic model (e.g. ``sentence-transformers``) instead of
:class:`secondmind.hashing_embedder.HashingEmbedder`'s trigram hashing,
for users who explicitly want better recall and are willing to install
and download a model. This module still lives in the zero-install core
(``secondmind/``, not ``secondmind_mcp/``) because ``sentence_transformers``
is imported lazily, inside a function, wrapped in ``try/except`` — the
module itself imports cleanly with nothing installed, so it never breaks
the core-isolation guarantee (verified by ``tests/test_core_isolation.py``,
which checks import statements, not runtime behavior).

Install with ``pip install -e ".[semantic]"``. If the extra isn't
installed, or the model fails to download (offline machine, first run
with no network), :func:`load_embedder` silently falls back to
``HashingEmbedder`` — new users never download anything by default, and
existing users who installed the extra still get a working system if the
model happens to be unavailable at import time.
"""

from __future__ import annotations

import os
from typing import Protocol

from secondmind.hashing_embedder import HashingEmbedder

_DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


class Embedder(Protocol):
    """The interface any embedder — hashing or semantic — must satisfy."""

    def embed(self, text: str) -> list[float]: ...


class _SentenceTransformerEmbedder:
    """Wraps a ``sentence-transformers`` model behind the ``Embedder`` interface."""

    def __init__(self, model: object) -> None:
        self._model = model

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        return [float(component) for component in vector]


def _try_load_sentence_transformer(model_name: str) -> _SentenceTransformerEmbedder | None:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None

    try:
        model = SentenceTransformer(model_name)
    except Exception:
        # Any failure at load time (no network for first download, disk
        # full, incompatible torch build, etc.) — never crash the caller,
        # fall back to the always-available embedder instead.
        return None

    return _SentenceTransformerEmbedder(model)


def load_embedder(prefer_semantic: bool = False, model_name: str = _DEFAULT_MODEL_NAME) -> Embedder:
    """Return a real semantic embedder if available and requested, else the default.

    ``prefer_semantic=False`` (the default) never even attempts the
    import — the zero-install path is the literal default, not just a
    fallback that happens to trigger. Only when a caller explicitly asks
    for semantic embeddings does this module try (and possibly fail
    silently back to) ``HashingEmbedder``.
    """
    if not prefer_semantic:
        return HashingEmbedder()

    embedder = _try_load_sentence_transformer(model_name)
    if embedder is not None:
        return embedder
    return HashingEmbedder()


def load_embedder_from_env(env: dict[str, str] | None = None) -> Embedder:
    """Return the embedder configured by ``SECONDMIND_EMBEDDER``.

    Unset or any value other than ``"semantic"`` -> ``HashingEmbedder``
    (the zero-install default). ``SECONDMIND_EMBEDDER=semantic`` opts
    into :func:`load_embedder`'s real-model attempt, with the same silent
    fallback if the extra isn't installed or the model can't load.
    """
    environ = os.environ if env is None else env
    prefer_semantic = environ.get("SECONDMIND_EMBEDDER", "").strip().lower() == "semantic"
    return load_embedder(prefer_semantic=prefer_semantic)
