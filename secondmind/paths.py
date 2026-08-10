"""Vault/index path resolution, note id safety, and atomic file writes.

Bounded-context responsibility: every filesystem boundary in SecondMind goes
through this module. No other module constructs a note path directly or
writes a vault file without going through :func:`atomic_write_text` — that
is what makes the atomicity and path-traversal guarantees in SPEC.md §2 and
§1.3 actually hold, rather than being promises no code enforces.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

_NOTE_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")

MAX_NOTE_ID_LENGTH = 128
"""The hard cap every note id must respect — shared with
:func:`secondmind.models.generate_note_id`, which must never produce an id
this module's own :func:`validate_note_id` would reject."""

_REPLACE_RETRY_ATTEMPTS = 5
_REPLACE_RETRY_DELAY_SECONDS = 0.1


def replace_with_windows_retry(src: Path, dst: Path) -> None:
    """``os.replace(src, dst)``, retrying on Windows' transient
    ``PermissionError``/``WinError 5``.

    On Windows, a rename target must have zero open handles from *any*
    process, and handle release after closing a file isn't always
    instantaneous — antivirus real-time scanning briefly reopening a
    just-written file is a well-documented cause. POSIX rename has no
    handle-based locking and never hits this — confirmed by this exact
    error surfacing only on a real windows-latest CI runner, never
    locally. A short bounded retry is the standard mitigation other
    cross-platform tools (pip, npm) use for this error class.
    """
    for attempt in range(_REPLACE_RETRY_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == _REPLACE_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS)


class InvalidNoteIdError(ValueError):
    """Raised when a note id fails the strict safety pattern.

    Any id that is empty, oversized, contains path separators (``/`` or
    ``\\``), traversal segments (``..``), a null byte, or characters outside
    ``[a-z0-9-]`` is rejected before it ever reaches a filesystem call —
    this is what makes path traversal via a note id structurally
    impossible rather than merely unlikely.
    """


def validate_note_id(note_id: str) -> None:
    """Raise :class:`InvalidNoteIdError` if ``note_id`` is unsafe.

    A valid id matches ``^[a-z0-9-]+$`` and is at most 128 characters. This
    single check is sufficient to rule out path traversal, absolute paths
    (Unix or Windows), and null-byte injection, because none of those can
    be expressed using only lowercase letters, digits, and hyphens.
    """
    if not isinstance(note_id, str) or not note_id:
        raise InvalidNoteIdError("note id must be a non-empty string")
    if len(note_id) > MAX_NOTE_ID_LENGTH:
        raise InvalidNoteIdError(f"note id exceeds {MAX_NOTE_ID_LENGTH} characters")
    if not _NOTE_ID_PATTERN.match(note_id):
        raise InvalidNoteIdError(
            f"note id {note_id!r} must match [a-z0-9-]+ — no slashes, "
            "backslashes, dots, or other characters"
        )


def note_path(vault_root: Path, note_id: str) -> Path:
    """Return the on-disk path for ``note_id`` inside ``vault_root``.

    Validates ``note_id`` first, so the returned path is guaranteed to be a
    direct child of ``vault_root`` — it can never resolve outside it.
    """
    validate_note_id(note_id)
    return vault_root / f"{note_id}.md"


def default_vault_root(env: dict[str, str] | None = None) -> Path:
    """Resolve the vault root: ``SECONDMIND_VAULT`` env var, else ``~/.secondmind/vault``.

    Never a hardcoded personal path — the fallback is always derived from
    :func:`pathlib.Path.home`, per SPEC.md §2.
    """
    environ = os.environ if env is None else env
    override = environ.get("SECONDMIND_VAULT")
    if override:
        return Path(override)
    return Path.home() / ".secondmind" / "vault"


def default_index_db(env: dict[str, str] | None = None) -> Path:
    """Resolve the index db path: ``SECONDMIND_INDEX_DB`` env var, else ``~/.secondmind/index.db``."""
    environ = os.environ if env is None else env
    override = environ.get("SECONDMIND_INDEX_DB")
    if override:
        return Path(override)
    return Path.home() / ".secondmind" / "index.db"


def atomic_write_text(target: Path, content: str) -> None:
    """Write ``content`` to ``target`` atomically.

    Writes to a temp file in the same directory as ``target``, closes the
    handle, then calls :func:`os.replace` to atomically swap it onto
    ``target``. A crash or exception at any point before the final
    ``os.replace`` leaves ``target`` exactly as it was — never truncated or
    partially written (SPEC.md §2). The handle is closed before the
    replace so this works identically on Windows, where a file cannot be
    replaced while a handle to it is still open.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.parent / f".{target.name}.tmp-{os.getpid()}"
    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        replace_with_windows_retry(temp_path, target)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise
