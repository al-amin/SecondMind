#!/bin/sh
# SecondMind launcher (POSIX: macOS, Linux, WSL, Git-Bash on Windows).
#
# Never assumes `python3` exists on PATH — probes what's actually there at
# runtime, in this order: python3, python, py -3 (the Windows launcher,
# sometimes present in Git-Bash/WSL PATH). Fails with a clear, actionable
# message if none are found, rather than a confusing "command not found".
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

find_python() {
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    if command -v py >/dev/null 2>&1; then
        echo "py -3"
        return 0
    fi
    return 1
}

PY=$(find_python) || {
    echo "secondmind: no Python 3 interpreter found on PATH (tried: python3, python, py -3)." >&2
    echo "Install Python 3.9+ from https://www.python.org/downloads/ and try again." >&2
    exit 127
}

# Intentionally unquoted: PY may be the two-token "py -3" and needs word
# splitting to invoke correctly.
cd "$REPO_ROOT"
exec $PY -m secondmind "$@"
