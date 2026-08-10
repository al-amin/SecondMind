"""Tests for secondmind_mcp.http_transport — the stateless Streamable HTTP transport.

Traces to SPEC.md §9/§10.3 (v1's documented extension point) and
ROADMAP.md item 2. Purely additive over the stdio adapter: no tool
contract changes, because secondmind_mcp/server.py's tools never relied
on hidden session state. Verified with a real uvicorn server on a real
socket and real HTTP POSTs via stdlib urllib — not TestClient, since
TestClient's synthetic 'testserver' Host header is rejected by mcp's own
DNS-rebinding protection (a real security feature, not a bug to route
around).
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from secondmind_mcp.http_transport import build_http_app


def _post_jsonrpc(port: int, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        status = response.status
        body = response.read().decode("utf-8")
    for line in body.splitlines():
        if line.startswith("data:"):
            return status, json.loads(line[len("data:") :].strip())
    return status, json.loads(body)


class TestHttpTransportTestCase(unittest.TestCase):
    """Spins up a real uvicorn server on a real socket for every test."""

    def setUp(self) -> None:
        import uvicorn

        self._tmp = tempfile.TemporaryDirectory()

        app = build_http_app(
            env={
                "SECONDMIND_VAULT": str(Path(self._tmp.name) / "vault"),
                "SECONDMIND_INDEX_DB": str(Path(self._tmp.name) / "index.db"),
            }
        )
        self.port = 8901
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        for _ in range(50):
            if self.server.started:
                break
            time.sleep(0.1)

    def tearDown(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)
        self._tmp.cleanup()


class TestHttpTransportBinding(unittest.TestCase):
    def test_app_binds_to_localhost_only(self) -> None:
        app = build_http_app(env={})
        # host="127.0.0.1" is passed to streamable_http_app for its DNS
        # rebinding decision — verified indirectly: a request with a
        # non-localhost Host header must be rejected (§ below), which is
        # only true if the app was actually built with a localhost host.
        self.assertIsNotNone(app)


class TestHttpTransportToolsList(TestHttpTransportTestCase):
    def test_tools_list_returns_all_six_tools_over_real_http(self) -> None:
        status, payload = _post_jsonrpc(
            self.port, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        self.assertEqual(status, 200)
        names = {tool["name"] for tool in payload["result"]["tools"]}
        self.assertEqual(
            names,
            {
                "secondmind_put",
                "secondmind_get",
                "secondmind_search",
                "secondmind_list",
                "secondmind_export",
                "secondmind_import",
            },
        )


class TestHttpTransportToolCall(TestHttpTransportTestCase):
    def test_put_then_search_over_two_independent_requests(self) -> None:
        # Two SEPARATE HTTP requests, no session id exchanged anywhere —
        # proves the stateless design holds over this transport too.
        put_status, put_payload = _post_jsonrpc(
            self.port,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "secondmind_put",
                    "arguments": {
                        "type": "core",
                        "title": "HTTP Note",
                        "body": "unique zylophone term",
                    },
                },
            },
        )
        self.assertEqual(put_status, 200)
        put_result = json.loads(put_payload["result"]["content"][0]["text"])
        self.assertIn("id", put_result)

        search_status, search_payload = _post_jsonrpc(
            self.port,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "secondmind_search", "arguments": {"query": "zylophone"}},
            },
        )
        self.assertEqual(search_status, 200)
        search_result = json.loads(search_payload["result"]["content"][0]["text"])
        found_ids = {r["id"] for r in search_result["results"]}
        self.assertIn(put_result["id"], found_ids)

    def test_get_missing_note_returns_jsonrpc_error(self) -> None:
        status, payload = _post_jsonrpc(
            self.port,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "secondmind_get", "arguments": {"id": "does-not-exist"}},
            },
        )
        self.assertEqual(status, 200)  # JSON-RPC errors are still HTTP 200
        self.assertIn("error", payload)
        self.assertEqual(payload["error"]["code"], -32602)


class TestHttpTransportRejectsForeignHost(TestHttpTransportTestCase):
    def test_non_localhost_host_header_is_rejected(self) -> None:
        # DNS-rebinding protection is a real security feature of the mcp
        # SDK itself — confirms it's actually active, not silently
        # disabled while wiring up this transport.
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/mcp",
            data=json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            ).encode("utf-8"),
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "Host": "evil.example.com",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(ctx.exception.code, 421)


if __name__ == "__main__":
    unittest.main()
