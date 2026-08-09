"""Proves the secondmind core never imports from secondmind_mcp.

Traces to SPEC.md §6 and ARCHITECTURE.md's component isolation boundary:
the core must run with zero pip dependencies, so it must never import
anything from the MCP adapter (the one place the `mcp` package is used).
This test inspects the AST of every secondmind/*.py file directly — it
does not rely on `mcp` being absent from the test environment, so it runs
correctly whether or not the optional extra is installed. The CI job in
.github/workflows/ci.yml additionally runs the full core suite in a venv
with `mcp` NOT installed, which is the end-to-end proof this test's static
check is meant to guarantee.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parent.parent / "secondmind"


def _imported_top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


class TestCoreNeverImportsMcpAdapter(unittest.TestCase):
    def test_no_core_module_imports_secondmind_mcp(self) -> None:
        offending: list[str] = []
        for path in _CORE_DIR.glob("*.py"):
            names = _imported_top_level_names(path)
            if "secondmind_mcp" in names:
                offending.append(str(path))
        self.assertEqual(offending, [])

    def test_no_core_module_imports_the_mcp_package_directly(self) -> None:
        offending: list[str] = []
        for path in _CORE_DIR.glob("*.py"):
            names = _imported_top_level_names(path)
            if "mcp" in names:
                offending.append(str(path))
        self.assertEqual(offending, [])

    def test_no_core_module_imports_dashboard(self) -> None:
        offending: list[str] = []
        for path in _CORE_DIR.glob("*.py"):
            names = _imported_top_level_names(path)
            if "dashboard" in names:
                offending.append(str(path))
        self.assertEqual(offending, [])


if __name__ == "__main__":
    unittest.main()
