# SecondMind — Architecture

This document is updated whenever a phase changes a system boundary. See [`SPEC.md`](./SPEC.md)
for the full contract; this document is the map of how the pieces connect.

## System context

Three ways to reach SecondMind: an MCP client (Claude Desktop/Code today; any MCP-compliant
client tomorrow), a browser hitting the local read-only dashboard, or a terminal user via the
CLI. All three ultimately go through the same core package — there is exactly one source of
truth (the vault) and one derived cache (the SQLite index), never a fork of logic per surface.

```mermaid
graph TD
    A[Claude Desktop / Code<br/>any MCP client] -->|stdio JSON-RPC| B[secondmind_mcp/server.py]
    C[Browser] -->|HTTP GET, localhost only| D[dashboard/server.py]
    E[Terminal user] -->|python3 -m secondmind| F[secondmind/cli.py]

    B --> G[secondmind/store.py]
    D -->|read-only queries| H[secondmind/sqlite_index.py]
    F --> G

    G --> H
    G --> I[secondmind/vault<br/>Markdown + frontmatter]
    H -->|rebuilds from| I
```

**ASCII fallback:**
```
  Claude Desktop/Code        Browser              Terminal user
        |                      |                       |
   stdio JSON-RPC         HTTP (127.0.0.1)        python3 -m secondmind
        v                      v                       v
  secondmind_mcp/         dashboard/server.py      secondmind/cli.py
   server.py                   |                        |
        |                read-only queries               |
        +---------------------+------------------------->+
                              v
                     secondmind/store.py
                          /        \
                         v          v
              secondmind/vault   secondmind/sqlite_index.py
              (Markdown, TRUTH)  (SQLite FTS5, DISPOSABLE CACHE)
                         ^______________|
                         index always rebuilds FROM the vault,
                         never the reverse
```

## Data flow: vault vs. index vs. export bundle

```mermaid
graph LR
    V[Vault<br/>Markdown + frontmatter<br/>DURABLE SOURCE OF TRUTH] -->|rebuild/put| I[SQLite Index<br/>FTS5 + hashing embedder<br/>DISPOSABLE CACHE]
    V -->|export| X[Export Bundle<br/>schema-versioned JSON<br/>PORTABILITY ARTIFACT]
    X -->|import| V
    I -.->|never regenerates the vault| V
```

The index rebuilds from the vault; the vault never rebuilds from the index. Deleting the index
file is always safe — the next read triggers a rebuild. Deleting the vault loses data; there is
no other durable copy inside SecondMind itself (git-tracking the vault directory externally,
outside this repo, is the user's own backup strategy).

## Component isolation boundary

`secondmind/` (core) has zero import edges into `secondmind_mcp/` or `dashboard/`. Both of those
depend on the core; the core depends on neither. This is enforced by a CI job that runs the core
test suite in a virtualenv with the `mcp` package deliberately *not* installed — if that job
passes, the boundary is real, not just documented.

```mermaid
graph TD
    MCP[secondmind_mcp/] --> CORE[secondmind/]
    DASH[dashboard/] --> CORE
    CLI[secondmind/cli.py] --> CORE
    CORE -.->|zero edges| MCP
    CORE -.->|zero edges| DASH
```

## Sequence: a `secondmind_search` call end-to-end

```mermaid
sequenceDiagram
    participant Client as MCP Client<br/>(Claude Desktop/Code)
    participant Adapter as secondmind_mcp/server.py
    participant Store as secondmind/store.py
    participant Index as secondmind/sqlite_index.py
    participant Vault as Vault (Markdown files)

    Client->>Adapter: tools/call secondmind_search {query, cursor?}
    Note over Adapter: No session lookup — vault/index path<br/>resolved fresh from env on this call
    Adapter->>Index: search(query, limit)
    Index->>Index: BM25 lexical rank (FTS5)
    Index->>Index: cosine dense rank (hashing embedder)
    Index->>Index: reciprocal_rank_fusion([lexical, dense])
    Index-->>Adapter: ranked note ids
    Adapter->>Store: get(id) for each ranked id
    Store->>Vault: read note file
    Vault-->>Store: frontmatter + body
    Store-->>Adapter: KnowledgeItem
    Adapter-->>Client: {results, next_cursor}
    Note over Client,Adapter: next_cursor is an explicit value the client<br/>threads back — never hidden session state
```

Verified end-to-end (not just in-process) by `scripts/live_probe.py`, which spawns the real
server as a real subprocess over real stdio and drives this exact call sequence.

## Stateless MCP boundary (2026-07-28 spec)

Per the current MCP specification, there is no session object anywhere in
`secondmind_mcp/server.py`. Every tool call resolves the vault/index path fresh via
`secondmind.paths` and reads/writes through `secondmind.store`. The one place state crosses a
call boundary is `secondmind_search`'s `cursor` — an opaque value the client stores and replays,
never something the server remembers between calls (the "explicit-handle pattern" from the
spec). This means any future Streamable HTTP transport can route each request to a different
server process with zero behavior change.

## Packaging: Agent Plugins 1.0.0

```
SecondMind/                      <- the plugin, per agent-plugins.org/specification
├── plugin.json                  <- {"$schema": "...", "name": "secondmind"}
├── mcp.json                     <- declares secondmind_mcp/server.py, "type": "stdio"
├── skills/secondmind/SKILL.md   <- natural-language trigger doc
├── secondmind/                  <- core (this diagram's "CORE")
├── secondmind_mcp/               <- MCP adapter
└── dashboard/                   <- optional read-only web UI
```

Each entry fails independently: if the dashboard is missing or `mcp.json`'s server fails to
start, a compliant client skips that entry and keeps the rest of the plugin working.
