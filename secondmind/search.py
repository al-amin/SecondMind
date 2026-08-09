"""Reciprocal Rank Fusion — combines independently ranked result lists.

Bounded-context responsibility: given N ranked lists of ids (e.g. a BM25
lexical ranking and a cosine-similarity dense ranking, per SPEC.md §3),
produce one fused ranking. This module knows nothing about SQLite, FTS5, or
embeddings — ``sqlite_index.py`` produces the ranked lists this module
fuses, keeping the fusion algorithm independently testable.

Complexity: with R ranked lists of up to k items each, fusion is
O(R * k * log(R * k)) — score accumulation is O(R * k), the final sort is
O(R * k log(R * k)). For the top-k results this module is called with
(never the full corpus), this is effectively O(k log k).
"""

from __future__ import annotations

_RRF_K = 60  # standard RRF damping constant


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], limit: int | None = None
) -> list[str]:
    """Fuse ``ranked_lists`` (each a list of ids, best first) into one ranking.

    Score for an id is the sum of ``1 / (k + rank)`` across every list it
    appears in (rank is 1-indexed), where ``k`` is a damping constant — the
    standard Reciprocal Rank Fusion formula. An id in no list scores 0 and
    is absent from the result. Duplicate ids within a single list count
    only their first (best) rank.
    """
    scores: dict[str, float] = {}
    order: list[str] = []

    for ranked_list in ranked_lists:
        seen_in_this_list: set[str] = set()
        for rank, item_id in enumerate(ranked_list, start=1):
            if item_id in seen_in_this_list:
                continue
            seen_in_this_list.add(item_id)
            if item_id not in scores:
                order.append(item_id)
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (_RRF_K + rank)

    fused = sorted(order, key=lambda item_id: scores[item_id], reverse=True)
    if limit is not None:
        return fused[:limit]
    return fused
