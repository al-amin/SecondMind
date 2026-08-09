# SecondMind — Roadmap

`main` is pinned at [`v1.0.0`](https://github.com/al-amin/SecondMind/releases/tag/v1.0.0) —
zero-install core, stateless MCP adapter, Agent Plugins packaging, CI-green on macOS/Linux/
Windows. All v2+ work happens on the `v2` branch and only merges back when it's ready to ship.

**Status (2026-08-09): all items below are in active development on `v2`, except Skill/plugin
discovery, which stays backlog — no concrete trigger for it yet (see its section below).**

## v2 — protocol & client expansion

1. **Port `secondmind_mcp/server.py` to `mcp` 2.0.0's API.** v1 pins `mcp>=1.2,<2.0`
   deliberately — 2.0 is a breaking rewrite of the low-level `Server` class (no more
   `list_tools()`/`call_tool()` decorators, a different `run()` signature). Discovered while
   fixing v1's CI, documented rather than rushed. Real, scoped work: re-verify every one of the
   6 tool contracts and the stateless design (SPEC.md §6) still hold under the new API.
2. **Streamable HTTP transport**, additive on top of the 2.0 port. v1 ships stdio only by
   design — because no tool relies on hidden session state, this is a pure addition, not a
   redesign (documented as the extension point in `SPEC.md` §9 since v1). Unlocks a
   browser-based or remote MCP client, not just a locally-spawned process.
3. **Verify (not build) Codex/Gemini/other MCP-compliant clients.** Once a client implements
   the standard, SecondMind needs zero client-specific code — the work here is confirming it,
   not writing new integration code.

## v2 — data & intelligence

4. **Optional real semantic embedder**, behind the existing `Embedder` protocol.
   `HashingEmbedder` (stdlib, zero download) stays the default for every user forever — a
   `secondmind[semantic]` extra would add something like `sentence-transformers`, wrapped in a
   try/except fallback to `HashingEmbedder` if the extra isn't installed OR the model fails to
   download (offline machine, etc.). New users never download anything by default; this is
   strictly opt-in, mirroring the pattern already proven in the AUPS reference system this
   project was inspired by.
5. **TTL/pruning enforcement.** `ttl_days` is already stored on every note (SPEC.md §1.1) but
   nothing acts on it yet — add a `secondmind prune` command/tool that expires notes past their
   TTL.
6. **Search performance past 10,000 notes**, if real usage ever reaches that scale.
   `BENCHMARKS.md` already reports the current gap honestly (p95 ~86-96ms vs. a 50ms
   aspirational target at 10k notes). Revisit only with real evidence of need — e.g., skip the
   dense cosine scan whenever lexical BM25 already fills `limit`.

## v2 — surface area

7. **Dashboard write/edit endpoints.** v1's dashboard is read-only by explicit decision, not a
   YAGNI inference. A v2 could add `put`/`supersede` through the browser.
8. **Vault migration/merge tooling.** v1 deliberately starts from an empty vault. A real script
   to import an existing personal Obsidian vault (or merge with the AUPS CKL / second-brain
   skill's bundle format, which SecondMind's export schema is already interop-shaped for per
   SPEC.md §7) into a SecondMind vault.

## Revisit later, not now (real gate re-check, not a blanket no)

- **Session reflection** (periodically distill notes into a higher-level summary). Blocked on
  a real capability SecondMind doesn't have yet: summarizing text needs an LLM call, and
  `HashingEmbedder` can only compare text, not summarize it. The natural unblock is item #2's
  MCP 2.0 port — MCP's sampling capability lets a server ask the *client's own LLM* to do the
  summarization, with no separate API key and no break to the zero-install-by-default
  promise. Sequence after the 2.0 port, not before.
- **Skill/plugin discovery** (auto-index other Claude Skills or MCP servers on the machine).
  In the AUPS system this fed other AUPS plugins — SecondMind has no such consumer today, so
  it still fails the "does this need to exist" gate as stated. Becomes a real v2 feature only
  with a concrete trigger — e.g., "SecondMind should discover and let me search across other
  Claude Skills on this machine too." Revisit if/when that concrete need shows up, not
  speculatively.

## Explicitly out of scope (not just "later" — actually not needed)

Postgres/pgvector backend (violates zero-install directly — SQLite already meets measured
performance targets at personal-knowledge-base scale), vault reorganization/wiki
auto-generation, cross-plugin timeline writer (no plugin ecosystem to feed). These solve
problems specific to the AUPS router system SecondMind was inspired by, not problems
SecondMind itself has as a standalone product.
