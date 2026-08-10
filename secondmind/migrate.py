"""Scan an existing external Markdown+frontmatter vault into an import-ready bundle.

Bounded-context responsibility: adapt any directory of ``.md`` files with
YAML-subset frontmatter (an existing personal Obsidian vault, or the
AUPS CKL / second-brain-skill vault, which SPEC.md §7 already documents as
field-for-field compatible) into the bundle shape
:func:`secondmind.portability.import_bundle` already knows how to import.
No new import machinery — this is purely a directory-to-bundle adapter in
front of the existing, already-tested import path.

A note missing an optional field gets a sensible default (see
:func:`_adapt_note`); a note with no frontmatter at all, or an
unparseable one, is skipped and reported rather than aborting the whole
scan — one bad file in a large personal vault must never block importing
the rest.
"""

from __future__ import annotations

import time
from pathlib import Path

from secondmind.frontmatter import FrontmatterError, parse
from secondmind.models import KnowledgeType, generate_note_id
from secondmind.paths import InvalidNoteIdError, validate_note_id
from secondmind.portability import SCHEMA_VERSION

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    return time.strftime(_ISO_FORMAT, time.gmtime())


def _sanitized_id(candidate: str, existing_ids: set[str]) -> str:
    """Return ``candidate`` if it's already a valid SecondMind id, else a
    slugified, collision-free replacement.

    An external vault's filenames or id conventions (spaces, punctuation,
    uppercase, underscores) very often don't match SecondMind's strict
    ``[a-z0-9-]+`` pattern — this is what makes a scanned bundle actually
    importable via :func:`secondmind.portability.import_bundle`, which
    calls :func:`secondmind.paths.validate_note_id` and would otherwise
    raise on nearly every real personal vault's filenames.
    """
    try:
        validate_note_id(candidate)
        if candidate not in existing_ids:
            return candidate
    except InvalidNoteIdError:
        pass
    return generate_note_id(candidate, existing_ids)


def _adapt_note(
    frontmatter: dict[str, object], body: str, filename_stem: str, existing_ids: set[str]
) -> dict[str, object]:
    """Fill in sensible defaults for any field the external note lacks."""
    note_id = _sanitized_id(str(frontmatter.get("id") or filename_stem), existing_ids)

    raw_type = frontmatter.get("type")
    try:
        knowledge_type = KnowledgeType.from_str(str(raw_type)) if raw_type else KnowledgeType.SEMANTIC
    except ValueError:
        knowledge_type = KnowledgeType.SEMANTIC

    title = str(frontmatter.get("title") or filename_stem)
    now = _now_iso()

    return {
        "id": note_id,
        "type": knowledge_type.value,
        "title": title,
        "body": body,
        "scope": str(frontmatter.get("scope") or ""),
        "entities": list(frontmatter.get("entities") or []),
        "tags": list(frontmatter.get("tags") or []),
        "source": str(frontmatter.get("source") or "migrated"),
        "created": str(frontmatter.get("created") or now),
        "updated": str(frontmatter.get("updated") or now),
        "ttl_days": frontmatter.get("ttl_days"),
        "supersedes": frontmatter.get("supersedes"),
    }


def scan_external_vault(vault_root: Path) -> dict[str, object]:
    """Scan every ``*.md`` file under ``vault_root`` into an import-ready bundle.

    Files with no frontmatter block (or a malformed one) are skipped —
    never raised, never aborting the scan of the rest of the vault.
    """
    items = []
    seen_ids: set[str] = set()
    for path in sorted(vault_root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        try:
            frontmatter, body = parse(text)
        except FrontmatterError:
            continue
        note = _adapt_note(frontmatter, body, path.stem, seen_ids)
        seen_ids.add(note["id"])
        items.append(note)

    return {"schema_version": SCHEMA_VERSION, "count": len(items), "items": items}
