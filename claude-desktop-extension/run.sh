#!/bin/sh
# SecondMind MCP server launcher for the Claude Desktop extension.
#
# manifest.json's mcp_config.command points directly at this script (not a
# bare "uv") because extension processes can launch with a minimal PATH that
# doesn't include wherever uv was installed (observed on this machine with
# Homebrew's /opt/homebrew/bin never being on the extension process's PATH).
# Probing common install locations here means the extension works on any
# user's machine without a hardcoded personal path.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

UV=$(find_uv) || {
    echo "secondmind: no 'uv' executable found (checked PATH, ~/.local/bin, ~/.cargo/bin, /opt/homebrew/bin, /usr/local/bin)." >&2
    echo "Install uv from https://docs.astral.sh/uv/getting-started/installation/ and try again." >&2
    exit 127
}

exec "$UV" run --directory "$REPO_ROOT" --extra mcp python3 -m secondmind_mcp.server
