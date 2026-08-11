"""Tests for scripts/diagnose.py — the self-diagnosis entry point.

diagnose.py deliberately has zero dependency on secondmind/secondmind_mcp
(it must run even when the venv/deps are the thing that's broken), so these
tests import it directly by path rather than as a package. Real
filesystem/subprocess checks are used where practical (no PII/user data
involved) rather than mocking every boundary, matching this project's own
preference for live checks over heavy mocking for this class of tool.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location("diagnose", _SCRIPTS_DIR / "diagnose.py")
diagnose = importlib.util.module_from_spec(_spec)
sys.modules["diagnose"] = diagnose
_spec.loader.exec_module(diagnose)


class TestCheckClaudeDesktopConfig(unittest.TestCase):
    def setUp(self) -> None:
        diagnose._RESULTS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_config_path = diagnose._claude_desktop_config_path
        self._orig_log_dir = diagnose._claude_desktop_log_dir
        diagnose._claude_desktop_log_dir = lambda: Path(self._tmp.name) / "no-such-log-dir"

    def tearDown(self) -> None:
        diagnose._claude_desktop_config_path = self._orig_config_path
        diagnose._claude_desktop_log_dir = self._orig_log_dir
        self._tmp.cleanup()

    def test_missing_config_file_is_a_warning_not_a_failure(self) -> None:
        missing = Path(self._tmp.name) / "does-not-exist.json"
        diagnose._claude_desktop_config_path = lambda: missing
        diagnose.check_claude_desktop()
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["Claude Desktop config found"], "WARN")

    def test_malformed_json_is_a_failure(self) -> None:
        bad_config = Path(self._tmp.name) / "claude_desktop_config.json"
        bad_config.write_text("{not valid json", encoding="utf-8")
        diagnose._claude_desktop_config_path = lambda: bad_config
        diagnose.check_claude_desktop()
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["Claude Desktop config valid"], "FAIL")

    def test_config_with_secondmind_entry_passes(self) -> None:
        good_config = Path(self._tmp.name) / "claude_desktop_config.json"
        good_config.write_text(
            json.dumps({"mcpServers": {"secondmind": {"command": "uv"}}}), encoding="utf-8"
        )
        diagnose._claude_desktop_config_path = lambda: good_config
        diagnose.check_claude_desktop()
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["Claude Desktop config valid"], "PASS")

    def test_config_without_secondmind_entry_is_a_warning(self) -> None:
        other_config = Path(self._tmp.name) / "claude_desktop_config.json"
        other_config.write_text(
            json.dumps({"mcpServers": {"some-other-server": {"command": "x"}}}), encoding="utf-8"
        )
        diagnose._claude_desktop_config_path = lambda: other_config
        diagnose.check_claude_desktop()
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["secondmind registered in Claude Desktop config"], "WARN")


class TestCheckInstalledExtensionFreshness(unittest.TestCase):
    """Claude Desktop copies claude-desktop-extension/ into its own private
    storage at install time -- a `git pull` in the repo does nothing to
    that copy. Real bug this guards against: a copy installed before the
    SECONDMIND_REPO_DIR fix has no reference to it and fails with
    "ModuleNotFoundError: No module named 'secondmind_mcp'" (confirmed on
    a real user's Windows machine and reproduced independently on macOS)."""

    def setUp(self) -> None:
        diagnose._RESULTS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_config_path = diagnose._claude_desktop_config_path
        self._orig_log_dir = diagnose._claude_desktop_log_dir
        self._orig_extensions_dir = diagnose._claude_desktop_extensions_dir
        diagnose._claude_desktop_config_path = lambda: Path(self._tmp.name) / "no-config.json"
        diagnose._claude_desktop_log_dir = lambda: Path(self._tmp.name) / "no-such-log-dir"

    def tearDown(self) -> None:
        diagnose._claude_desktop_config_path = self._orig_config_path
        diagnose._claude_desktop_log_dir = self._orig_log_dir
        diagnose._claude_desktop_extensions_dir = self._orig_extensions_dir
        self._tmp.cleanup()

    def _make_installed_copy(self, launcher_name: str, launcher_content: str) -> Path:
        extensions_dir = Path(self._tmp.name) / "extensions"
        installed = extensions_dir / "local.unpacked.al-amin.secondmind"
        installed.mkdir(parents=True)
        (installed / launcher_name).write_text(launcher_content, encoding="utf-8")
        diagnose._claude_desktop_extensions_dir = lambda: extensions_dir
        return installed

    def test_up_to_date_launcher_referencing_repo_dir_passes(self) -> None:
        launcher_name = "run.bat" if platform.system() == "Windows" else "run.sh"
        self._make_installed_copy(launcher_name, "echo %SECONDMIND_REPO_DIR%")
        diagnose.check_claude_desktop()
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["Installed extension is up to date"], "PASS")

    def test_stale_launcher_without_repo_dir_reference_fails(self) -> None:
        launcher_name = "run.bat" if platform.system() == "Windows" else "run.sh"
        self._make_installed_copy(launcher_name, "exec uv run --directory \"$REPO_ROOT\" -m secondmind_mcp.server")
        diagnose.check_claude_desktop()
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["Installed extension is up to date"], "FAIL")


