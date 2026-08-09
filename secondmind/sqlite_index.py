"""Disposable/rebuildable SQLite search index — the speed layer over the vault.

Bounded-context responsibility: fast hybrid search over notes. This index
is never the only place a fact lives (SPEC.md §2) — :meth:`SqliteIndex.rebuild`
regenerates it entirely from a list of :class:`KnowledgeItem`, so deleting
the index file and calling ``rebuild`` is always a safe recovery path.

Search combines two independently ranked lists (SPEC.md §3):
- **Lexical**: SQLite FTS5, which IS an inverted index (token -> posting
  list of note ids) with a built-in ``bm25()`` ranking function. Lookup is
  O(log n + k): a B-tree seek plus k matching postings, never a full-table
  scan.
- **Dense**: cosine similarity over :class:`secondmind.hashing_embedder.HashingEmbedder`
  vectors, computed over the (small, personal-scale) corpus already loaded
  for a query — O(n) in the number of notes, acceptable at the thousands-of-notes
  scale this project targets (see SPEC.md §8 performance targets).

The two ranked lists are fused with :func:`secondmind.search.reciprocal_rank_fusion`.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from secondmind.hashing_embedder import HashingEmbedder, cosine_similarity
from secondmind.models import KnowledgeItem, KnowledgeType
from secondmind.search import reciprocal_rank_fusion

_MIN_DENSE_SIMILARITY = 0.25  # below this, hash collisions dominate over real similarity

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    embedding TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    id UNINDEXED, title, body
);
"""


def _fts5_available(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
        connection.execute("DROP TABLE _fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


class SqliteIndex:
    """A rebuildable FTS5 + hashing-embedder hybrid search index."""

    def __init__(self, db_path: Path, embedder: HashingEmbedder | None = None) -> None:
        self._db_path = db_path
        self._embedder = embedder or HashingEmbedder()
        self._connection = self._open(db_path)
        self._fts5_available = _fts5_available(self._connection)
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def _open(self, db_path: Path) -> sqlite3.Connection:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(db_path), check_same_thread=False)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def close(self) -> None:
        self._connection.close()

    def put(self, item: KnowledgeItem) -> None:
        """Insert or update ``item`` in the index (idempotent on ``item.id``)."""
        embedding = json.dumps(self._embedder.embed(f"{item.title}\n{item.body}"))
        self._connection.execute(
            "INSERT INTO items (id, type, title, embedding) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET type=excluded.type, title=excluded.title, "
            "embedding=excluded.embedding",
            (item.id, item.type.value, item.title, embedding),
        )
        self._connection.execute("DELETE FROM items_fts WHERE id = ?", (item.id,))
        self._connection.execute(
            "INSERT INTO items_fts (id, title, body) VALUES (?, ?, ?)",
            (item.id, item.title, item.body),
        )
        self._connection.commit()

    def delete(self, note_id: str) -> None:
        """Remove ``note_id`` from the index. A no-op if it was never present."""
        self._connection.execute("DELETE FROM items WHERE id = ?", (note_id,))
        self._connection.execute("DELETE FROM items_fts WHERE id = ?", (note_id,))
        self._connection.commit()

    def _lexical_search(self, query: str, limit: int) -> list[str]:
        if not self._fts5_available:
            like_query = f"%{query}%"
            rows = self._connection.execute(
                "SELECT id FROM items_fts WHERE title LIKE ? OR body LIKE ? LIMIT ?",
                (like_query, like_query, limit),
            ).fetchall()
            return [row[0] for row in rows]

        try:
            rows = self._connection.execute(
                "SELECT id FROM items_fts WHERE items_fts MATCH ? ORDER BY bm25(items_fts) LIMIT ?",
                (query, limit),
            ).fetchall()
            return [row[0] for row in rows]
        except sqlite3.OperationalError:
            return []

    def _dense_search(self, query: str, limit: int) -> list[str]:
        query_vector = self._embedder.embed(query)
        rows = self._connection.execute("SELECT id, embedding FROM items").fetchall()
        scored = [
            (row[0], cosine_similarity(query_vector, json.loads(row[1]))) for row in rows
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [
            note_id
            for note_id, score in scored[:limit]
            if score >= _MIN_DENSE_SIMILARITY
        ]

    def search(self, query: str, limit: int = 20) -> list[str]:
        """Return up to ``limit`` note ids ranked by hybrid BM25+cosine relevance.

        An empty (or whitespace-only) query returns an empty list rather
        than matching everything.
        """
        if not query.strip():
            return []
        lexical = self._lexical_search(query, limit)
        dense = self._dense_search(query, limit)
        return reciprocal_rank_fusion([lexical, dense], limit=limit)

    def rebuild(self, items: list[KnowledgeItem]) -> None:
        """Fully regenerate the index from ``items`` — safe to call on a corrupt db.

        Rebuilds into a temporary file, then atomically swaps it onto the
        live db path, so a reader querying during a rebuild never sees an
        empty or half-populated index (SPEC.md §2).
        """
        self._connection.close()

        temp_path = self._db_path.parent / f".{self._db_path.name}.tmp-{os.getpid()}"
        temp_path.unlink(missing_ok=True)
        temp_connection = self._open(temp_path)
        temp_connection.executescript(_SCHEMA)
        temp_connection.commit()

        rebuilder = SqliteIndex.__new__(SqliteIndex)
        rebuilder._db_path = temp_path
        rebuilder._embedder = self._embedder
        rebuilder._connection = temp_connection
        rebuilder._fts5_available = _fts5_available(temp_connection)
        for item in items:
            rebuilder.put(item)
        rebuilder.close()

        os.replace(temp_path, self._db_path)
        for suffix in ("-wal", "-shm"):
            stale = Path(f"{self._db_path}{suffix}")
            stale.unlink(missing_ok=True)

        self._connection = self._open(self._db_path)
        self._fts5_available = _fts5_available(self._connection)
