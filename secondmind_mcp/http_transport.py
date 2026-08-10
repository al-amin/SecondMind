"""Stateless Streamable HTTP transport — additive over the stdio adapter.

Bounded-context responsibility: expose the exact same 6 tools as
``secondmind_mcp/server.py`` over HTTP instead of stdio, with zero tool
contract changes (SPEC.md §9/§10.3 documented this as a pure addition
since v1, because no tool ever relied on hidden session state). Bound to
``127.0.0.1`` only via ``host="127.0.0.1"`` in ``streamable_http_app``,
which also activates the SDK's own DNS-rebinding protection — a request
whose ``Host`` header doesn't match a local address is rejected with 421
before it ever reaches a tool handler.

Unlike the stdio adapter, ``dispatch_tool_call`` here resolves the vault
per HTTP request from a fixed ``env`` captured at startup, not per-process
env vars — a Streamable HTTP server is long-running and may serve many
independent requests, but always against the same configured vault (the
per-request env override that ``dispatch_tool_call`` supports is used to
pin that vault once, at app-build time, not to vary it per request).
"""

from __future__ import annotations

import os

from starlette.applications import Starlette

from secondmind_mcp.server import build_server


def build_http_app(env: dict[str, str] | None = None) -> Starlette:
    """Build the stateless Streamable HTTP ASGI app for SecondMind's MCP server.

    ``env`` pins the vault/index location for every request this app
    instance serves — pass ``SECONDMIND_VAULT``/``SECONDMIND_INDEX_DB`` to
    override the default (``~/.secondmind/...``), matching the stdio
    adapter's own env-var contract.

    Applied via ``os.environ`` at build time rather than threaded through
    per request: ``on_call_tool`` (in ``secondmind_mcp/server.py``) calls
    ``dispatch_tool_call`` with no explicit ``env``, so it always reads
    the process environment — correct for a single long-running server
    process serving one configured vault, matching how the stdio adapter
    already resolves its vault from ``os.environ`` implicitly.
    """
    if env:
        os.environ.update(env)

    server = build_server()
    return server.streamable_http_app(stateless_http=True, host="127.0.0.1")
