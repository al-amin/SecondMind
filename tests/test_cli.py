"""Tests for secondmind.cli — the python3 -m secondmind entry point.

Traces to SPEC.md §4 (CLI contract). Every command prints JSON to stdout on
success, a one-line message to stderr and non-zero exit on error — never a
raw traceback for an expected error condition.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from secondmind.cli import run


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {"SECONDMIND_VAULT": self._tmp.name}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = run(argv, env=self.env)
        return exit_code, stdout.getvalue(), stderr.getvalue()


class TestPut(CliTestCase):
    def test_put_creates_a_note_and_prints_json_with_id(self) -> None:
        code, out, _ = self._run(
            ["put", "--type", "core", "--title", "My Note", "--body", "Hello"]
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("id", payload)

    def test_put_with_explicit_id_uses_it(self) -> None:
        code, out, _ = self._run(
            ["put", "--id", "explicit", "--type", "core", "--title", "T", "--body", "B"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["id"], "explicit")

    def test_put_rejects_invalid_type(self) -> None:
        code, _, err = self._run(
            ["put", "--type", "not-a-type", "--title", "T", "--body", "B"]
        )
        self.assertNotEqual(code, 0)
        self.assertTrue(err.strip())


class TestGet(CliTestCase):
    def test_get_existing_note_prints_json(self) -> None:
        self._run(["put", "--id", "n1", "--type", "core", "--title", "N1", "--body", "Body1"])
        code, out, _ = self._run(["get", "n1"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["id"], "n1")
        self.assertEqual(payload["body"], "Body1")

    def test_get_missing_note_exits_nonzero_with_stderr_message(self) -> None:
        code, out, err = self._run(["get", "does-not-exist"])
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertTrue(err.strip())


class TestList(CliTestCase):
    def test_list_on_empty_vault_prints_empty_json_array(self) -> None:
        code, out, _ = self._run(["list"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

    def test_list_after_put_includes_the_note(self) -> None:
        self._run(["put", "--id", "n1", "--type", "core", "--title", "N1", "--body", "B"])
        code, out, _ = self._run(["list"])
        self.assertEqual(code, 0)
        ids = [item["id"] for item in json.loads(out)]
        self.assertEqual(ids, ["n1"])

    def test_list_filters_by_type(self) -> None:
        self._run(["put", "--id", "a", "--type", "core", "--title", "A", "--body", "x"])
        self._run(["put", "--id", "b", "--type", "semantic", "--title", "B", "--body", "x"])
        code, out, _ = self._run(["list", "--type", "core"])
        self.assertEqual(code, 0)
        ids = [item["id"] for item in json.loads(out)]
        self.assertEqual(ids, ["a"])


class TestSearch(CliTestCase):
    def test_search_finds_matching_note(self) -> None:
        self._run(
            ["put", "--id", "n1", "--type", "core", "--title", "T", "--body", "unique zyzzyva term"]
        )
        code, out, _ = self._run(["search", "zyzzyva"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("n1", [r["id"] for r in payload["results"]])
        self.assertIn("next_cursor", payload)

    def test_search_on_empty_vault_returns_empty_results(self) -> None:
        code, out, _ = self._run(["search", "anything"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["results"], [])


class TestExportImport(CliTestCase):
    def test_export_then_import_into_fresh_vault_round_trips(self) -> None:
        self._run(["put", "--id", "n1", "--type", "core", "--title", "T", "--body", "content"])
        with tempfile.TemporaryDirectory() as export_dir:
            bundle_path = str(Path(export_dir) / "bundle.json")
            code, _, _ = self._run(["export", "--output", bundle_path])
            self.assertEqual(code, 0)
            self.assertTrue(Path(bundle_path).exists())

            with tempfile.TemporaryDirectory() as fresh_vault:
                fresh_env = {"SECONDMIND_VAULT": fresh_vault}
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = run(["import", bundle_path], env=fresh_env)
                self.assertEqual(code, 0)

                stdout2 = io.StringIO()
                with contextlib.redirect_stdout(stdout2):
                    run(["get", "n1"], env=fresh_env)
                self.assertIn("content", stdout2.getvalue())


class TestRebuild(CliTestCase):
    def test_rebuild_exits_zero_on_empty_vault(self) -> None:
        code, _, _ = self._run(["rebuild"])
        self.assertEqual(code, 0)


class TestPrune(CliTestCase):
    def test_prune_on_empty_vault_reports_zero_pruned(self) -> None:
        code, out, _ = self._run(["prune"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["pruned"], [])

    def test_prune_deletes_expired_note(self) -> None:
        self._run(
            ["put", "--id", "n1", "--type", "core", "--title", "N1", "--body", "x", "--ttl-days", "1"]
        )
        note_path = Path(self._tmp.name) / "n1.md"
        content = note_path.read_text(encoding="utf-8")
        import re

        content = re.sub(r"updated: [^\n]+", "updated: 2020-01-01T00:00:00Z", content)
        note_path.write_text(content, encoding="utf-8")

        code, out, _ = self._run(["prune"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["pruned"], ["n1"])

    def test_prune_dry_run_flag(self) -> None:
        code, out, _ = self._run(["prune", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["pruned"], [])


class TestMigrate(CliTestCase):
    def test_migrate_imports_notes_from_an_external_vault(self) -> None:
        with tempfile.TemporaryDirectory() as external_dir:
            (Path(external_dir) / "note.md").write_text(
                "---\ntype: core\ntitle: External\ncreated: 2026-01-01T00:00:00Z\n"
                "updated: 2026-01-01T00:00:00Z\n---\nexternal content\n",
                encoding="utf-8",
            )
            code, out, _ = self._run(["migrate", external_dir])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["imported"], 1)

    def test_migrate_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as external_dir:
            (Path(external_dir) / "note.md").write_text(
                "---\ntype: core\ntitle: External\ncreated: 2026-01-01T00:00:00Z\n"
                "updated: 2026-01-01T00:00:00Z\n---\nx\n",
                encoding="utf-8",
            )
            code, out, _ = self._run(["migrate", external_dir, "--dry-run"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["imported"], 1)
            list_code, list_out, _ = self._run(["list"])
            self.assertEqual(json.loads(list_out), [])

    def test_migrate_on_empty_external_vault_imports_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as external_dir:
            code, out, _ = self._run(["migrate", external_dir])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["imported"], 0)


class TestUnknownCommand(CliTestCase):
    def test_unknown_command_exits_nonzero_with_stderr_message(self) -> None:
        code, out, err = self._run(["not-a-real-command"])
        self.assertNotEqual(code, 0)
        self.assertTrue(err.strip())


if __name__ == "__main__":
    unittest.main()
