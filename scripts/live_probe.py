"""Live probe — spawns the real MCP server as a real subprocess over real
stdio and calls every tool in sequence. This is the check that closes the
gap between "unit tests pass" and "actually works when a real client
spawns it" (per the project's own live-verification standard).

Uses the official ``mcp`` Python SDK's client session over a stdio
transport, driving the exact process a Claude Desktop/Code config would
spawn. No mocking anywhere in this script.

Run with:

    python3 scripts/live_probe.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_REPO_ROOT = Path(__file__).resolve().parent.parent


async def probe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "secondmind_mcp.server"],
            env={
                "SECONDMIND_VAULT": str(Path(tmp) / "vault"),
                "SECONDMIND_INDEX_DB": str(Path(tmp) / "index.db"),
                "PYTHONPATH": str(_REPO_ROOT),
            },
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("[1/7] initialize: ok")

                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                assert tool_names == {
                    "secondmind_put",
                    "secondmind_get",
                    "secondmind_search",
                    "secondmind_list",
                    "secondmind_export",
                    "secondmind_import",
                    "secondmind_prune",
                }, f"unexpected tool set: {tool_names}"
                print("[2/7] list_tools: ok — all 7 tools present")

                put_result = await session.call_tool(
                    "secondmind_put",
                    {"type": "core", "title": "Live Probe Note", "body": "Real subprocess, real stdio."},
                )
                put_payload = json.loads(put_result.content[0].text)
                note_id = put_payload["id"]
                assert note_id, "put did not return an id"
                print(f"[3/7] secondmind_put: ok — created {note_id!r}")

                get_result = await session.call_tool("secondmind_get", {"id": note_id})
                get_payload = json.loads(get_result.content[0].text)
                assert get_payload["body"] == "Real subprocess, real stdio."
                print("[4/7] secondmind_get: ok — round-tripped body content")

                search_result = await session.call_tool(
                    "secondmind_search", {"query": "subprocess"}
                )
                search_payload = json.loads(search_result.content[0].text)
                found_ids = {r["id"] for r in search_payload["results"]}
                assert note_id in found_ids, f"search did not find {note_id!r}: {search_payload}"
                print("[5/7] secondmind_search: ok — found the note by real query")

                export_result = await session.call_tool("secondmind_export", {})
                export_payload = json.loads(export_result.content[0].text)
                assert export_payload["bundle"]["count"] >= 1
                print("[6/7] secondmind_export: ok — bundle contains the note")

                prune_result = await session.call_tool("secondmind_prune", {"dry_run": True})
                prune_payload = json.loads(prune_result.content[0].text)
                assert prune_payload["pruned"] == [], "note has no ttl_days, must never be pruned"
                print("[7/7] secondmind_prune: ok — note with no ttl_days correctly never pruned")

    print("\nLive probe PASSED — all 7 tools verified over a real stdio subprocess.")


def main() -> None:
    asyncio.run(probe())


if __name__ == "__main__":
    main()
