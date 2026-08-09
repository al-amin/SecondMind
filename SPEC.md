# SecondMind — Specification

**Status:** Draft v1. This document is the contract every later phase's tests trace back to.
If a test doesn't map to a clause here, either this spec is incomplete or the test is scope
creep — fix the spec, don't let the test drift.

**What SecondMind is:** a portable, cross-session memory layer for AI assistants. You tell it
something once; any AI client (Claude Desktop, Claude Code, and — as they adopt the same open
standards — Codex, Gemini, Cursor, etc.) can recall it later, on any machine, with nothing to
install beyond a stock Python interpreter.

**What SecondMind is not (v1):** a RAG-over-external-sources system, a multi-user server, a
note-taking app with a rich editor, a vector database service.

---

## 1. Data model

### 1.1 Note

A **note** is one Markdown file with YAML-subset frontmatter, stored in the vault. Frontmatter
fields (chosen to match the existing AUPS CKL / second-brain-skill shape for future
zero-translation interop — see §7):

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | `[a-z0-9-]+`, max 128 chars. Filename stem. Never contains `..`, `/`, `\`. |
| `type` | string | yes | One of: `core`, `semantic`, `episodic`, `procedural` (see §1.2). |
| `title` | string | yes | Free text, max 300 chars. |
| `scope` | string | no | Free text namespace hint (e.g. project name). Default `""`. |
| `entities` | list[string] | no | Named entities mentioned in the note. Default `[]`. |
| `tags` | list[string] | no | Free-text tags. Default `[]`. |
| `source` | string | no | Where this note came from (e.g. `manual`, `import:<bundle>`). Default `"manual"`. |
| `created` | string (ISO 8601) | yes | Set once, never changed. |
| `updated` | string (ISO 8601) | yes | Set on every write. |
| `ttl_days` | int | no | If set, note is eligible for pruning `ttl_days` after `updated`. Default `null` (never expires). |
| `supersedes` | string (note id) | no | If set, this note is a revision of an earlier note with that id. |

Body: everything after the frontmatter's closing `---`, plain Markdown, may contain
`[[wikilinks]]` (Obsidian-compatible, but SecondMind itself never parses or requires them).

### 1.2 Knowledge types (CoALA-inspired, kept minimal for v1)

- `core` — durable facts about the user/project that rarely change.
- `semantic` — general knowledge, lessons, how-things-work notes.
- `episodic` — dated events, session summaries, "what happened."
- `procedural` — how-to steps, runbooks, reusable procedures.

### 1.3 Identity and uniqueness

- `id` is globally unique within a vault. Filename is always `{id}.md`.
- If no `id` is supplied on `put`, one is generated: lowercase slug of `title` +
  short content-hash suffix, guaranteed unique against existing files in the vault.
- `supersede(old_id, new_content)` MUST reuse `old_id` as the resulting note's `id` — never
  mint a new id for a supersede. (This is a named regression test — see §5, historical bug
  class: a prior system minted a new id on supersede, causing duplicate notes.)

---

## 2. Storage guarantees

- **Vault = source of truth.** Plain Markdown files under a vault root directory. Nothing else
  is authoritative.
- **SQLite index = disposable cache.** Rebuildable 100% from the vault at any time. The index
  is never the only place a fact lives.
- **Atomicity.** Every note write: write to a temp file in the same directory, then
  `os.replace()` (atomic rename) onto the final path. A crash mid-write leaves either the old
  version or nothing new — never a truncated file. On Windows, the file handle is closed before
  `os.replace()` is called (POSIX allows replacing an open file; Windows does not).
- **Index rebuild.** Rebuild writes to a temp SQLite file, then atomically swaps it onto the
  live index path. A concurrent reader never sees an empty or half-populated index during a
  rebuild.
- **Concurrency.** SQLite opened with `PRAGMA journal_mode=WAL` and a `busy_timeout` set on
  every connection, so the CLI, MCP server, and dashboard can all read concurrently, and a
  writer never crashes a concurrent reader with "database is locked."
- **Default locations** (no hardcoded personal paths):
  - Vault: `Path.home() / ".secondmind" / "vault"` unless overridden by `SECONDMIND_VAULT` env
    var or `--vault` CLI flag.
  - Index: `Path.home() / ".secondmind" / "index.db"` unless overridden by
    `SECONDMIND_INDEX_DB` env var.
  - Both directories auto-created on first use if missing.

---

## 3. Search contract

- **Hybrid**: BM25 lexical (via SQLite FTS5) + cosine similarity over a stdlib hashing
  embedder, fused with Reciprocal Rank Fusion (RRF).
- **Complexity**: FTS5 lookup is O(log n + k) (B-tree seek + k matching postings), not a
  linear scan. Hashing embedder is O(1) amortized per token. RRF fusion over top-k from each
  side is O(k log k). No full-table scan on the search hot path.
- **Fallback**: if the Python build's SQLite lacks FTS5 (rare, but possible on some
  distributions), search falls back to a linear substring scan with a logged warning — never a
  crash.
- **Pagination**: `search(query, limit, cursor=None) -> (results, next_cursor)`. `cursor` is an
  explicit opaque string the caller threads back on the next call — no server-side session
  state (see §6, stateless MCP contract).

---

## 4. CLI contract

`python3 -m secondmind <command> [args]` — zero required pip installs.

| Command | Args | Behavior |
|---|---|---|
| `put` | `--id`, `--type`, `--title`, `--body` (or stdin), `--tags`, `--scope`, `--ttl-days` | Create or update a note. Runs conflict classification (§5) before writing. |
| `get` | `id` | Print one note (frontmatter + body) as JSON. Exit code 1 + stderr message if not found. |
| `list` | `--type`, `--tag` (optional filters) | Print matching note ids + titles as JSON. |
| `search` | `query`, `--limit`, `--cursor` | Print ranked results as JSON: `{results: [...], next_cursor: str|null}`. |
| `export` | `--output <path>` | Write a schema-versioned bundle (§7) of the whole vault. |
| `import` | `<path>`, `--dry-run` | Import a bundle. Idempotent — importing twice never duplicates. |
| `rebuild` | — | Force a full index rebuild from the vault. |

Every command: on error, prints a one-line human-readable message to stderr and exits non-zero.
Never a raw traceback for expected error conditions (missing id, bad args, vault unreadable).

---

## 5. Conflict-safe writes

Every `put`/`import` write is classified before touching disk:

- **identical** — new content hashes the same as existing note with that id → no-op, `updated`
  timestamp unchanged.
- **nonmaterial** — only whitespace/frontmatter-ordering differs → write allowed, no conflict
  flagged.
- **material** — body or a semantically meaningful field actually changed → write allowed,
  `updated` timestamp bumped, previous content preserved implicitly via git history of the
  vault (SecondMind does not itself version notes beyond `supersedes`).

This exists specifically to prevent the historical bug class of `supersede()` minting a new id
instead of updating in place, which caused duplicate notes in a prior system. §1.3's rule
("supersede reuses the prior id") is the fix; conflict classification is what makes the fix
observable and testable.

---

## 6. MCP tool contracts (stateless, per MCP spec 2026-07-28)

Transport: stdio only in v1. No `initialize`/`Mcp-Session-Id` session state — every tool call
is self-contained; nothing is cached in a session object between calls. Tool names are
namespaced `secondmind_*` to avoid collision with any other knowledge-layer MCP server
registered in the same client. Error responses use JSON-RPC `-32602` (Invalid Params) for
not-found/bad-argument conditions — the current standard code, not the deprecated `-32002`.

| Tool | Input schema (JSON Schema 2020-12) | Output | Notes |
|---|---|---|---|
| `secondmind_put` | `{id?, type, title, body, scope?, tags?, ttl_days?}` | `{id, created, updated}` | `type` constrained to the 4 enum values via schema, not runtime-only validation. |
| `secondmind_get` | `{id}` | `{id, type, title, body, ...frontmatter}` or error | Error if not found: `-32602`. |
| `secondmind_search` | `{query, limit?, cursor?}` | `{results: [...], next_cursor}` | `cursor` is the explicit-handle pattern — no hidden session state. |
| `secondmind_list` | `{type?, tag?}` | `{items: [{id, title, type}]}` | |
| `secondmind_export` | `{}` | `{schema_version, count, bundle}` | Returns the full bundle inline (no session-scoped temp file). |
| `secondmind_import` | `{bundle, dry_run?}` | `{imported, skipped, errors}` | Idempotent. Forward-tolerant of a newer `schema_version` than this server knows about. |

The `mcp` (pip) Python SDK is the only allowed dependency, imported exclusively inside
`secondmind_mcp/`. The `secondmind` core package never imports from `secondmind_mcp` —
verified by a CI job that runs the core test suite with `mcp` not installed.

---

## 7. Export/import bundle schema

```json
{
  "schema_version": 1,
  "exported_at": "2026-08-09T00:00:00Z",
  "count": 42,
  "items": [
    {
      "id": "...", "type": "...", "title": "...", "body": "...",
      "scope": "", "entities": [], "tags": [], "source": "manual",
      "created": "...", "updated": "...", "ttl_days": null, "supersedes": null
    }
  ]
}
```

- **Idempotent**: importing the same bundle twice never creates duplicates (matched by `id`,
  conflict-classified per §5).
- **Forward-tolerant**: a bundle with a higher `schema_version` than this build knows about is
  imported using only the fields this build understands, with a warning — never a crash.
- **Interop-shaped**: this shape intentionally matches the existing AUPS CKL / second-brain
  skill bundle format field-for-field, so a bundle can move between systems with zero
  translation code, even though SecondMind's own MCP tool names are namespaced differently.

---

## 8. Non-functional targets (measured in `BENCHMARKS.md`, never claimed unmeasured)

- Search p95 latency: target sub-50ms at 10,000 notes on a stdlib-only laptop-class machine.
- Put latency: target sub-20ms p95 (single note write + index update).
- Full rebuild: reported, not gated — expected to scale roughly linearly with vault size.
- All numbers regenerated whenever `sqlite_index.py`, `search.py`, or `store.py` changes.

---

## 9. Extension points (documented now, not built now — see plan's YAGNI section)

- **Streamable HTTP transport** — additive only. Because no MCP tool relies on hidden session
  state (§6), adding a stateless Streamable HTTP transport later requires zero tool-contract
  changes.
- **Additional embedders** — `secondmind.hashing_embedder` implements an `Embedder` Protocol;
  a future optional extra could add a real ML embedder behind the same interface, following the
  reference system's proven pattern of a try/except fallback to the stdlib default.
- **Agent Plugins packaging** — `plugin.json`/`mcp.json`/`skills/` (Agent Plugins 1.0.0) means
  new clients that adopt the spec need zero SecondMind-side integration code.
