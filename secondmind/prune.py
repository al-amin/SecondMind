"""TTL-based note expiry — acts on the ttl_days field stored since v1.

Bounded-context responsibility: decide which notes are past their
``ttl_days`` (SPEC.md §1.1: "eligible for pruning ttl_days after
updated") and delete them via :meth:`secondmind.store.VaultStore.delete`.
A note with no ``ttl_days`` is never eligible — pruning is strictly
opt-in per note, never a default expiry policy.
"""

from __future__ import annotations

import time

from secondmind.store import VaultStore

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    return time.strftime(_ISO_FORMAT, time.gmtime())


def _parse_iso(value: str) -> float:
    return time.mktime(time.strptime(value, _ISO_FORMAT))


def find_expired(store: VaultStore, now: str | None = None) -> list[str]:
    """Return the ids of every note whose ``ttl_days`` has elapsed since ``updated``.

    ``now`` defaults to the current UTC time; pass an explicit ISO 8601
    string for deterministic testing.
    """
    now_ts = _parse_iso(now) if now is not None else _parse_iso(_now_iso())
    expired = []
    for item in store.list():
        if item.ttl_days is None:
            continue
        updated_ts = _parse_iso(item.updated)
        elapsed_days = (now_ts - updated_ts) / 86400
        if elapsed_days >= item.ttl_days:
            expired.append(item.id)
    return expired


def prune(store: VaultStore, now: str | None = None, dry_run: bool = False) -> dict[str, object]:
    """Delete every expired note (per :func:`find_expired`), unless ``dry_run``.

    Returns ``{"pruned": [ids]}`` — the ids that were (or, in a dry run,
    would have been) deleted.
    """
    expired = find_expired(store, now=now)
    if not dry_run:
        for note_id in expired:
            store.delete(note_id)
    return {"pruned": expired}
