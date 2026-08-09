"""Write classification for secondmind.store — the guard against silent clobber.

Bounded-context responsibility: decide, before any write touches disk,
whether an incoming ``put``/``import`` is a brand-new note, an identical
no-op, a nonmaterial (whitespace-only) edit, or a real content change. This
exists specifically to prevent the historical bug class where a supersede
operation minted a new id instead of updating in place, silently producing
duplicate notes (SPEC.md §5).
"""

from __future__ import annotations

from enum import Enum


class ChangeKind(Enum):
    """The outcome of comparing an incoming write against what's on disk."""

    NEW = "new"
    IDENTICAL = "identical"
    NONMATERIAL = "nonmaterial"
    MATERIAL = "material"


def classify_change(existing_body: str | None, new_body: str) -> ChangeKind:
    """Classify an incoming write relative to ``existing_body``.

    ``existing_body`` is ``None`` when no note with this id exists yet.
    Comparison is whitespace-insensitive for NONMATERIAL vs MATERIAL: two
    bodies that differ only in leading/trailing/blank-line whitespace are
    NONMATERIAL, anything else that differs is MATERIAL.
    """
    if existing_body is None:
        return ChangeKind.NEW
    if existing_body == new_body:
        return ChangeKind.IDENTICAL
    if existing_body.strip() == new_body.strip():
        return ChangeKind.NONMATERIAL
    return ChangeKind.MATERIAL