class TestCheckClaudeDesktopLog(unittest.TestCase):
    def setUp(self) -> None:
        diagnose._RESULTS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_config_path = diagnose._claude_desktop_config_path
        self._orig_log_dir = diagnose._claude_desktop_log_dir
        diagnose._claude_desktop_config_path = lambda: Path(self._tmp.name) / "no-config.json"

    def tearDown(self) -> None:
        diagnose._claude_desktop_config_path = self._orig_config_path
        diagnose._claude_desktop_log_dir = self._orig_log_dir
        self._tmp.cleanup()

    def test_log_with_no_error_signals_passes(self) -> None:
        log_dir = Path(self._tmp.name)
        (log_dir / "mcp-server-SecondMind.log").write_text(
            "2026-08-10T00:00:00Z [SecondMind] [info] Server started and connected successfully\n",
            encoding="utf-8",
        )
        diagnose._claude_desktop_log_dir = lambda: log_dir
        diagnose.check_claude_desktop()
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["SecondMind MCP server log — no recent errors"], "PASS")

    def test_log_with_windows_sh_not_recognized_error_fails(self) -> None:
        # Real bug this session found and fixed: cmd.exe cannot execute a
        # .sh file directly. Pinning the exact error text as a regression
        # guard, not a contrived string.
        log_dir = Path(self._tmp.name)
        (log_dir / "mcp-server-SecondMind.log").write_text(
            "2026-08-10T00:00:00Z [SecondMind] [info] Starting\n"
            "'sh' is not recognized as an internal or external command,\n"
            "operable program or batch file.\n"
            "2026-08-10T00:00:01Z [SecondMind] [error] Server disconnected.\n",
            encoding="utf-8",
        )
        diagnose._claude_desktop_log_dir = lambda: log_dir
        diagnose.check_claude_desktop()
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["SecondMind MCP server log — recent errors found"], "FAIL")

    def test_log_error_report_never_includes_full_line_content_beyond_the_error_signal(self) -> None:
        # Privacy guard: a "Message from client/server" log line can
        # contain a note's real title/body verbatim. The error-line report
        # must never echo an unrelated line that happens to sit near a real
        # error, only lines that themselves match a known error signal.
        log_dir = Path(self._tmp.name)
        (log_dir / "mcp-server-SecondMind.log").write_text(
            '2026-08-10T00:00:00Z [SecondMind] [info] Message from client: '
            '{"method":"tools/call","params":{"name":"secondmind_put",'
            '"arguments":{"title":"my secret plan","body":"do not leak this"}}}\n'
            "2026-08-10T00:00:01Z [SecondMind] [error] Server disconnected.\n",
            encoding="utf-8",
        )
        diagnose._claude_desktop_log_dir = lambda: log_dir
        diagnose.check_claude_desktop()
        detail = next(
            detail
            for status, check, detail in diagnose._RESULTS
            if check == "SecondMind MCP server log — recent errors found"
        )
        self.assertNotIn("my secret plan", detail)
        self.assertNotIn("do not leak this", detail)
        self.assertIn("[error] Server disconnected.", detail)

    def test_missing_log_file_is_a_warning(self) -> None:
        diagnose._claude_desktop_log_dir = lambda: Path(self._tmp.name) / "no-such-dir"
        diagnose.check_claude_desktop()
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["SecondMind MCP server log found"], "WARN")


class TestCheckUv(unittest.TestCase):
    def setUp(self) -> None:
        diagnose._RESULTS.clear()

    def test_uv_not_found_anywhere_is_a_failure(self) -> None:
        import shutil

        orig_which = shutil.which
        orig_exists = Path.exists
        shutil.which = lambda name: None
        Path.exists = lambda self: False
        try:
            result = diagnose.check_uv()
        finally:
            shutil.which = orig_which
            Path.exists = orig_exists
        self.assertIsNone(result)
        statuses = {check: status for status, check, _ in diagnose._RESULTS}
        self.assertEqual(statuses["uv installed"], "FAIL")


class TestPathResolutionMatchesSecondmindPaths(unittest.TestCase):
    """diagnose.py re-implements path resolution instead of importing
    secondmind.paths (it must run even if secondmind/ itself is broken) —
    these tests pin that the two independent implementations agree."""

    def test_default_vault_root_matches_secondmind_paths(self) -> None:
        from secondmind.paths import default_vault_root

        with unittest.mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("SECONDMIND_VAULT", None)
            self.assertEqual(diagnose._default_vault_root(), default_vault_root())

    def test_default_vault_root_respects_env_override(self) -> None:
        from secondmind.paths import default_vault_root

        with unittest.mock.patch.dict("os.environ", {"SECONDMIND_VAULT": "/tmp/custom-vault"}):
            self.assertEqual(diagnose._default_vault_root(), default_vault_root())
            self.assertEqual(diagnose._default_vault_root(), Path("/tmp/custom-vault"))


if __name__ == "__main__":
    unittest.main()
