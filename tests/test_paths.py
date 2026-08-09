"""Tests for secondmind.paths — vault/index location, id safety, atomic writes.

Traces to SPEC.md §1.3 (id constraints), §2 (storage guarantees: default
locations, atomicity) and the Exception & Edge Case Matrix "Security" row
(path traversal via note id must be blocked).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from secondmind.paths import (
    InvalidNoteIdError,
    atomic_write_text,
    default_index_db,
    default_vault_root,
    note_path,
    replace_with_windows_retry,
    validate_note_id,
)


class TestValidateNoteId(unittest.TestCase):
    def test_accepts_lowercase_alnum_and_hyphen(self) -> None:
        validate_note_id("my-note-123")  # must not raise

    def test_rejects_empty_id(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("")

    def test_rejects_none_id(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id(None)  # type: ignore[arg-type]

    def test_rejects_parent_directory_traversal(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("../../etc/passwd")

    def test_rejects_forward_slash(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("sub/dir")

    def test_rejects_backslash(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("sub\\dir")

    def test_rejects_absolute_unix_path(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("/etc/passwd")

    def test_rejects_absolute_windows_path(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("C:\\Windows\\System32")

    def test_rejects_uppercase(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("MyNote")

    def test_rejects_oversized_id(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("a" * 129)

    def test_accepts_max_length_id(self) -> None:
        validate_note_id("a" * 128)  # must not raise

    def test_rejects_id_with_null_byte(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("note\x00id")

    def test_rejects_dot_dot_alone(self) -> None:
        with self.assertRaises(InvalidNoteIdError):
            validate_note_id("..")


class TestNotePath(unittest.TestCase):
    def test_joins_vault_root_and_id_with_md_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_root = Path(tmp)
            path = note_path(vault_root, "my-note")
            self.assertEqual(path, vault_root / "my-note.md")

    def test_rejects_traversal_even_when_building_a_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_root = Path(tmp)
            with self.assertRaises(InvalidNoteIdError):
                note_path(vault_root, "../escape")

    def test_result_never_escapes_vault_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_root = Path(tmp)
            path = note_path(vault_root, "safe-id")
            self.assertTrue(str(path.resolve()).startswith(str(vault_root.resolve())))


class TestDefaultLocations(unittest.TestCase):
    def test_default_vault_root_is_under_home_when_no_env_override(self) -> None:
        env = {}
        root = default_vault_root(env=env)
        self.assertTrue(str(root).startswith(str(Path.home())))
        self.assertIn(".secondmind", str(root))

    def test_default_vault_root_honors_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {"SECONDMIND_VAULT": tmp}
            root = default_vault_root(env=env)
            self.assertEqual(root, Path(tmp))

    def test_default_index_db_is_under_home_when_no_env_override(self) -> None:
        env = {}
        db_path = default_index_db(env=env)
        self.assertTrue(str(db_path).startswith(str(Path.home())))

    def test_default_index_db_honors_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp) / "custom-index.db")
            env = {"SECONDMIND_INDEX_DB": target}
            db_path = default_index_db(env=env)
            self.assertEqual(db_path, Path(target))

    def test_no_hardcoded_personal_username_in_defaults(self) -> None:
        root = default_vault_root(env={})
        # The default must be derived from Path.home(), never a literal
        # personal path baked into the source.
        self.assertNotIn("al.amin1", str(root).replace(str(Path.home()), ""))


class TestAtomicWriteText(unittest.TestCase):
    def test_writes_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "note.md"
            atomic_write_text(target, "hello world")
            self.assertEqual(target.read_text(encoding="utf-8"), "hello world")

    def test_overwrites_existing_file_completely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "note.md"
            target.write_text("old content", encoding="utf-8")
            atomic_write_text(target, "new content")
            self.assertEqual(target.read_text(encoding="utf-8"), "new content")

    def test_leaves_no_temp_file_behind_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "note.md"
            atomic_write_text(target, "content")
            remaining = list(Path(tmp).iterdir())
            self.assertEqual(remaining, [target])

    def test_creates_parent_directory_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "dir" / "note.md"
            atomic_write_text(target, "content")
            self.assertEqual(target.read_text(encoding="utf-8"), "content")

    @unittest.skipIf(
        sys.platform == "win32",
        "os.chmod cannot express a read-only directory on Windows (ACL-based, not POSIX bits)",
    )
    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "root ignores directory permission bits — cannot express read-only via chmod",
    )
    def test_original_file_untouched_if_write_target_dir_is_readonly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "note.md"
            target.write_text("original", encoding="utf-8")
            os.chmod(tmp, 0o555)
            try:
                with self.assertRaises(OSError):
                    atomic_write_text(target, "new content")
                self.assertEqual(target.read_text(encoding="utf-8"), "original")
            finally:
                os.chmod(tmp, 0o755)


class TestReplaceWithWindowsRetry(unittest.TestCase):
    def test_succeeds_immediately_when_no_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.txt"
            dst = Path(tmp) / "dst.txt"
            src.write_text("content", encoding="utf-8")
            replace_with_windows_retry(src, dst)
            self.assertEqual(dst.read_text(encoding="utf-8"), "content")

    def test_retries_on_permission_error_then_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.txt"
            dst = Path(tmp) / "dst.txt"
            src.write_text("content", encoding="utf-8")

            call_count = {"n": 0}
            real_replace = os.replace

            def flaky_replace(a, b):
                call_count["n"] += 1
                if call_count["n"] < 3:
                    raise PermissionError("simulated transient Windows lock")
                return real_replace(a, b)

            with patch("secondmind.paths.os.replace", side_effect=flaky_replace):
                replace_with_windows_retry(src, dst)

            self.assertEqual(call_count["n"], 3)
            self.assertEqual(dst.read_text(encoding="utf-8"), "content")

    def test_raises_after_exhausting_all_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.txt"
            dst = Path(tmp) / "dst.txt"
            src.write_text("content", encoding="utf-8")

            with patch(
                "secondmind.paths.os.replace",
                side_effect=PermissionError("persistent lock"),
            ):
                with self.assertRaises(PermissionError):
                    replace_with_windows_retry(src, dst)


if __name__ == "__main__":
    unittest.main()
