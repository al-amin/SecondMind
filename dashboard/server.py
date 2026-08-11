"""Web dashboard — stdlib http.server only, no Node/npm/build step.

Bounded-context responsibility: expose search/browse/view/put/supersede
over HTTP for a browser that can't run Obsidian or a CLI. v1 was
read-only by explicit decision; v2 (ROADMAP.md item 8) adds write
endpoints that go through :meth:`secondmind.store.VaultStore.put`/
:meth:`secondmind.store.VaultStore.supersede` — the exact same
conflict-safety guarantees the CLI and MCP adapter already use, never a
separate, weaker write path. Bound to ``127.0.0.1`` only — never
reachable from another machine on the LAN. All SQLite access goes through
parameterized queries via :mod:`secondmind.sqlite_index` and
:mod:`secondmind.store`, never raw SQL built from request input.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from secondmind.models import KnowledgeType
from secondmind.paths import InvalidNoteIdError
from secondmind.sqlite_index import SqliteIndex
from secondmind.store import NoteNotFoundError, VaultStore

_STATIC_DIR = Path(__file__).resolve().parent
_STATIC_FILES = {
    "/": ("index.html", "text/html"),
    "/index.html": ("index.html", "text/html"),
    "/app.js": ("app.js", "application/javascript"),
    "/app.css": ("app.css", "text/css"),
}


class DashboardHandler(BaseHTTPRequestHandler):
    """Routes GET requests only — no do_POST/do_PUT/do_DELETE exist on this class."""

    def route(self, path: str) -> tuple[int, str, str]:
        """Dispatch ``path`` to the matching handler, returning ``(status, content_type, body)``.

        Kept separate from ``do_GET`` so it can be exercised in-process by
        tests without opening a real socket.
        """
        parsed = urlparse(path)
        query = parse_qs(parsed.query)

        if parsed.path in _STATIC_FILES:
            filename, content_type = _STATIC_FILES[parsed.path]
            content = (_STATIC_DIR / filename).read_text(encoding="utf-8")
            return 200, content_type, content

        if parsed.path == "/api/search":
            search_query = query.get("q", [""])[0]
            ids = self._index.search(search_query, limit=20) if search_query else []
            results = []
            for note_id in ids:
                try:
                    item = self._store.get(note_id)
                    results.append({"id": item.id, "title": item.title})
                except NoteNotFoundError:
                    continue
            return 200, "application/json", json.dumps({"results": results})

        if parsed.path == "/api/list":
            items = self._store.list()
            return 200, "application/json", json.dumps(
                {"items": [{"id": item.id, "title": item.title} for item in items]}
            )

        if parsed.path == "/api/settings":
            return 200, "application/json", json.dumps(
                {
                    "vault_dir": str(self._store.vault_root),
                    "index_db": str(self._index.db_path),
                    "note_count": len(self._store.list()),
                }
            )

        if parsed.path.startswith("/api/note/"):
            note_id = parsed.path[len("/api/note/") :]
            try:
                item = self._store.get(note_id)
            except NoteNotFoundError:
                return 404, "application/json", json.dumps({"error": "not found"})
            except InvalidNoteIdError as exc:
                return 400, "application/json", json.dumps({"error": str(exc)})
            frontmatter, body = item.to_frontmatter()
            return 200, "application/json", json.dumps({**frontmatter, "body": body})

        return 404, "application/json", json.dumps({"error": "not found"})

    def route_post(self, path: str, raw_body: bytes) -> tuple[int, str, str]:
        """Dispatch a POST ``path``+body, returning ``(status, content_type, body)``.

        Every write goes through :class:`secondmind.store.VaultStore`'s
        own ``put``/``supersede`` — the identical conflict-safety path the
        CLI and MCP adapter use, never a separate write implementation.
        """
        parsed = urlparse(path)

        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return 400, "application/json", json.dumps({"error": "invalid JSON body"})

        if parsed.path == "/api/put":
            try:
                knowledge_type = KnowledgeType.from_str(payload["type"])
            except (KeyError, ValueError) as exc:
                return 400, "application/json", json.dumps({"error": str(exc)})
            try:
                title = payload["title"]
                body = payload["body"]
            except KeyError as exc:
                return 400, "application/json", json.dumps({"error": f"missing field: {exc}"})

            try:
                result = self._store.put(
                    id=payload.get("id"),
                    type=knowledge_type,
                    title=title,
                    body=body,
                    scope=payload.get("scope", ""),
                    tags=payload.get("tags", []),
                    ttl_days=payload.get("ttl_days"),
                )
            except InvalidNoteIdError as exc:
                return 400, "application/json", json.dumps({"error": str(exc)})
            self._index.put(self._store.get(result.id))
            return 200, "application/json", json.dumps(
                {"id": result.id, "created": result.created, "updated": result.updated}
            )

        if parsed.path.startswith("/api/supersede/"):
            note_id = parsed.path[len("/api/supersede/") :]
            try:
                new_body = payload["body"]
            except KeyError as exc:
                return 400, "application/json", json.dumps({"error": f"missing field: {exc}"})
            try:
                item = self._store.supersede(note_id, new_body=new_body)
            except NoteNotFoundError:
                return 404, "application/json", json.dumps({"error": "not found"})
            except InvalidNoteIdError as exc:
                return 400, "application/json", json.dumps({"error": str(exc)})
            self._index.put(item)
            return 200, "application/json", json.dumps({"id": item.id, "updated": item.updated})

        return 404, "application/json", json.dumps({"error": "not found"})

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming convention
        self._store = self.server._store  # type: ignore[attr-defined]
        self._index = self.server._index  # type: ignore[attr-defined]
        status, content_type, body = self.route(self.path)
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming convention
        self._store = self.server._store  # type: ignore[attr-defined]
        self._index = self.server._index  # type: ignore[attr-defined]
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length else b""
        status, content_type, body = self.route_post(self.path, raw_body)
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # keep test/CI output clean — no per-request access log noise


class _Server(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], store: VaultStore, index: SqliteIndex) -> None:
        super().__init__(address, DashboardHandler)
        self._store = store
        self._index = index


def build_server(store: VaultStore, index: SqliteIndex, port: int = 8765) -> _Server:
    """Build (but do not start) the dashboard HTTP server, bound to 127.0.0.1 only."""
    return _Server(("127.0.0.1", port), store, index)
