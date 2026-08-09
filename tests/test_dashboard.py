"""Tests for dashboard.server — the read-only web dashboard.

Traces to SPEC.md/plan's dashboard scope: read-only (search/browse/view),
stdlib http.server only, bound to 127.0.0.1 only, parameterized SQLite
queries only. No write/edit endpoints in v1.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from secondmind.models import KnowledgeType
from secondmind.sqlite_index import SqliteIndex
from secondmind.store import VaultStore

from dashboard.server import DashboardHandler, build_server


class DashboardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.vault_root = Path(self._tmp.name) / "vault"
        self.db_path = Path(self._tmp.name) / "index.db"
        self.store = VaultStore(self.vault_root)
        self.index = SqliteIndex(self.db_path)

    def tearDown(self) -> None:
        self.index.close()
        self._tmp.cleanup()

    def _handle(self, path: str) -> tuple[int, dict | str]:
        """Call the handler's routing logic directly (in-process), without
        opening a real socket — the real socket binding is exercised
        separately by test_server_binds_to_localhost_only."""
        handler = DashboardHandler.__new__(DashboardHandler)
        handler._store = self.store
        handler._index = self.index
        status, content_type, body = handler.route(path)
        if content_type == "application/json":
            return status, json.loads(body)
        return status, body


class TestSearchEndpoint(DashboardTestCase):
    def test_search_finds_matching_note(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="unique zebra term")
        self.index.put(self.store.get("a"))
        status, payload = self._handle("/api/search?q=zebra")
        self.assertEqual(status, 200)
        self.assertIn("a", [r["id"] for r in payload["results"]])

    def test_search_with_no_query_returns_empty_results(self) -> None:
        status, payload = self._handle("/api/search")
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"], [])


class TestListEndpoint(DashboardTestCase):
    def test_list_returns_all_notes(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="x")
        self.store.put(id="b", type=KnowledgeType.SEMANTIC, title="B", body="x")
        status, payload = self._handle("/api/list")
        self.assertEqual(status, 200)
        ids = {item["id"] for item in payload["items"]}
        self.assertEqual(ids, {"a", "b"})


class TestNoteEndpoint(DashboardTestCase):
    def test_get_existing_note_returns_full_content(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="full content here")
        status, payload = self._handle("/api/note/a")
        self.assertEqual(status, 200)
        self.assertEqual(payload["body"], "full content here")

    def test_get_missing_note_returns_404(self) -> None:
        status, _ = self._handle("/api/note/does-not-exist")
        self.assertEqual(status, 404)


class TestUnknownRoute(DashboardTestCase):
    def test_unknown_api_path_returns_404(self) -> None:
        status, _ = self._handle("/api/not-a-real-endpoint")
        self.assertEqual(status, 404)


class TestNoWriteEndpoints(DashboardTestCase):
    def test_handler_has_no_put_or_delete_method(self) -> None:
        # Read-only by explicit design (v1 scope decision) — the handler
        # class must not define do_POST/do_PUT/do_DELETE at all.
        self.assertFalse(hasattr(DashboardHandler, "do_POST"))
        self.assertFalse(hasattr(DashboardHandler, "do_PUT"))
        self.assertFalse(hasattr(DashboardHandler, "do_DELETE"))


class TestServerBinding(unittest.TestCase):
    def test_server_binds_to_localhost_only_not_all_interfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp) / "vault")
            index = SqliteIndex(Path(tmp) / "index.db")
            try:
                server = build_server(store, index, port=0)
                try:
                    self.assertEqual(server.server_address[0], "127.0.0.1")
                finally:
                    server.server_close()
            finally:
                index.close()

    def test_real_http_request_against_a_running_server(self) -> None:
        """Live check, not just in-process routing: actually start the
        server on a real socket and issue a real HTTP GET, per the
        project's live-verification standard."""
        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp) / "vault")
            index = SqliteIndex(Path(tmp) / "index.db")
            store.put(id="live", type=KnowledgeType.CORE, title="Live Note", body="real http body")
            index.put(store.get("live"))
            try:
                server = build_server(store, index, port=0)
                port = server.server_address[1]
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    response = urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/note/live", timeout=5
                    )
                    payload = json.loads(response.read().decode("utf-8"))
                    response.close()
                    self.assertEqual(payload["body"], "real http body")

                    response = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
                    html = response.read().decode("utf-8")
                    response.close()
                    self.assertIn("SecondMind", html)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)
                    server.server_close()
            finally:
                index.close()


if __name__ == "__main__":
    unittest.main()
