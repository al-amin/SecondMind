"""Pure domain model for a SecondMind note.

Bounded-context responsibility: define what a note *is*, with zero I/O and
zero dependency on how it is stored or searched. ``store.py``,
``sqlite_index.py``, and ``portability.py`` all operate on
:class:`KnowledgeItem` instances; none of them redefine the shape.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum

from secondmind.paths import MAX_NOTE_ID_LENGTH

_REQUIRED_FIELDS = ("id", "type", "title", "created", "updated")
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class KnowledgeType(Enum):
    """The four CoALA-inspired memory types SecondMind supports (SPEC.md §1.2)."""

    CORE = "core"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"

    @classmethod
    def from_str(cls, value: str) -> "KnowledgeType":
        """Look up a member by its string value, raising ``ValueError`` if unknown."""
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"unknown knowledge type: {value!r}")


@dataclass(frozen=True)
class KnowledgeItem:
    """One note: frontmatter fields plus body, per SPEC.md §1.1.

    Frozen so a stored/returned item can never be mutated in place by a
    caller — any change must go through :func:`secondmind.store.put`, which
    is where conflict classification (SPEC.md §5) happens.
    """

    id: str
    type: KnowledgeType
    title: str
    body: str
    created: str
    updated: str
    scope: str = ""
    entities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source: str = "manual"
    ttl_days: int | None = None
    supersedes: str | None = None

    def to_frontmatter(self) -> tuple[dict[str, object], str]:
        """Convert to the ``(frontmatter_dict, body)`` shape ``frontmatter.dump`` expects."""
        frontmatter: dict[str, object] = {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "scope": self.scope,
            "entities": list(self.entities),
            "tags": list(self.tags),
            "source": self.source,
            "created": self.created,
            "updated": self.updated,
            "ttl_days": self.ttl_days,
            "supersedes": self.supersedes,
        }
        return frontmatter, self.body

    @classmethod
    def from_frontmatter(cls, frontmatter: dict[str, object], body: str) -> "KnowledgeItem":
        """Build a :class:`KnowledgeItem` from a parsed frontmatter dict + body.

        Raises ``ValueError`` if a required field (SPEC.md §1.1) is missing
        or ``type`` is not one of the four known values.
        """
        missing = [name for name in _REQUIRED_FIELDS if name not in frontmatter]
        if missing:
            raise ValueError(f"frontmatter missing required field(s): {missing}")

        return cls(
            id=str(frontmatter["id"]),
            type=KnowledgeType.from_str(str(frontmatter["type"])),
            title=str(frontmatter["title"]),
            body=body,
            created=str(frontmatter["created"]),
            updated=str(frontmatter["updated"]),
            scope=str(frontmatter.get("scope") or ""),
            entities=list(frontmatter.get("entities") or []),
            tags=list(frontmatter.get("tags") or []),
            source=str(frontmatter.get("source") or "manual"),
            ttl_days=frontmatter.get("ttl_days"),  # type: ignore[arg-type]
            supersedes=frontmatter.get("supersedes"),  # type: ignore[arg-type]
        )


_ID_SUFFIX_DIGEST_SIZE = 4  # -> 8 hex chars
_ID_RESERVED_FOR_SUFFIX_AND_ATTEMPTS = 1 + (_ID_SUFFIX_DIGEST_SIZE * 2) + len("-999")


def generate_note_id(title: str, existing_ids: set[str]) -> str:
    """Generate a unique note id: a slug of ``title`` plus a short hash suffix.

    Guaranteed to match the ``[a-z0-9-]+`` shape and the
    :data:`secondmind.paths.MAX_NOTE_ID_LENGTH` cap :func:`secondmind.paths.validate_note_id`
    requires, and guaranteed unique against ``existing_ids``.

    The slug is truncated, not the title itself, so an ordinary long
    descriptive title (a real scenario — SPEC.md's own documented title
    limit is 300 chars, well past the point a naive untruncated slug would
    exceed the id cap) never fails outright. Truncating the slug rather
    than raising is the right call here: the hash suffix already
    guarantees uniqueness on its own, so information lost to truncation
    doesn't create a collision risk — a bug fix, not a workaround, found
    via a real 180-character title in tests/test_complex_scenarios.py.
    """
    slug = _SLUG_PATTERN.sub("-", title.lower()).strip("-")
    if not slug:
        slug = "note"

    max_slug_length = MAX_NOTE_ID_LENGTH - _ID_RESERVED_FOR_SUFFIX_AND_ATTEMPTS
    slug = slug[:max_slug_length].strip("-") or "note"

    suffix = hashlib.blake2b(title.encode("utf-8"), digest_size=_ID_SUFFIX_DIGEST_SIZE).hexdigest()
    candidate = f"{slug}-{suffix}"
    attempt = 0
    while candidate in existing_ids:
        attempt += 1
        candidate = f"{slug}-{suffix}-{attempt}"
    return candidate
