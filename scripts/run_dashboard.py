"""Run SecondMind's web dashboard — stdlib http.server only, no dependency.

Serves search/browse/view/put/supersede over HTTP for a browser, bound to
127.0.0.1 only. Reads from and writes to the same vault the CLI and MCP
adapter use — pass ``--vault``/``--index-db`` to point at a specific one,
or set ``SECONDMIND_VAULT``/``SECONDMIND_INDEX_DB`` env vars (same
contract as every other SecondMind entry point).

Run with:

    python3 scripts/run_dashboard.py [--port 8765] [--vault PATH] [--index-db PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.server import build_server  # noqa: E402
from secondmind.paths import default_index_db, default_vault_root  # noqa: E402
from secondmind.sqlite_index import SqliteIndex  # noqa: E402
from secondmind.store import VaultStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--vault", default=None)
    parser.add_argument("--index-db", default=None)
    args = parser.parse_args()

    env = {}
    if args.vault:
        env["SECONDMIND_VAULT"] = args.vault
    if args.index_db:
        env["SECONDMIND_INDEX_DB"] = args.index_db

    vault_root = default_vault_root(env=env or None)
    index_db = default_index_db(env=env or None)

    store = VaultStore(vault_root)
    index = SqliteIndex(index_db)

    print(f"SecondMind dashboard — vault: {vault_root}")
    print(f"Serving on http://127.0.0.1:{args.port}/  (Ctrl+C to stop)")

    server = build_server(store, index, port=args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        index.close()


if __name__ == "__main__":
    main()
