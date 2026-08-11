"""Vault-backed CRUD orchestration for SecondMind notes.

Bounded-context responsibility: the vault (Markdown + frontmatter files) is
the single source of truth (SPEC.md §2). This module is the only place that
reads or writes it directly — ``cli.py``, ``secondmind_mcp/server.py``, and
``sqlite_index.py`` (rebuild) all go through :class:`VaultStore`, never
through raw file I/O of their own. Every write here runs through
:mod:`secondmind.conflict` first, which is what closes the historical
duplicate-id-minting bug class described in SPEC.md §5.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from secondmind.conflict import ChangeKind, classify_change
from secondmind.frontmatter import dump, parse
from secondmind.models import KnowledgeItem, KnowledgeType, generate_note_id
from secondmind.paths import atomic_write_text, note_path, validate_note_id


class NoteNotFoundError(KeyError):
    """Raised when an operation references a note id that does not exist."""


@dataclass(frozen=True)
class PutResult:
    """Outcome of a :meth:`VaultStore.put` call."""

    id: str
    created: str
    updated: str
    kind: ChangeKind


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class VaultStore:
    """CRUD operations against a single vault directory."""

    def __init__(self, vault_root: Path) -> None:
        self._vault_root = vault_root

    @property
    def vault_root(self) -> Path:
        """The vault directory this store reads/writes — read-only, callers
        (the dashboard's settings display) must never mutate it in place."""
        return self._vault_root

    def _existing_ids(self) -> set[str]:
        if not self._vault_root.exists():
            return set()
        return {path.stem for path in self._vault_root.glob("*.md")}

    def _read_item(self, note_id: str) -> KnowledgeItem:
        path = note_path(self._vault_root, note_id)
        if not path.exists():
            raise NoteNotFoundError(note_id)
        text = path.read_text(encoding="utf-8")
        frontmatter, body = parse(text)
        return KnowledgeItem.from_frontmatter(frontmatter, body)

    def _write_item(self, item: KnowledgeItem) -> None:
        path = note_path(self._vault_root, item.id)
        frontmatter, body = item.to_frontmatter()
        atomic_write_text(path, dump(frontmatter, body))

    def put(
        self,
        *,
        id: str | None,
        type: KnowledgeType,
        title: str,
        body: str,
        scope: str = "",
        entities: list[str] | None = None,
        tags: list[str] | None = None,
        source: str = "manual",
        ttl_days: int | None = None,
        supersedes: str | None = None,
        created: str | None = None,
        updated: str | None = None,
    ) -> PutResult:
        """Create or update a note, classifying the change before writing (SPEC.md §5).

        ``created``/``updated``, when explicitly provided, are used
        verbatim instead of the current time — needed for a faithful
        export/import restore (see :func:`secondmind.portability.import_bundle`),
        which must preserve a note's original history rather than
        re-stamping it with the import time. Ordinary callers (the CLI,
        the MCP adapter) never pass these, so their behavior — timestamp
        "now" — is unchanged.
        """
        if id is not None:
            validate_note_id(id)
            resolved_id = id
        else:
            resolved_id = generate_note_id(title, self._existing_ids())

        existing_body: str | None = None
        resolved_created = created if created is not None else _now_iso()
        try:
            existing = self._read_item(resolved_id)
            existing_body = existing.body
            if created is None:
                resolved_created = existing.created
        except NoteNotFoundError:
            pass

        kind = classify_change(existing_body, body)
        if kind == ChangeKind.IDENTICAL:
            existing_item = self._read_item(resolved_id)
            return PutResult(
                id=resolved_id, created=existing_item.created, updated=existing_item.updated, kind=kind
            )

        created = resolved_created
        updated = updated if updated is not None else _now_iso()
        item = KnowledgeItem(
            id=resolved_id,
            type=type,
            title=title,
            body=body,
            created=created,
            updated=updated,
            scope=scope,
            entities=entities or [],
            tags=tags or [],
            source=source,
            ttl_days=ttl_days,
            supersedes=supersedes,
        )
        self._write_item(item)
        return PutResult(id=resolved_id, created=created, updated=updated, kind=kind)

    def get(self, note_id: str) -> KnowledgeItem:
        """Return the note with ``note_id``, raising :class:`NoteNotFoundError` if absent."""
        return self._read_item(note_id)

    def path_for(self, note_id: str) -> Path:
        """Return the on-disk path for ``note_id`` (may not exist yet)."""
        return note_path(self._vault_root, note_id)

    def delete(self, note_id: str) -> None:
        """Delete the note with ``note_id``, raising :class:`NoteNotFoundError` if absent."""
        path = note_path(self._vault_root, note_id)
        if not path.exists():
            raise NoteNotFoundError(note_id)
        path.unlink()

    def list(
        self, *, type: KnowledgeType | None = None, tag: str | None = None
    ) -> list[KnowledgeItem]:
        """Return every note in the vault, optionally filtered by type and/or tag."""
        if not self._vault_root.exists():
            return []
        items = [self._read_item(path.stem) for path in sorted(self._vault_root.glob("*.md"))]
        if type is not None:
            items = [item for item in items if item.type == type]
        if tag is not None:
            items = [item for item in items if tag in item.tags]
        return items

    def supersede(self, note_id: str, new_body: str) -> KnowledgeItem:
        """Replace ``note_id``'s body in place, reusing the same id.

        Never mints a new id — see SPEC.md §1.3/§5 and the pinned
        regression test in ``tests/test_store.py`` for the historical bug
        this specifically guards against.
        """
        existing = self._read_item(note_id)
        updated_item = KnowledgeItem(
            id=existing.id,
            type=existing.type,
            title=existing.title,
            body=new_body,
            created=existing.created,
            updated=_now_iso(),
            scope=existing.scope,
            entities=existing.entities,
            tags=existing.tags,
            source=existing.source,
            ttl_days=existing.ttl_days,
            supersedes=existing.supersedes,
        )
        self._write_item(updated_item)
        return updated_item
