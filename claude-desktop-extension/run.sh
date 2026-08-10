#!/bin/sh
# Entry point mirror of manifest.json's mcp_config -- kept in sync so this
# extension launches correctly whether Claude Desktop invokes mcp_config
# directly or falls back to entry_point. Uses uv's absolute path (not bare
# "uv") because extension processes may launch with a minimal PATH that
# doesn't include /opt/homebrew/bin. --extra mcp ensures uv resolves this
# project's own isolated environment with the mcp SDK installed, never a
# stray system python3 that might have an incompatible mcp version.
exec /opt/homebrew/bin/uv run --directory "/Users/al.amin1/dev/personal/gitHub_personal/SecondMind" \
  --extra mcp \
  python3 -m secondmind_mcp.server
