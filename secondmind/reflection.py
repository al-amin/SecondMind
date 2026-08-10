"""Client-driven session reflection — pure data retrieval, zero LLM dependency.

Bounded-context responsibility: return recently-updated notes, most
recent first, so the *calling AI* can decide what's worth distilling into
a higher-level summary and write that summary back via
:func:`secondmind.store.VaultStore.put`. This module does no
summarization itself and makes no LLM call of any kind.

This design was corrected after real research into the 2026-07-28 MCP
spec (SPEC.md §10.2/§10.3): the original plan — the server asks the
client's LLM to summarize via MCP sampling — is not viable. A connection
negotiated at that protocol version has no back-channel for
server-initiated requests on any transport; ``create_message()``
(sampling) raises ``NoBackChannelError`` unconditionally. Returning raw
data and letting the client's own LLM (already present in the calling
AI's own turn) do the summarization sidesteps that restriction entirely,
rather than fighting it.
"""

from __future__ import annotations

from secondmind.models import KnowledgeItem, KnowledgeType
from secondmind.store import VaultStore

_DEFAULT_LIMIT = 20


def get_recent(
    store: VaultStore, limit: int = _DEFAULT_LIMIT, type: KnowledgeType | None = None
) -> list[KnowledgeItem]:
    """Return up to ``limit`` notes, most recently ``updated`` first.

    Optionally filtered by ``type``. Never summarizes or transforms the
    content — the caller (a human, or the AI client's own LLM in its own
    turn) decides what, if anything, to distill from the result.

    ``updated``'s ISO-8601-seconds resolution means two notes written
    within the same second (e.g. during a bulk migration) compare equal
    on that field alone — file mtime (float, sub-second) breaks that tie,
    confirmed necessary by direct reproduction: two ``store.put()`` calls
    executed microseconds apart in a test produced identical ``updated``
    timestamps.
    """
    items = store.list(type=type)
    items.sort(
        key=lambda item: (item.updated, store.path_for(item.id).stat().st_mtime),
        reverse=True,
    )
    return items[:limit]
