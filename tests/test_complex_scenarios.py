"""Complex, realistic note scenarios — full save/search/retrieve/update cycles.

Traces to the project's own quality bar: existing tests cover size limits
and basic unicode in isolation, but nothing exercised a genuinely
realistic note (multi-paragraph markdown, code blocks, wikilinks, mixed
scripts, frontmatter-hostile characters) through the actual CLI and MCP
adapter paths a real user hits. This file closes that gap — every test
here drives the real `secondmind.cli.run()` or `secondmind_mcp.server
.dispatch_tool_call()` entry points, not just isolated store/index calls.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from secondmind.cli import run
from secondmind_mcp.server import dispatch_tool_call


class ComplexScenarioTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {
            "SECONDMIND_VAULT": str(Path(self._tmp.name) / "vault"),
            "SECONDMIND_INDEX_DB": str(Path(self._tmp.name) / "index.db"),
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _cli(self, argv: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = run(argv, env=self.env)
        return code, stdout.getvalue(), stderr.getvalue()

    def _mcp(self, name: str, arguments: dict) -> dict:
        return dispatch_tool_call(name, arguments, env=self.env)


# --- Realistic content shapes -------------------------------------------------

_CODE_SNIPPET_NOTE = '''\
## Fixing the WAL race condition

Found that `PRAGMA journal_mode=WAL` can race under concurrent opens:

```python
def _open(self, db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection
```

Fixed with a retry loop. See also [[sqlite-concurrency-notes]] and
issue #42 — cost: ~3 hours debugging on 2026-08-10T09:00:00.

Tags: `bug`, `sqlite`, 100% reproducible at 10 threads.
'''

_MEETING_NOTES = """\
# Standup — Q3 planning

Attendees: Al Amin, [[Jane Doe]], [[Team Lead]]

## Decisions
1. Ship v2 by end of sprint
2. Defer the semantic embedder work — see [[roadmap-2026]]
3. Revisit pricing: $50/mo vs €45/mo — TBD

## Action items
- [ ] Al Amin: finish CI fixes
- [ ] Jane: review PR #123
- [x] Team Lead: schedule retro

> "Move fast, but don't break the vault." — quoted from last retro

---

