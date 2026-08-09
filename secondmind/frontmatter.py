"""YAML-subset frontmatter codec for SecondMind notes.

Bounded-context responsibility: convert between a note's on-disk text
representation (``---`` delimited frontmatter block + Markdown body) and an
in-memory ``(dict, str)`` pair. Deliberately hand-rolled instead of using
PyYAML — the zero-pip-dependency constraint (SPEC.md §2, README "Zero-install
philosophy") means the core package cannot require any third-party library,
and the frontmatter fields (SPEC.md §1.1) only ever need scalars, lists of
scalars, and null — a small enough grammar that a full YAML parser buys
nothing but a dependency.
"""

from __future__ import annotations

DELIMITER = "---"


class FrontmatterError(ValueError):
    """Raised when text cannot be parsed as a valid frontmatter document."""


def _parse_scalar(raw: str) -> object:
    """Parse a single YAML-subset scalar: null, int, or string.

    An empty value (``key:`` with nothing after the colon) is the empty
    string, not null — only the literal token ``null`` means None. This
    keeps ``scope: ""`` round-trip-safe (SPEC.md §1.1 default is ``""``,
    not ``None``).
    """
    if raw == "null":
        return None
    if raw == "":
        return ""
    try:
        return int(raw)
    except ValueError:
        return raw


def _parse_value(raw: str) -> object:
    """Parse a YAML-subset value: an inline list, or a scalar."""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [item.strip() for item in inner.split(",")]
    return _parse_scalar(raw)


def _dump_value(value: object) -> str:
    """Render a Python value back into its YAML-subset text form."""
    if value is None:
        return "null"
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return str(value)


def parse(text: str) -> tuple[dict[str, object], str]:
    """Parse ``text`` into ``(frontmatter_dict, body)``.

    Raises ``FrontmatterError`` if ``text`` has no opening delimiter, no
    closing delimiter, or a frontmatter line that is not a recognizable
    ``key: value`` pair. Never raises on a well-formed but semantically
    empty document (``---\\n---\\n``), which parses to ``({}, body)``.
    """
    lines = text.split("\n")
    if not lines or lines[0] != DELIMITER:
        raise FrontmatterError("document does not start with a frontmatter delimiter")

    closing_index = None
    for index in range(1, len(lines)):
        if lines[index] == DELIMITER:
            closing_index = index
            break

    if closing_index is None:
        raise FrontmatterError("frontmatter block has no closing delimiter")

    frontmatter: dict[str, object] = {}
    for line in lines[1:closing_index]:
        if not line.strip():
            continue
        if ":" not in line:
            raise FrontmatterError(f"malformed frontmatter line: {line!r}")
        key, _, raw_value = line.partition(":")
        frontmatter[key.strip()] = _parse_value(raw_value)

    body = "\n".join(lines[closing_index + 1 :])
    return frontmatter, body


def dump(frontmatter: dict[str, object], body: str) -> str:
    """Render ``(frontmatter, body)`` back into on-disk note text.

    ``dump`` and ``parse`` are exact inverses for any value this codec can
    produce (round-trip is verified by ``tests/test_frontmatter.py``).
    """
    lines = [DELIMITER]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {_dump_value(value)}")
    lines.append(DELIMITER)
    return "\n".join(lines) + "\n" + body
