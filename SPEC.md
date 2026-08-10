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
| `prune` (v2) | `--dry-run` | Delete notes past their `ttl_days` expiry. Prints `{pruned: [ids]}`. |
| `migrate` (v2) | `<external_vault_path>`, `--dry-run` | Scan any directory of Markdown+frontmatter files and import them (see §12). Run `rebuild` afterward to make imported notes searchable, same as `import`. |

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
| `secondmind_prune` (v2) | `{dry_run?}` | `{pruned: [ids]}` | Deletes notes past their `ttl_days` expiry (see §1.1). A note with no `ttl_days` is never eligible. |

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
  changes. Built in v2 — see §11.
- **Additional embedders** — `secondmind.hashing_embedder` implements an `Embedder` Protocol;
  a future optional extra could add a real ML embedder behind the same interface, following the
  reference system's proven pattern of a try/except fallback to the stdlib default.
- **Agent Plugins packaging** — `plugin.json`/`mcp.json`/`skills/` (Agent Plugins 1.0.0) means
  new clients that adopt the spec need zero SecondMind-side integration code.

---

## 10. v2 addendum — `mcp` 2.0.0 port (ROADMAP.md item 1)

v1 pinned `mcp>=1.2,<2.0` after discovering 2.0.0 is a breaking rewrite of the low-level
`Server` API, incompatible with v1's decorator-based adapter. This section is the contract the
v2 port executes against — researched from the official SDK migration guide
(`py.sdk.modelcontextprotocol.io/migration/`) and confirmed against the actual installed 2.0.0
package, not assumed.

### 10.1 What changes in `secondmind_mcp/server.py`

- **Handler registration**: decorators (`@server.list_tools()`, `@server.call_tool()`) are
  gone. Handlers are passed as `on_list_tools=`/`on_call_tool=` keyword arguments to the
  `Server(...)` constructor.
- **Handler signature**: `async def handler(ctx: ServerRequestContext, params: <TypedParams>) -> <TypedResult>`
  — no more `(name, arguments)` unpacking. `on_call_tool` receives `CallToolRequestParams`
  (with `.name`, `.arguments`) and must return `CallToolResult` (with keyword `content`,
  `is_error`) or `InputRequiredResult`.
- **Field names**: all Python attribute access is snake_case (`input_schema`, `is_error`,
  `next_cursor`) — the JSON wire format is unchanged (still camelCase via Pydantic aliases).
  Constructor kwargs still accept the old camelCase spelling, but SecondMind's own code uses
  snake_case throughout for consistency with the rest of the codebase.
- **Exceptions**: `McpError` is renamed `MCPError` (importable from `mcp.shared.exceptions` or
  top-level `mcp`), constructed as `MCPError(code, message, data=None)` — no more wrapping an
  `ErrorData`. Raising `MCPError` from `on_call_tool` now surfaces as a top-level JSON-RPC error
  (unchanged intent from v1's `-32602` contract in §6). A non-`MCPError` exception is **no
  longer auto-wrapped** into an error-flagged tool result — `on_call_tool` must catch its own
  exceptions and return `CallToolResult(is_error=True, content=[...])` for tool-execution
  failures the calling LLM should see and react to (distinct from protocol-level rejections,
  which use `MCPError`).
- **What does NOT change**: `stdio_server()` import path and usage, `server.run(read_stream,
  write_stream, initialization_options)`, `server.create_initialization_options()`. The v1
  serving scaffolding in `main()`/`_run_stdio()` needs no changes — only the handler
  registration and signatures inside `build_server()` and `dispatch_tool_call()`.

### 10.2 Stateless guarantee re-confirmed (not just re-stated)

Real finding from the migration guide, not assumed: on a connection negotiated at the
2026-07-28 protocol version — which is what a v2 SDK client defaults to against a v2 SDK
server, `mode='auto'`, on every transport including stdio — **there is no back-channel for
server-initiated requests at all**. Calling `ctx.session.create_message()` (sampling),
`ctx.elicit()`, or `ctx.session.list_roots()` raises `NoBackChannelError` unconditionally. This
is a spec-level restriction (SEP-2577 deprecates Roots/Sampling/Logging entirely), not an SDK
implementation gap. SecondMind's adapter already needs none of these (§6's stateless design
predates this finding and remains correct), so the port requires no behavior change here — this
is confirmed as a non-issue, not worked around.

