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

## Why `uv`

The core CLI (`python3 -m secondmind ...`) needs nothing beyond a stock Python — but the MCP
server Claude Desktop/Code actually talks to (`secondmind_mcp/`) has one real, hard dependency:
the official [`mcp`](https://pypi.org/project/mcp/) SDK. `uv` isn't magic — it's just the
recommended way to get that installed into an isolated environment automatically, so it never
conflicts with whatever else is on your system Python.

The one-click Claude Desktop extension below always uses `uv` (it's baked into
`manifest.json`, which is what makes install a single click rather than a manual venv setup).
If you're registering SecondMind manually instead (Claude Code, or Option B in
[`TESTING_WITH_CLAUDE.md`](./TESTING_WITH_CLAUDE.md)), you can manage the venv yourself and
skip `uv` entirely:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[mcp]"
python -m secondmind_mcp.server   # point Claude's config at this venv's python instead of uv
```

## Quick start — Claude Desktop (recommended, no config editing)

You need Claude Desktop and [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
installed. No manual config file editing required — one extra field to fill in at install time.

**macOS:**

1. Install `uv` if you don't have it: `brew install uv` (or the installer script on the page
   linked above).
2. Clone this repo: `git clone https://github.com/al-amin/SecondMind.git`
3. Claude Desktop → **Settings → Extensions → Install Unpacked Extension** → select the
   `claude-desktop-extension` folder inside your clone.
4. Click **Configure** and set **SecondMind repo location** to the full path of your clone
   (the folder containing `pyproject.toml`) — this is required. Claude Desktop copies the
   extension's own files elsewhere on install, so the launcher can no longer find the repo on
   its own; this field is the only way it knows where your clone actually is. Vault/index
   location can stay at their defaults.
5. Click **Save**, then fully quit and reopen Claude Desktop (closing the window is not enough).

**Windows:**

1. Install `uv`: open PowerShell and run
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   (or see the [official installer docs](https://docs.astral.sh/uv/getting-started/installation/)).
2. Clone this repo: `git clone https://github.com/al-amin/SecondMind.git`
3. Claude Desktop → **Settings → Extensions → Install Unpacked Extension** → select the
   `claude-desktop-extension` folder inside your clone.
4. Click **Configure** and set **SecondMind repo location** to the full path of your clone
   (e.g. `C:\Users\yourname\SecondMind`) — required, same reason as above.
5. Click **Save**, then fully quit and reopen Claude Desktop.

**Either platform:** if it doesn't connect, run `python3 scripts/diagnose.py` (macOS) or
`python scripts\diagnose.py` (Windows) from inside your clone — one command, checks Python/
`uv`/the venv/vault/both client registrations and whether an already-installed extension copy
is stale, and tells you exactly what to fix. On Windows, if you're not sure Python is even
installed, run `scripts\diagnose.bat` (double-click it, or run it in cmd.exe) instead —
`diagnose.py` needs Python to already exist to run at all, so it can't diagnose "Python is
missing"; `diagnose.bat` is plain batch, checks for that first, and hands off to `diagnose.py`
once confirmed.

Once connected, in a new chat: *"Remember that I prefer TypeScript over JavaScript for new
projects."* Then, in any future chat: *"What do you know about my language preferences?"*

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
