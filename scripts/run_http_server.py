"""Run SecondMind's MCP server over Streamable HTTP instead of stdio.

Requires the ``mcp`` extra (``pip install -e ".[mcp]"``) — uvicorn and
starlette come along as its transitive dependencies, so no new dependency
is introduced for this transport.

Run with:

    python3 scripts/run_http_server.py [--port 8765] [--vault PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

from secondmind_mcp.http_transport import build_http_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--vault", default=None)
    args = parser.parse_args()

    env = {"SECONDMIND_VAULT": args.vault} if args.vault else None
    app = build_http_app(env=env)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
