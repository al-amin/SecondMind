# SecondMind

**One memory. Every AI. Any machine.**

SecondMind is a portable, cross-session memory layer for AI assistants. Tell it something
once — a fact, a decision, a lesson — and any MCP-compatible AI client can recall it later,
on any machine, with nothing to install beyond a stock Python interpreter.

## Why

Every AI chat starts from zero. Close the tab, lose the context. SecondMind fixes that with a
plain-text vault (Markdown + YAML frontmatter, Obsidian-compatible but not Obsidian-dependent),
a fast local search index, and a standard MCP server so Claude Desktop, Claude Code, and any
future MCP-compliant client can read and write it — no server to run, no account to create, no
data leaving your machine.

## Status

Early build. See [`SPEC.md`](./SPEC.md) for the full contract and
[`ARCHITECTURE.md`](./ARCHITECTURE.md) for how the pieces fit together.

## Zero-install philosophy

The core (`secondmind/`) runs with a stock `python3` — no `pip install` required. Only the
optional MCP adapter needs one dependency (the official `mcp` SDK), isolated so the core never
depends on it:

```bash
python3 -m secondmind put --title "My first note" --body "Hello, SecondMind."
python3 -m secondmind search "hello"
```

## Design principles

- **Vault is truth.** Plain Markdown files. The search index is a disposable, rebuildable
  cache — delete it any time, it comes back from the vault.
- **Stateless MCP, built for the 2026-07-28 spec.** No hidden session state, explicit-handle
  pagination, standard error codes, JSON Schema 2020-12 tool schemas.
- **Cross-platform for real.** macOS and Windows are both CI-tested, including the native
  launcher scripts — not "should work," verified to work.
- **Hybrid search, justified.** SQLite FTS5 (an inverted index) + BM25 ranking + a stdlib
  hashing embedder, fused with Reciprocal Rank Fusion. No linear scans on the hot path.
- **Agent Plugins packaging.** One `plugin.json`/`mcp.json` manifest, portable across any
  client that adopts the open Agent Plugins 1.0.0 standard.

## License

Apache 2.0 — see [`LICENSE`](./LICENSE).
