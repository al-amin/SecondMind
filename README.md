<div align="center">

# SecondMind

**One memory. Every AI. Any machine.**

[![CI](https://github.com/al-amin/SecondMind/actions/workflows/ci.yml/badge.svg)](https://github.com/al-amin/SecondMind/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)

</div>

SecondMind is a portable, cross-session memory layer for AI assistants. Tell it something
once — a fact, a decision, a lesson — and any MCP-compatible AI client can recall it later, on
any machine, with nothing to install beyond a stock Python interpreter and
[`uv`](https://docs.astral.sh/uv/getting-started/installation/).

<div align="center">

### [▶ Watch the demo](https://youtu.be/8Bj2PdPscmY)

[![SecondMind demo — Persistent AI Memory Across Devices](https://img.youtube.com/vi/8Bj2PdPscmY/maxresdefault.jpg)](https://youtu.be/8Bj2PdPscmY)

</div>

---

## Table of contents

- [Why SecondMind](#why-secondmind)
- [Why `uv`](#why-uv)
- [Quick start — Claude Desktop](#quick-start--claude-desktop)
- [Quick start — Claude Code](#quick-start--claude-code)
- [Quick start — CLI only, no AI client](#quick-start--cli-only-no-ai-client)
- [Web dashboard](#web-dashboard)
- [Full verification walkthrough](#full-verification-walkthrough)
- [Design principles](#design-principles)
- [Documentation](#documentation)
- [Versioning](#versioning)
- [License](#license)

---

## Why SecondMind

Every AI chat starts from zero. Close the tab, lose the context. SecondMind fixes that with:

- A **plain-text vault** — Markdown + YAML frontmatter, Obsidian-compatible but not
  Obsidian-dependent. You own the files; nothing is locked in a database format.
- A **fast local search index** — hybrid BM25 + semantic ranking, entirely on your machine.
- A **standard MCP server** — Claude Desktop, Claude Code, and any future MCP-compliant client
  can read and write the same memory.

No server to run, no account to create, no data leaving your machine.

## Why `uv`

The core CLI (`python3 -m secondmind ...`) needs nothing beyond a stock Python — but the MCP
server Claude Desktop/Code actually talks to (`secondmind_mcp/`) has one real, hard dependency:
the official [`mcp`](https://pypi.org/project/mcp/) SDK. `uv` isn't magic — it's just the
recommended way to get that installed into an isolated environment automatically, so it never
conflicts with whatever else is on your system Python.

The one-click Claude Desktop extension below always uses `uv` (it's baked into `manifest.json`,
which is what makes install a single click rather than a manual venv setup). If you're
registering SecondMind manually instead (Claude Code, or Option B in
[`TESTING_WITH_CLAUDE.md`](./TESTING_WITH_CLAUDE.md)), you can manage the venv yourself and
skip `uv` entirely:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[mcp]"
python -m secondmind_mcp.server   # point Claude's config at this venv's python instead of uv
```

---

## Quick start — Claude Desktop

*Recommended path: no manual config file editing.*

You need Claude Desktop and [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
installed. One extra field to fill in at install time — everything else is a single click.

<details open>
<summary><strong>macOS</strong></summary>

1. Install `uv` if you don't have it:
   ```bash
   brew install uv
   ```
   (or use the installer script on [uv's installation page](https://docs.astral.sh/uv/getting-started/installation/))
2. Clone this repo:
   ```bash
   git clone https://github.com/al-amin/SecondMind.git
   ```
3. Claude Desktop → **Settings → Extensions → Install Unpacked Extension** → select the
   `claude-desktop-extension` folder inside your clone.
4. Click **Configure** and set:
   - **SecondMind repo location** (required) — the full path to your clone (the folder
     containing `pyproject.toml`). Claude Desktop copies the extension's own files elsewhere on
     install, so the launcher can no longer find the repo on its own — this field is the only
     way it knows where your clone actually is.
   - **Vault / index location** — optional, defaults are fine for everyday use.
5. Click **Save**, then fully quit and reopen Claude Desktop (closing the window is not
   enough).

</details>

<details>
<summary><strong>Windows</strong></summary>

1. Install `uv` — open PowerShell and run:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
   (or see the [official installer docs](https://docs.astral.sh/uv/getting-started/installation/))
2. Clone this repo:
   ```powershell
   git clone https://github.com/al-amin/SecondMind.git
   ```
3. Claude Desktop → **Settings → Extensions → Install Unpacked Extension** → select the
   `claude-desktop-extension` folder inside your clone.
4. Click **Configure** and set **SecondMind repo location** (required) to the full path of
   your clone, e.g. `C:\Users\yourname\SecondMind` — same reason as macOS above.
5. Click **Save**, then fully quit and reopen Claude Desktop.

</details>

**If it doesn't connect on either platform**, run the built-in diagnostic before anything else:

```bash
python3 scripts/diagnose.py     # macOS / Linux
python scripts\diagnose.py      # Windows
```

One command — checks Python, `uv`, the venv, the vault, both client registrations, and whether
an already-installed extension copy is stale — and tells you exactly what to fix. Not sure
Python is even installed on Windows? Run `scripts\diagnose.bat` instead (double-click it, or
run it in `cmd.exe`) — it checks for a Python interpreter first, with no Python required to run
itself, then hands off to `diagnose.py` once confirmed.

**Try it**: in a new chat, say *"Remember that I prefer TypeScript over JavaScript for new
projects."* Then, in any future chat: *"What do you know about my language preferences?"*

---

## Quick start — Claude Code

```bash
git clone https://github.com/al-amin/SecondMind.git
cd SecondMind
claude mcp add secondmind -- uv run --directory "$(pwd)" --extra mcp python3 -m secondmind_mcp.server
```

Then ask Claude Code to remember something, in any session, and recall it in a different one —
that's the actual "any session, any client" promise, working end to end.

---

## Quick start — CLI only, no AI client

The core (`secondmind/`) needs nothing beyond a stock `python3` — no `pip install` required:

```bash
python3 -m secondmind put --type core --title "My first note" --body "Hello, SecondMind."
python3 -m secondmind search "hello"
```

---

## Web dashboard

A modern, local-only web UI — search, browse, and save notes from a browser.

```bash
uv run --extra mcp python3 scripts/run_dashboard.py --port 8765
```

Then open `http://127.0.0.1:8765/`. Bound to `127.0.0.1` only — never reachable from another
machine on your network.

---

## Full verification walkthrough

[`TESTING_WITH_CLAUDE.md`](./TESTING_WITH_CLAUDE.md) is the step-by-step, actually-verified
guide for the complete flow: save in Claude Desktop, recall in Claude Code, export the vault,
import it somewhere else, and browse it in the web dashboard. Every command in it was run for
real against a real client before being written down.

---

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

---

## Documentation

| Document | Covers |
|---|---|
| [`SPEC.md`](./SPEC.md) | The full contract: data model, storage guarantees, MCP tool contracts, CLI contract, export/import schema. |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | How the pieces fit together — system diagrams, sequence diagrams, v2 additions. |
| [`ROADMAP.md`](./ROADMAP.md) | What shipped, what's next. |
| [`TESTING_WITH_CLAUDE.md`](./TESTING_WITH_CLAUDE.md) | Real end-to-end client verification, step by step. |
| [`BENCHMARKS.md`](./BENCHMARKS.md) | Measured performance numbers, not claims. |

---

## Versioning

[`v1.0.0`](https://github.com/al-amin/SecondMind/releases/tag/v1.0.0) is tagged and stays
available if you ever want to roll back to the original zero-install core before the v2
protocol/feature work (mcp 2.0, Streamable HTTP, semantic embedder, pruning, migration, session
reflection):

```bash
git checkout v1.0.0
```

`main` always tracks the current shipping version.

---

## License

Apache 2.0 — see [`LICENSE`](./LICENSE).
