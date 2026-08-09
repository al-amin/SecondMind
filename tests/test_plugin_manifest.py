"""Tests for the Agent Plugins 1.0.0 packaging manifests.

Traces to ARCHITECTURE.md's "Packaging: Agent Plugins 1.0.0" section. A
plugin is just a directory with fixed-location files; these tests validate
that plugin.json/mcp.json exist, parse, and have the shape the spec
requires — this is what makes "one manifest, portable across clients" a
verified claim rather than an assertion in docs.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TestPluginJson(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((_REPO_ROOT / "plugin.json").read_text(encoding="utf-8"))

    def test_has_schema_field(self) -> None:
        self.assertIn("$schema", self.manifest)
        self.assertIn("agent-plugins.org", self.manifest["$schema"])

    def test_has_name_field(self) -> None:
        self.assertEqual(self.manifest["name"], "secondmind")

    def test_does_not_relocate_or_inline_components(self) -> None:
        # Per the spec: plugin.json cannot declare components inline or
        # relocate them — it should only carry metadata fields, never a
        # "skills" or "mcp" key pointing somewhere else.
        self.assertNotIn("skills", self.manifest)
        self.assertNotIn("mcp", self.manifest)


class TestMcpJson(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((_REPO_ROOT / "mcp.json").read_text(encoding="utf-8"))

    def test_declares_the_secondmind_server(self) -> None:
        self.assertIn("secondmind", self.manifest.get("mcpServers", {}))

    def test_server_entry_has_explicit_stdio_type(self) -> None:
        entry = self.manifest["mcpServers"]["secondmind"]
        self.assertEqual(entry["type"], "stdio")

    def test_server_entry_has_command_and_args(self) -> None:
        entry = self.manifest["mcpServers"]["secondmind"]
        self.assertIn("command", entry)
        self.assertIn("args", entry)


class TestSkillFile(unittest.TestCase):
    def test_skill_md_exists_at_fixed_location(self) -> None:
        skill_path = _REPO_ROOT / "skills" / "secondmind" / "SKILL.md"
        self.assertTrue(skill_path.exists())

    def test_skill_md_is_nonempty(self) -> None:
        skill_path = _REPO_ROOT / "skills" / "secondmind" / "SKILL.md"
        self.assertTrue(skill_path.read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()
