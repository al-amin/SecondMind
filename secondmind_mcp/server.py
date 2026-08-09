"""Stateless MCP stdio server exposing SecondMind's 6 tools.

Bounded-context responsibility: translate MCP tool calls into calls against
:mod:`secondmind.store`/:mod:`secondmind.sqlite_index`/:mod:`secondmind.portability`,
and translate their results/errors into the MCP wire format. This is the
only module in the whole project that imports the ``mcp`` package — the
:mod:`secondmind` core never imports anything from here (verified by
``tests/test_core_isolation.py``).

Designed stateless per the 2026-07-28 MCP specification (SPEC.md §6): no
session object anywhere, every tool call resolves the vault/index path
fresh via ``secondmind.paths``, and pagination uses the explicit-handle
pattern (an opaque ``cursor`` argument the client threads back) rather
than server-side session state. Not-found/bad-argument errors use
``INVALID_PARAMS`` (-32602), the current standard JSON-RPC code — not the
deprecated ``-32002``.
"""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from secondmind.models import KnowledgeType
from secondmind.paths import InvalidNoteIdError, default_index_db, default_vault_root
from secondmind.portability import export_bundle, import_bundle
from secondmind.sqlite_index import SqliteIndex
from secondmind.store import NoteNotFoundError, VaultStore

_SCHEMA = "https://json-schema.org/draft/2020-12/schema"
_KNOWLEDGE_TYPE_ENUM = [member.value for member in KnowledgeType]

TOOLS: list[Tool] = [
    Tool(
        name="secondmind_put",
        description="Create or update a note in SecondMind's memory.",
        input_schema={
            "$schema": _SCHEMA,
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "type": {"type": "string", "enum": _KNOWLEDGE_TYPE_ENUM},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "scope": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "ttl_days": {"type": ["integer", "null"]},
            },
            "required": ["type", "title", "body"],
        },
    ),
    Tool(
        name="secondmind_get",
        description="Retrieve one note by id from SecondMind's memory.",
        input_schema={
            "$schema": _SCHEMA,
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    ),
    Tool(
        name="secondmind_search",
        description="Hybrid BM25+semantic search over SecondMind's memory.",
        input_schema={
            "$schema": _SCHEMA,
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": ["string", "null"]},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="secondmind_list",
        description="List notes in SecondMind's memory, optionally filtered by type/tag.",
        input_schema={
            "$schema": _SCHEMA,
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": _KNOWLEDGE_TYPE_ENUM},
                "tag": {"type": "string"},
            },
        },
    ),
    Tool(
        name="secondmind_export",
        description="Export the entire SecondMind vault as a portable bundle.",
        input_schema={"$schema": _SCHEMA, "type": "object", "properties": {}},
    ),
    Tool(
        name="secondmind_import",
        description="Import a portable bundle into SecondMind's memory.",
        input_schema={
            "$schema": _SCHEMA,
            "type": "object",
            "properties": {
                "bundle": {"type": "object"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["bundle"],
        },
    ),
]


def _invalid_params(message: str) -> MCPError:
    return MCPError(INVALID_PARAMS, message)


def dispatch_tool_call(
    name: str, arguments: dict, env: dict[str, str] | None = None
) -> dict:
    """Execute one tool call and return its result as a plain dict.

    Resolves the vault/index path fresh from ``env`` on every call — no
    session object holds state between calls (SPEC.md §6).
    """
    vault_root = default_vault_root(env=env)
    index_db = default_index_db(env=env)
    store = VaultStore(vault_root)

    try:
        if name == "secondmind_put":
            try:
                knowledge_type = KnowledgeType.from_str(arguments["type"])
            except ValueError as exc:
                raise _invalid_params(str(exc)) from exc
            result = store.put(
                id=arguments.get("id"),
                type=knowledge_type,
                title=arguments["title"],
                body=arguments["body"],
                scope=arguments.get("scope", ""),
                tags=arguments.get("tags", []),
                ttl_days=arguments.get("ttl_days"),
            )
            index = SqliteIndex(index_db)
            try:
                index.put(store.get(result.id))
            finally:
                index.close()
            return {"id": result.id, "created": result.created, "updated": result.updated}

        if name == "secondmind_get":
            try:
                item = store.get(arguments["id"])
            except NoteNotFoundError as exc:
                raise _invalid_params(f"note not found: {arguments['id']}") from exc
            frontmatter, body = item.to_frontmatter()
            return {**frontmatter, "body": body}

        if name == "secondmind_search":
            index = SqliteIndex(index_db)
            try:
                ids = index.search(arguments["query"], limit=arguments.get("limit", 20))
            finally:
                index.close()
            results = []
            for note_id in ids:
                try:
                    item = store.get(note_id)
                    results.append({"id": item.id, "title": item.title})
                except NoteNotFoundError:
                    continue
            return {"results": results, "next_cursor": None}

        if name == "secondmind_list":
            knowledge_type = (
                KnowledgeType.from_str(arguments["type"]) if arguments.get("type") else None
            )
            items = store.list(type=knowledge_type, tag=arguments.get("tag"))
            return {"items": [{"id": item.id, "title": item.title} for item in items]}

        if name == "secondmind_export":
            return {"bundle": export_bundle(store)}

        if name == "secondmind_import":
            result = import_bundle(store, arguments["bundle"], dry_run=arguments.get("dry_run", False))
            return result

    except InvalidNoteIdError as exc:
        raise _invalid_params(str(exc)) from exc

    raise _invalid_params(f"unknown tool: {name}")


async def _handle_list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


async def _handle_call_tool(
    ctx: ServerRequestContext, params: CallToolRequestParams
) -> CallToolResult:
    """Dispatch one tool call, converting exceptions to CallToolResult ourselves.

    v2 no longer auto-wraps a raised exception into an error-flagged tool
    result (SPEC.md §10.1) — MCPError is allowed to propagate (it becomes a
    protocol-level JSON-RPC error, matching the -32602 contract in §6),
    but any other exception must be caught here and returned as
    ``CallToolResult(is_error=True, ...)`` so the calling LLM still sees it
    as a tool result rather than a raw connection error.
    """
    try:
        result = dispatch_tool_call(params.name, params.arguments or {})
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result))],
            is_error=False,
        )
    except MCPError:
        raise
    except Exception as exc:
        return CallToolResult(
            content=[TextContent(type="text", text=str(exc))],
            is_error=True,
        )


def build_server() -> Server:
    """Construct the low-level MCP server with all 6 tools registered, stateless."""
    return Server(
        "secondmind",
        on_list_tools=_handle_list_tools,
        on_call_tool=_handle_call_tool,
    )


async def _run_stdio() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
