"""Tests for dashboard.server — the SecondMind web dashboard.

Traces to SPEC.md/plan's dashboard scope: search/browse/view (v1) plus
put/supersede (v2, ROADMAP.md item 8) — stdlib http.server only, bound to
127.0.0.1 only, parameterized SQLite queries only. Write endpoints go
through the same VaultStore.put/supersede conflict-safety guarantees the
CLI and MCP adapter already use — no separate write path with weaker
guarantees.
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

    def _handle_post(self, path: str, payload: dict) -> tuple[int, dict | str]:
        handler = DashboardHandler.__new__(DashboardHandler)
        handler._store = self.store
        handler._index = self.index
        status, content_type, body = handler.route_post(path, json.dumps(payload).encode("utf-8"))
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

    def test_get_note_with_path_traversal_id_returns_400_not_a_crash(self) -> None:
        # Real bug: store.get() raises InvalidNoteIdError (a ValueError
        # subclass, not NoteNotFoundError) for a malformed id, which the
        # route() handler didn't catch — the request thread crashed with
        # an unhandled exception and the client got a dropped connection
        # with no HTTP response at all, confirmed against a real socket.
        # This is exactly the "path traversal via note id" row of the
        # project's own Exception & Edge Case Matrix.
        status, payload = self._handle("/api/note/../../etc/passwd")
        self.assertEqual(status, 400)
        self.assertIn("error", payload)


class TestUnknownRoute(DashboardTestCase):
    def test_unknown_api_path_returns_404(self) -> None:
        status, _ = self._handle("/api/not-a-real-endpoint")
        self.assertEqual(status, 404)


class TestPutEndpoint(DashboardTestCase):
    def test_put_creates_a_note_and_indexes_it(self) -> None:
        status, payload = self._handle_post(
            "/api/put", {"type": "core", "title": "Dashboard Note", "body": "unique walrus term"}
        )
        self.assertEqual(status, 200)
        self.assertIn("id", payload)
        # The dashboard must index what it writes, exactly like the CLI's
        # put command does — otherwise a dashboard-created note would be
        # invisible to /api/search until an external rebuild.
        search_status, search_payload = self._handle("/api/search?q=walrus")
        self.assertEqual(search_status, 200)
        self.assertIn(payload["id"], [r["id"] for r in search_payload["results"]])

    def test_put_with_explicit_id_updates_in_place(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="original")
        status, payload = self._handle_post(
            "/api/put", {"id": "a", "type": "core", "title": "A", "body": "updated"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["id"], "a")
        self.assertEqual(self.store.get("a").body, "updated")

    def test_put_rejects_invalid_type(self) -> None:
        status, payload = self._handle_post(
            "/api/put", {"type": "not-a-type", "title": "X", "body": "x"}
        )
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_put_rejects_missing_required_field(self) -> None:
        status, payload = self._handle_post("/api/put", {"type": "core", "title": "X"})
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_put_with_path_traversal_explicit_id_returns_400_not_a_crash(self) -> None:
        status, payload = self._handle_post(
            "/api/put", {"id": "../../etc/passwd", "type": "core", "title": "X", "body": "x"}
        )
        self.assertEqual(status, 400)
        self.assertIn("error", payload)


class TestSupersedeEndpoint(DashboardTestCase):
    def test_supersede_replaces_body_reusing_the_same_id(self) -> None:
        self.store.put(id="a", type=KnowledgeType.CORE, title="A", body="v1")
        status, payload = self._handle_post("/api/supersede/a", {"body": "v2"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["id"], "a")
        self.assertEqual(self.store.get("a").body, "v2")

    def test_supersede_missing_note_returns_404(self) -> None:
        status, payload = self._handle_post("/api/supersede/does-not-exist", {"body": "x"})
        self.assertEqual(status, 404)
        self.assertIn("error", payload)

    def test_supersede_with_path_traversal_id_returns_400_not_a_crash(self) -> None:
        status, payload = self._handle_post("/api/supersede/../../etc/passwd", {"body": "x"})
        self.assertEqual(status, 400)
        self.assertIn("error", payload)


class TestOnlyIntendedWriteEndpointsExist(DashboardTestCase):
    def test_unknown_post_path_returns_404(self) -> None:
        status, payload = self._handle_post("/api/not-a-real-write-endpoint", {})
        self.assertEqual(status, 404)


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

    def test_real_http_post_against_a_running_server(self) -> None:
        """Live check for the write path: a real socket, real HTTP POST,
        via stdlib urllib — matching the existing GET live-check pattern."""
        import json as _json
        import urllib.error

        with tempfile.TemporaryDirectory() as tmp:
            store = VaultStore(Path(tmp) / "vault")
            index = SqliteIndex(Path(tmp) / "index.db")
            try:
                server = build_server(store, index, port=0)
                port = server.server_address[1]
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    body = _json.dumps(
                        {"type": "core", "title": "Live POST", "body": "real http write"}
                    ).encode("utf-8")
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/put",
                        data=body,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    response = urllib.request.urlopen(request, timeout=5)
                    payload = json.loads(response.read().decode("utf-8"))
                    response.close()
                    self.assertIn("id", payload)
                    self.assertEqual(store.get(payload["id"]).body, "real http write")

                    bad_request = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/put",
                        data=_json.dumps({"type": "not-a-type"}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with self.assertRaises(urllib.error.HTTPError) as ctx:
                        urllib.request.urlopen(bad_request, timeout=5)
                    self.assertEqual(ctx.exception.code, 400)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)
                    server.server_close()
            finally:
                index.close()


if __name__ == "__main__":
    unittest.main()
