"""Read-only web dashboard — stdlib http.server only, no Node/npm/build step.

Bounded-context responsibility: expose search/browse/view over HTTP for a
browser that can't run Obsidian or a CLI. Explicitly read-only in v1 (no
write/edit endpoints — a deliberate user decision, not a YAGNI inference,
verified by ``tests/test_dashboard.py``'s absence-of-do_POST check). Bound
to ``127.0.0.1`` only — never reachable from another machine on the LAN.
All SQLite access goes through parameterized queries via
:mod:`secondmind.sqlite_index` and :mod:`secondmind.store`, never raw SQL
built from request input.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from secondmind.sqlite_index import SqliteIndex
from secondmind.store import NoteNotFoundError, VaultStore

_STATIC_DIR = Path(__file__).resolve().parent
_STATIC_FILES = {
    "/": ("index.html", "text/html"),
    "/index.html": ("index.html", "text/html"),
    "/app.js": ("app.js", "application/javascript"),
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

        if parsed.path.startswith("/api/note/"):
            note_id = parsed.path[len("/api/note/") :]
            try:
                item = self._store.get(note_id)
            except NoteNotFoundError:
                return 404, "application/json", json.dumps({"error": "not found"})
            frontmatter, body = item.to_frontmatter()
            return 200, "application/json", json.dumps({**frontmatter, "body": body})

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
