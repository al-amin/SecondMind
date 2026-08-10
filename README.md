# SecondMind

**One memory. Every AI. Any machine.**

SecondMind is a portable, cross-session memory layer for AI assistants. Tell it something
once — a fact, a decision, a lesson — and any MCP-compatible AI client can recall it later,
on any machine, with nothing to install beyond a stock Python interpreter and
[`uv`](https://docs.astral.sh/uv/getting-started/installation/).

## Why

Every AI chat starts from zero. Close the tab, lose the context. SecondMind fixes that with a
plain-text vault (Markdown + YAML frontmatter, Obsidian-compatible but not Obsidian-dependent),
a fast local search index, and a standard MCP server so Claude Desktop, Claude Code, and any
future MCP-compliant client can read and write it — no server to run, no account to create, no
data leaving your machine.

## Quick start — Claude Desktop (recommended, no config editing)

You only need Claude Desktop and [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
installed. No manual config file editing required.

1. Clone this repo: `git clone https://github.com/al-amin/SecondMind.git`
2. Claude Desktop → **Settings → Extensions → Install Unpacked Extension** → select the
   `claude-desktop-extension` folder inside your clone.
3. (Optional) Click **Configure** to change where your vault lives — it defaults to
   `~/.secondmind/vault`, created automatically on first use.
4. Fully quit and reopen Claude Desktop (closing the window is not enough — see
   [`TESTING_WITH_CLAUDE.md`](./TESTING_WITH_CLAUDE.md) if it doesn't connect).
5. In a new chat: *"Remember that I prefer TypeScript over JavaScript for new projects."*
   Then, in any future chat: *"What do you know about my language preferences?"*

## Quick start — Claude Code

```bash
git clone https://github.com/al-amin/SecondMind.git
cd SecondMind
claude mcp add secondmind -- uv run --directory "$(pwd)" --extra mcp python3 -m secondmind_mcp.server
```

Then ask Claude Code to remember something, in any session, and recall it in a different one.

## Quick start — no AI client, just the CLI

The core (`secondmind/`) needs nothing beyond a stock `python3` — no `pip install` required:

```bash
python3 -m secondmind put --type core --title "My first note" --body "Hello, SecondMind."
python3 -m secondmind search "hello"
```

## Full verification walkthrough

[`TESTING_WITH_CLAUDE.md`](./TESTING_WITH_CLAUDE.md) is the step-by-step, actually-verified
guide for the complete flow: save in Claude Desktop, recall in Claude Code, export the vault,
import it somewhere else, and browse it in the web dashboard. Every command in it was run for
real against a real client before being written down.

## Web dashboard (optional)

```bash
uv run --extra mcp python3 scripts/run_dashboard.py --port 8765
```

Then open `http://127.0.0.1:8765/` — browse, search, and edit notes from a browser. Bound to
localhost only, never reachable from another machine.

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

## Documentation

- [`SPEC.md`](./SPEC.md) — the full contract: data model, storage guarantees, MCP tool
  contracts, CLI contract, export/import schema.
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — how the pieces fit together, with diagrams.
- [`ROADMAP.md`](./ROADMAP.md) — what shipped, what's next.
- [`TESTING_WITH_CLAUDE.md`](./TESTING_WITH_CLAUDE.md) — real end-to-end client verification.
- [`BENCHMARKS.md`](./BENCHMARKS.md) — measured performance numbers, not claims.

## Versioning

[`v1.0.0`](https://github.com/al-amin/SecondMind/releases/tag/v1.0.0) is tagged and stays
available if you ever want to roll back to the original zero-install core before the v2
protocol/feature work (mcp 2.0, Streamable HTTP, semantic embedder, pruning, migration,
session reflection) — `git checkout v1.0.0`. `main` always tracks the current shipping version.

## License

Apache 2.0 — see [`LICENSE`](./LICENSE).