### 10.3 What this unblocks vs. blocks for the rest of the v2 roadmap

- **Streamable HTTP transport** (ROADMAP.md item 2): unaffected by the sampling restriction —
  SecondMind's tools never needed a back-channel. Purely additive once the port lands. Built
  and live-verified (§11).
- **Session reflection** (ROADMAP.md item 7): the original plan ("server asks the client's LLM
  to summarize via sampling") is **not viable** under 2026-07-28 — confirmed by this research,
  not assumed. Corrected design: a tool returns raw recent notes; the calling AI does the
  summarization in its own turn and writes the result back via `secondmind_put`. No sampling,
  no back-channel, no LLM dependency inside SecondMind itself.

---

## 11. v2 addendum — Streamable HTTP transport (ROADMAP.md item 2)

Additive over stdio, per §9/§10.3. Same 6 tools, same contracts, zero tool-contract changes —
only the wire transport differs.

- **Module**: `secondmind_mcp/http_transport.py`, built on `Server.streamable_http_app(...)`
  from the `mcp` package's own transitive dependencies (`starlette`, `uvicorn`) — no new
  dependency introduced beyond the existing `mcp` extra.
- **Stateless mode**: `stateless_http=True` — no `Mcp-Session-Id`, every HTTP request is
  independent. Live-verified: two separate `POST /mcp` requests (a `secondmind_put` followed by
  an unrelated `secondmind_search`) succeed with no session negotiation between them.
- **Bound to localhost**: `host="127.0.0.1"` passed to `streamable_http_app`, which also
  activates the SDK's own DNS-rebinding protection — a request with a non-local `Host` header
  is rejected with HTTP 421 before reaching any tool handler. Live-verified, not assumed: a
  request with `Host: evil.example.com` is confirmed rejected.
- **Vault configuration**: resolved once at `build_http_app()` call time via `os.environ`, not
  per request — correct for a single long-running server process serving one configured vault
  for its whole lifetime (the same env-var contract as stdio: `SECONDMIND_VAULT`/
  `SECONDMIND_INDEX_DB`).
- **Running it**: `python3 scripts/run_http_server.py [--port 8765] [--vault PATH]` — separate
  from `mcp.json` (which declares the stdio entry Claude Desktop/Code spawn); this transport is
  for a remote or browser-based MCP client, run manually or by a different deployment, not
  something Claude Desktop/Code launch automatically.

---

## 12. v2 addendum — vault migration (ROADMAP.md item 9)

`secondmind.migrate.scan_external_vault(vault_root)` adapts any directory of `.md` files with
YAML-subset frontmatter into the §7 bundle shape, then reuses the existing, already-tested
`import_bundle()` — no new import machinery.

- **Field defaults**: a note missing an optional field gets a sensible default — `type` falls
  back to `semantic` (including on an unrecognized/foreign type string), `title` falls back to
  the filename, `created`/`updated` fall back to the current time if absent.
- **Id sanitization**: an external vault's filenames or frontmatter `id` values very often
  don't match SecondMind's strict `[a-z0-9-]+` pattern (spaces, punctuation, uppercase,
  underscores are all common in real personal Obsidian vaults). Every id is validated and, if
  invalid, slugified via the same `generate_note_id()` collision-avoidance logic `put` already
  uses when no id is supplied — verified by direct reproduction with a realistic filename
  (`"My Weird Note Name!.md"`), which raised `InvalidNoteIdError` all the way through
  `import_bundle()` before this sanitization was added.
- **Malformed files are skipped, not fatal**: a file with no frontmatter block, or an
  unparseable one, is skipped and simply absent from the scanned bundle — one bad file in a
  large personal vault must never abort scanning the rest.
- **Post-migration step**: like `import`, `migrate` writes to the vault but does not
  automatically update the search index — run `rebuild` afterward (documented in the CLI
  contract, §4) to make migrated notes searchable. Live-verified end-to-end: a real directory
  with a realistic filename, migrated via the CLI, then made searchable via `rebuild`.