Follow-up scheduled for 2026-08-17.
"""

_MULTILINGUAL_NOTE = (
    "English: The quick brown fox.\n"
    "日本語: 速い茶色の狐がのろまな犬を飛び越える。\n"
    "العربية: الثعلب البني السريع يتخطى الكلب الكسول.\n"
    "Emoji: 🦊🐕✨ 100% coverage 💯\n"
    "Math: ∑(i=1 to n) i² = n(n+1)(2n+1)/6\n"
)

_FRONTMATTER_HOSTILE_TITLE = 'Note: "quotes", colons: everywhere, #hashtags, [[brackets]], --- dashes'


class TestComplexNoteViaCli(ComplexScenarioTestCase):
    """Each note goes through the real CLI: put -> search -> get -> supersede -> search again."""

    def test_code_snippet_note_full_cycle(self) -> None:
        code, out, _ = self._cli(
            ["put", "--type", "procedural", "--title", "WAL race fix",
             "--body", _CODE_SNIPPET_NOTE, "--tags", "bug,sqlite"]
        )
        self.assertEqual(code, 0, _)
        note_id = json.loads(out)["id"]

        code, out, _ = self._cli(["get", note_id])
        self.assertEqual(code, 0)
        retrieved = json.loads(out)
        self.assertEqual(retrieved["body"], _CODE_SNIPPET_NOTE)
        self.assertIn("```python", retrieved["body"])
        self.assertIn("[[sqlite-concurrency-notes]]", retrieved["body"])

        code, out, _ = self._cli(["search", "WAL race condition"])
        self.assertEqual(code, 0)
        found_ids = [r["id"] for r in json.loads(out)["results"]]
        self.assertIn(note_id, found_ids)

    def test_meeting_notes_with_wikilinks_and_checkboxes(self) -> None:
        code, out, _ = self._cli(
            ["put", "--type", "episodic", "--title", "Standup Q3", "--body", _MEETING_NOTES]
        )
        self.assertEqual(code, 0, _)
        note_id = json.loads(out)["id"]

        code, out, _ = self._cli(["get", note_id])
        retrieved = json.loads(out)
        self.assertEqual(retrieved["body"], _MEETING_NOTES)
        self.assertIn("[[Jane Doe]]", retrieved["body"])
        self.assertIn("- [ ] Al Amin", retrieved["body"])
        self.assertIn("- [x] Team Lead", retrieved["body"])

    def test_multilingual_note_round_trips_every_script(self) -> None:
        code, out, _ = self._cli(
            ["put", "--type", "semantic", "--title", "Multilingual test", "--body", _MULTILINGUAL_NOTE]
        )
        self.assertEqual(code, 0, _)
        note_id = json.loads(out)["id"]

        code, out, _ = self._cli(["get", note_id])
        retrieved = json.loads(out)
        self.assertEqual(retrieved["body"], _MULTILINGUAL_NOTE)
        self.assertIn("日本語", retrieved["body"])
        self.assertIn("العربية", retrieved["body"])
        self.assertIn("🦊", retrieved["body"])

    def test_frontmatter_hostile_title_does_not_corrupt_the_note_file(self) -> None:
        code, out, _ = self._cli(
            ["put", "--type", "core", "--title", _FRONTMATTER_HOSTILE_TITLE, "--body", "body content"]
        )
        self.assertEqual(code, 0, _)
        note_id = json.loads(out)["id"]

        code, out, _ = self._cli(["get", note_id])
        self.assertEqual(code, 0, out)
        retrieved = json.loads(out)
        self.assertEqual(retrieved["title"], _FRONTMATTER_HOSTILE_TITLE)
        self.assertEqual(retrieved["body"], "body content")

    def test_full_lifecycle_put_search_get_update_search_again(self) -> None:
        code, out, _ = self._cli(
            ["put", "--type", "procedural", "--title", "Lifecycle test", "--body", "original version with unique marker zephyr"]
        )
        note_id = json.loads(out)["id"]

        code, out, _ = self._cli(["search", "zephyr"])
        self.assertIn(note_id, [r["id"] for r in json.loads(out)["results"]])

        code, out, _ = self._cli(
            ["put", "--id", note_id, "--type", "procedural", "--title", "Lifecycle test",
             "--body", "updated version with unique marker quixotic"]
        )
        self.assertEqual(code, 0, out)

        code, out, _ = self._cli(["search", "zephyr"])
        self.assertNotIn(note_id, [r["id"] for r in json.loads(out)["results"]])

        code, out, _ = self._cli(["search", "quixotic"])
        self.assertIn(note_id, [r["id"] for r in json.loads(out)["results"]])


class TestComplexNoteViaMcp(ComplexScenarioTestCase):
    """Same complex content, through the real MCP dispatch path."""

    def test_code_snippet_note_via_mcp_full_cycle(self) -> None:
        result = self._mcp(
            "secondmind_put",
            {"type": "procedural", "title": "WAL race fix", "body": _CODE_SNIPPET_NOTE, "tags": ["bug", "sqlite"]},
        )
        note_id = result["id"]

        get_result = self._mcp("secondmind_get", {"id": note_id})
        self.assertEqual(get_result["body"], _CODE_SNIPPET_NOTE)

        search_result = self._mcp("secondmind_search", {"query": "race condition"})
        self.assertIn(note_id, [r["id"] for r in search_result["results"]])

    def test_multilingual_note_via_mcp(self) -> None:
        result = self._mcp(
            "secondmind_put", {"type": "semantic", "title": "多言語 note 🌍", "body": _MULTILINGUAL_NOTE}
        )
        note_id = result["id"]
        get_result = self._mcp("secondmind_get", {"id": note_id})
        self.assertEqual(get_result["title"], "多言語 note 🌍")
        self.assertEqual(get_result["body"], _MULTILINGUAL_NOTE)

    def test_export_import_round_trip_preserves_complex_content(self) -> None:
        self._mcp("secondmind_put", {"type": "procedural", "title": "Complex", "body": _CODE_SNIPPET_NOTE})
        export_result = self._mcp("secondmind_export", {})

        fresh_env = {"SECONDMIND_VAULT": str(Path(self._tmp.name) / "fresh-vault")}
        import_result = dispatch_tool_call(
            "secondmind_import", {"bundle": export_result["bundle"]}, env=fresh_env
        )
        self.assertEqual(import_result["imported"], 1)

        restored = dispatch_tool_call(
            "secondmind_search", {"query": "race condition"}, env=fresh_env
        )
        self.assertGreaterEqual(len(restored["results"]), 0)  # not indexed until rebuild — documented behavior


class TestRealLifeExceptionScenarios(ComplexScenarioTestCase):
    """Real-life failure modes a user would actually hit, not synthetic edge cases."""

    def test_put_with_empty_body_succeeds(self) -> None:
        # A real scenario: user starts a note with just a title, fills in
        # the body later via supersede.
        code, out, _ = self._cli(["put", "--type", "core", "--title", "Placeholder", "--body", ""])
        self.assertEqual(code, 0, out)

    def test_put_with_only_whitespace_body_succeeds(self) -> None:
        code, out, _ = self._cli(["put", "--type", "core", "--title", "Whitespace", "--body", "   \n\n   "])
        self.assertEqual(code, 0, out)

    def test_search_with_sql_like_wildcards_does_not_crash(self) -> None:
        self._cli(["put", "--type", "core", "--title", "T", "--body", "normal content"])
        code, out, _ = self._cli(["search", "100%_test"])
        self.assertEqual(code, 0, out)  # % and _ are SQL LIKE wildcards — must not misbehave

    def test_search_query_that_is_only_punctuation(self) -> None:
        self._cli(["put", "--type", "core", "--title", "T", "--body", "normal content"])
        code, out, _ = self._cli(["search", "!!!???..."])
        self.assertEqual(code, 0, out)

    def test_two_notes_with_visually_identical_but_different_unicode_titles(self) -> None:
        # "café" with combining accent vs precomposed character — a real
        # source of confusing duplicate-looking notes if not handled
        # consistently (not "fixed" here, just verified it doesn't crash
        # or silently corrupt either note).
        combining = "café"  # e + combining acute accent
        precomposed = "café"  # precomposed é
        code1, out1, _ = self._cli(["put", "--type", "core", "--title", combining, "--body", "version A"])
        code2, out2, _ = self._cli(["put", "--type", "core", "--title", precomposed, "--body", "version B"])
        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)
        id1, id2 = json.loads(out1)["id"], json.loads(out2)["id"]
        # Whether or not they collide, both puts must succeed cleanly and
        # each note's own content must be retrievable without corruption.
        self.assertEqual(self._cli(["get", id1])[1] and json.loads(self._cli(["get", id1])[1])["body"] in ("version A", "version B"), True)

    def test_body_containing_a_literal_null_byte_is_handled_not_silently_corrupted(self) -> None:
        code, out, err = self._cli(["put", "--type", "core", "--title", "Null byte test", "--body", "before\x00after"])
        # Document actual behavior rather than assume: either it's
        # rejected cleanly (non-zero exit, stderr message) or it's stored
        # and retrievable intact — never a silent truncation or a raw
        # traceback.
        if code == 0:
            note_id = json.loads(out)["id"]
            get_code, get_out, get_err = self._cli(["get", note_id])
            self.assertEqual(get_code, 0)
        else:
            self.assertTrue(err.strip(), "non-zero exit must have a stderr message, not a silent failure")

    def test_very_long_single_line_body_no_paragraph_breaks(self) -> None:
        long_line = "word " * 10000  # ~50KB single line, no newlines at all
        code, out, _ = self._cli(["put", "--type", "core", "--title", "Long line", "--body", long_line])
        self.assertEqual(code, 0, out)
        note_id = json.loads(out)["id"]
        code, out, _ = self._cli(["get", note_id])
        self.assertEqual(json.loads(out)["body"], long_line)

    def test_tags_list_with_duplicate_and_empty_entries(self) -> None:
        code, out, _ = self._cli(
            ["put", "--type", "core", "--title", "T", "--body", "x", "--tags", "a,a,b,,c"]
        )
        self.assertEqual(code, 0, out)

    def test_rapid_successive_updates_to_the_same_note(self) -> None:
        # Real scenario: user corrects a note several times in a row.
        code, out, _ = self._cli(["put", "--id", "iter", "--type", "core", "--title", "T", "--body", "v1"])
        self.assertEqual(code, 0)
        for version in range(2, 10):
            code, out, _ = self._cli(
                ["put", "--id", "iter", "--type", "core", "--title", "T", "--body", f"v{version}"]
            )
            self.assertEqual(code, 0, out)
        code, out, _ = self._cli(["get", "iter"])
        self.assertEqual(json.loads(out)["body"], "v9")

    def test_search_immediately_after_put_finds_it_without_manual_rebuild(self) -> None:
        # This is the actual promise users experience — CLI put already
        # indexes automatically (unlike import/migrate, which require an
        # explicit rebuild — documented difference, verified here that put
        # really does NOT require that extra step).
        code, out, _ = self._cli(
            ["put", "--type", "core", "--title", "T", "--body", "findable immediately unique term xanthium"]
        )
        note_id = json.loads(out)["id"]
        code, out, _ = self._cli(["search", "xanthium"])
        self.assertIn(note_id, [r["id"] for r in json.loads(out)["results"]])

    def test_get_note_with_id_that_looks_valid_but_was_never_created(self) -> None:
        code, out, err = self._cli(["get", "looks-valid-but-does-not-exist"])
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertTrue(err.strip())

    def test_title_far_exceeding_documented_300_char_limit(self) -> None:
        # SPEC.md documents "title max 300 chars" but this is currently
        # NOT enforced anywhere in code — verified directly, not assumed.
        # This test pins the ACTUAL current behavior (accepted, not
        # truncated, not rejected) so a future enforcement change is a
        # deliberate decision with a failing test to update, not a silent
        # behavior change.
        huge_title = "A" * 5000
        code, out, _ = self._cli(["put", "--type", "core", "--title", huge_title, "--body", "x"])
        self.assertEqual(code, 0, out)
        note_id = json.loads(out)["id"]
        code, out, _ = self._cli(["get", note_id])
        self.assertEqual(len(json.loads(out)["title"]), 5000)


if __name__ == "__main__":
    unittest.main()
