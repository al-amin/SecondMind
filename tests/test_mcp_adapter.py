"""Tests for secondmind_mcp.server — the stateless MCP tool adapter.

Traces to SPEC.md §6. Every tool call resolves the vault/index path fresh
(no session object holds state between calls — verified by
test_no_state_persists_between_independent_calls). Not-found/bad-argument
errors use McpError with INVALID_PARAMS (-32602), the current standard
code. These tests call the adapter's dispatch function directly (in-process)
— scripts/live_probe.py separately proves the same behavior over a real
stdio subprocess.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mcp.shared.exceptions import McpError
from mcp.types import INVALID_PARAMS

from secondmind_mcp.server import TOOLS, dispatch_tool_call


class McpAdapterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {
            "SECONDMIND_VAULT": self._tmp.name,
            "SECONDMIND_INDEX_DB": str(Path(self._tmp.name) / "index.db"),
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _call(self, name: str, arguments: dict) -> dict:
        return dispatch_tool_call(name, arguments, env=self.env)


class TestToolRegistry(unittest.TestCase):
    def test_exposes_exactly_the_six_spec_tools(self) -> None:
        names = {tool.name for tool in TOOLS}
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

    def test_every_tool_has_a_json_schema_2020_12_input_schema(self) -> None:
        for tool in TOOLS:
            self.assertIn("$schema", tool.inputSchema)
            self.assertIn("2020-12", tool.inputSchema["$schema"])


class TestSecondmindPut(McpAdapterTestCase):
    def test_put_returns_id_created_updated(self) -> None:
        result = self._call(
            "secondmind_put",
            {"type": "core", "title": "My Note", "body": "Hello"},
        )
        self.assertIn("id", result)
        self.assertIn("created", result)
        self.assertIn("updated", result)

    def test_put_rejects_invalid_type_via_schema_enum(self) -> None:
        with self.assertRaises(McpError) as ctx:
            self._call("secondmind_put", {"type": "not-a-type", "title": "X", "body": "x"})
        self.assertEqual(ctx.exception.error.code, INVALID_PARAMS)


class TestSecondmindGet(McpAdapterTestCase):
    def test_get_existing_note(self) -> None:
        put_result = self._call("secondmind_put", {"type": "core", "title": "T", "body": "B"})
        result = self._call("secondmind_get", {"id": put_result["id"]})
        self.assertEqual(result["title"], "T")
        self.assertEqual(result["body"], "B")

    def test_get_missing_note_raises_invalid_params(self) -> None:
        with self.assertRaises(McpError) as ctx:
            self._call("secondmind_get", {"id": "does-not-exist"})
        self.assertEqual(ctx.exception.error.code, INVALID_PARAMS)


class TestSecondmindSearch(McpAdapterTestCase):
    def test_search_finds_matching_note_and_returns_cursor_field(self) -> None:
        self._call("secondmind_put", {"type": "core", "title": "T", "body": "unique zonkey term"})
        result = self._call("secondmind_search", {"query": "zonkey"})
        self.assertIn("results", result)
        self.assertIn("next_cursor", result)
        self.assertTrue(any(r["id"] for r in result["results"]))

    def test_search_accepts_explicit_cursor_without_server_side_session(self) -> None:
        # The explicit-handle pattern: cursor is just an argument, never
        # implicit server-side state tied to a session.
        result = self._call("secondmind_search", {"query": "anything", "cursor": None})
        self.assertIn("results", result)


class TestSecondmindList(McpAdapterTestCase):
    def test_list_returns_items_array(self) -> None:
        self._call("secondmind_put", {"type": "core", "title": "T", "body": "B"})
        result = self._call("secondmind_list", {})
        self.assertIn("items", result)
        self.assertEqual(len(result["items"]), 1)


class TestSecondmindExportImport(McpAdapterTestCase):
    def test_export_then_import_round_trips(self) -> None:
        self._call("secondmind_put", {"type": "core", "title": "T", "body": "content"})
        export_result = self._call("secondmind_export", {})
        self.assertIn("bundle", export_result)

        with tempfile.TemporaryDirectory() as fresh_vault:
            fresh_env = {"SECONDMIND_VAULT": fresh_vault}
            import_result = dispatch_tool_call(
                "secondmind_import", {"bundle": export_result["bundle"]}, env=fresh_env
            )
            self.assertEqual(import_result["imported"], 1)

    def test_import_dry_run_reports_without_writing(self) -> None:
        bundle = {
            "schema_version": 1,
            "count": 1,
            "items": [
                {
                    "id": "a",
                    "type": "core",
                    "title": "A",
                    "body": "x",
                    "created": "2026-08-09T00:00:00Z",
                    "updated": "2026-08-09T00:00:00Z",
                }
            ],
        }
        result = self._call("secondmind_import", {"bundle": bundle, "dry_run": True})
        self.assertEqual(result["imported"], 1)
        list_result = self._call("secondmind_list", {})
        self.assertEqual(list_result["items"], [])


class TestStatelessness(McpAdapterTestCase):
    def test_no_state_persists_between_independent_calls(self) -> None:
        """Each dispatch_tool_call resolves paths fresh from env — nothing
        is cached in a session object between calls, per SPEC.md §6."""
        self._call("secondmind_put", {"type": "core", "title": "First", "body": "x"})

        # A brand-new env pointing at a different vault must not see the
        # first vault's data — proves no shared hidden state leaked across
        # calls that would break isolation between "sessions."
        with tempfile.TemporaryDirectory() as other_vault:
            other_env = {"SECONDMIND_VAULT": other_vault}
            result = dispatch_tool_call("secondmind_list", {}, env=other_env)
            self.assertEqual(result["items"], [])

    def test_unknown_tool_name_raises_invalid_params(self) -> None:
        with self.assertRaises(McpError) as ctx:
            self._call("not_a_real_tool", {})
        self.assertEqual(ctx.exception.error.code, INVALID_PARAMS)


if __name__ == "__main__":
    unittest.main()
