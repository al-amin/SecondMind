"""Schema-versioned, idempotent export/import — the portability layer.

Bounded-context responsibility: convert between a :class:`secondmind.store.VaultStore`
and the bundle shape defined in SPEC.md §7. Idempotent (importing the same
bundle twice never duplicates, because every import goes through
:meth:`VaultStore.put`, which is conflict-classified) and forward-tolerant
(a bundle from a newer, unknown ``schema_version`` is imported using only
the fields this build understands, never a crash).
"""

from __future__ import annotations

from secondmind.models import KnowledgeType
from secondmind.store import VaultStore

SCHEMA_VERSION = 1

_REQUIRED_ITEM_FIELDS = ("id", "type", "title", "body", "created", "updated")


def export_bundle(store: VaultStore) -> dict[str, object]:
    """Export every note in ``store`` as a schema-versioned bundle (SPEC.md §7)."""
    items = []
    for item in store.list():
        frontmatter, body = item.to_frontmatter()
        entry = dict(frontmatter)
        entry["body"] = body
        items.append(entry)
    return {"schema_version": SCHEMA_VERSION, "count": len(items), "items": items}


def import_bundle(
    store: VaultStore, bundle: dict[str, object], dry_run: bool = False
) -> dict[str, object]:
    """Import ``bundle`` into ``store``.

    Idempotent: re-importing the same bundle updates in place (via
    ``VaultStore.put``'s conflict classification) rather than duplicating.
    Forward-tolerant: a ``schema_version`` newer than :data:`SCHEMA_VERSION`
    is accepted — only the fields this build recognizes are used, unknown
    fields are ignored. A malformed item (missing a required field) is
    skipped and recorded in ``errors`` rather than aborting the whole
    import.
    """
    imported = 0
    skipped = 0
    errors: list[str] = []

    for entry in bundle.get("items", []):  # type: ignore[union-attr]
        missing = [name for name in _REQUIRED_ITEM_FIELDS if name not in entry]
        if missing:
            skipped += 1
            errors.append(f"item {entry.get('id', '<unknown>')!r} missing field(s): {missing}")
            continue

        if not dry_run:
            store.put(
                id=entry["id"],
                type=KnowledgeType.from_str(entry["type"]),
                title=entry["title"],
                body=entry["body"],
                scope=entry.get("scope", ""),
                entities=entry.get("entities", []),
                tags=entry.get("tags", []),
                source=entry.get("source", "manual"),
                ttl_days=entry.get("ttl_days"),
                supersedes=entry.get("supersedes"),
                # Preserve the original history rather than re-stamping
                # with the import time — a faithful restore, not a new
                # write. Found necessary via a real CI failure where the
                # round-trip test's two timestamps differed by exactly the
                # time it took a slow Windows runner to run put() twice.
                created=entry.get("created"),
                updated=entry.get("updated"),
            )
        imported += 1

    return {"imported": imported, "skipped": skipped, "errors": errors}
