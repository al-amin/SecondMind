#!/bin/sh
# Run a SecondMind command against a named disposable test vault.
#
# Collapses the repeated
#   SECONDMIND_VAULT=~/.secondmind-<profile>/vault \
#   SECONDMIND_INDEX_DB=~/.secondmind-<profile>/index.db \
#   uv run --extra mcp python3 ...
# pattern from TESTING_WITH_CLAUDE.md into one line per command, so the
# vault path is defined in exactly one place instead of copy-pasted at
# every call site.
#
# Usage:
#   scripts/with_test_vault.sh <profile> <command> [args...]
#
# <profile> is any name — it maps to ~/.secondmind-<profile>/{vault,index.db}.
# TESTING_WITH_CLAUDE.md uses "test" and "import-test".
#
# Examples:
#   scripts/with_test_vault.sh test -m secondmind search "orange sunset"
#   scripts/with_test_vault.sh import-test -m secondmind import /tmp/export.json
#   scripts/with_test_vault.sh test scripts/run_dashboard.py --port 8765
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <profile> <command> [args...]" >&2
    echo "  e.g.: $0 test -m secondmind search \"orange sunset\"" >&2
    exit 64
fi

PROFILE=$1
shift

case "$PROFILE" in
    */* | .. | "")
        echo "secondmind: invalid profile name '$PROFILE' — use a plain name like 'test', not a path" >&2
        exit 64
        ;;
esac

BASE="$HOME/.secondmind-$PROFILE"
export SECONDMIND_VAULT="$BASE/vault"
export SECONDMIND_INDEX_DB="$BASE/index.db"

if ! command -v uv >/dev/null 2>&1; then
    echo "secondmind: 'uv' not found on PATH — install it from https://docs.astral.sh/uv/ first." >&2
    exit 127
fi

echo "secondmind: profile '$PROFILE' -> vault=$SECONDMIND_VAULT" >&2
exec uv run --directory "$REPO_ROOT" --extra mcp python3 "$@"
